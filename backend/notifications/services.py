import logging
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db.models import Max
from django.utils import timezone

from accounts.models import User

from .models import DeviceToken, Notification
from .push import get_backend

log = logging.getLogger(__name__)
Kind, Action = Notification.Kind, Notification.Action

REMINDER_MIN_AGE_DAYS = 14
PRICE_DROP_COOLDOWN_DAYS = 7
DIGEST_COOLDOWN_DAYS = 6
DIGEST_MIN_ITEMS = 3
DIGEST_MIN_COMPAT = 95


def _setting(name, default):
    return getattr(settings, name, default)


# --texts--
def texts(kind, lang, **kw):
    uk = lang != "en"
    if kind == Kind.MEASUREMENT_REMINDER:
        return (("Час оновити заміри", "Оновіть заміри, щоб примірка залишалась точною.") if uk else
                ("Time to update your measurements", "Update them to keep the fitting accurate."))
    if kind == Kind.AVATAR_READY:
        return ((f"Аватар «{kw['name']}» готовий", "Можна переходити до 3D-примірки.") if uk else
                (f"Avatar “{kw['name']}” is ready", "You can start the 3D try-on."))
    if kind == Kind.PRICE_DROP:
        old, new, cur = kw["old"], kw["new"], kw["currency"]
        pct = kw["percent"]
        size = f" Ваш розмір: {kw['size']}." if uk and kw.get("size") else f" Your size: {kw['size']}." if kw.get("size") else ""
        return ((f"Знижка −{pct}%: {kw['title']}", f"Було {old}, стало {new} {cur}.{size}") if uk else
                (f"{pct}% off: {kw['title']}", f"Was {old}, now {new} {cur}.{size}"))
    if kind == Kind.NEW_COLLECTION:
        n = kw["count"]
        return ((f"Нова добірка для вас: {n} нов.", "Нові речі, що чудово сідають на ваш аватар.") if uk else
                (f"A new selection for you: {n} new", "New items that fit your avatar very well."))
    raise ValueError(kind)


# --delivery--
def send_push(user, title, body, data=None):
    tokens = list(user.device_tokens.values_list("token", flat=True))
    if not tokens:
        return 0
    try:
        invalid = get_backend().send(tokens, title, body, data or {}) or []
    except Exception:  # noqa: BLE001  (a push problem must never break the caller)
        log.exception("Push delivery failed")
        return 0
    if invalid:
        DeviceToken.objects.filter(token__in=invalid).delete()
    return len(tokens) - len(invalid)


def notify(user, kind, title, body, action="", data=None):
    note = None
    if user.in_app_enabled:
        note = Notification.objects.create(user=user, kind=kind, title=title, body=body, action=action,
                                           data=data or {})
    if user.push_enabled:
        send_push(user, title, body, {"kind": kind, "action": action, **(data or {}),
                                      **({"notification_id": note.pk} if note else {})})
    return note


# --monthly reminder--
def _zone(user):
    try:
        return ZoneInfo(user.timezone_name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo("Europe/Kyiv")


def reminder_due(user, newest_measurement, now):
    zone = _zone(user)
    local = now.astimezone(zone)
    scheduled = local.replace(day=user.reminder_day, hour=user.reminder_time.hour,
                              minute=user.reminder_time.minute, second=0, microsecond=0)
    if local < scheduled:
        return False
    if user.last_reminder_at and user.last_reminder_at.astimezone(zone).strftime("%Y-%m") == local.strftime("%Y-%m"):
        return False
    if newest_measurement and now - newest_measurement < timedelta(days=_setting("MEASUREMENT_REMINDER_MIN_AGE_DAYS", REMINDER_MIN_AGE_DAYS)):
        return False
    return True


def users_due_for_reminder(now=None):
    now = now or timezone.now()
    candidates = (User.objects.filter(is_active=True, reminder_enabled=True, avatars__isnull=False)
                  .annotate(last_measured=Max("avatars__measurements_updated_at"))
                  .exclude(last_reminder_at__gt=now - timedelta(days=20)))
    return [u for u in candidates if reminder_due(u, u.last_measured, now)]


def send_due_reminders(now=None):
    now = now or timezone.now()
    count = 0
    for user in users_due_for_reminder(now):
        if not (user.in_app_enabled or user.push_enabled):
            continue
        title, body = texts(Kind.MEASUREMENT_REMINDER, user.language)
        avatar = user.avatars.filter(is_default=True).first() or user.avatars.first()
        notify(user, Kind.MEASUREMENT_REMINDER, title, body, Action.UPDATE_MEASUREMENTS,
               {"avatar_id": str(avatar.pk)} if avatar else {})
        user.last_reminder_at = now
        user.save(update_fields=["last_reminder_at"])
        count += 1
    return count


# --avatar ready--
def notify_avatar_ready(avatar):
    user = avatar.user
    title, body = texts(Kind.AVATAR_READY, user.language, name=avatar.name)
    return notify(user, Kind.AVATAR_READY, title, body, Action.OPEN_AVATAR, {"avatar_id": str(avatar.pk)})


# --price drops--
def notify_price_drops(drops, now=None):
    from fitting.models import TryOnItem
    now = now or timezone.now()
    notified = 0
    for product, old, new in drops:
        if old is None or new is None or new >= old:
            continue
        percent = int(round((Decimal(old) - Decimal(new)) / Decimal(old) * 100))
        items = (TryOnItem.objects.filter(product=product, session__user__is_active=True)
                 .select_related("session__user").order_by("id"))
        seen = set()
        for item in items:
            user = item.session.user
            if user.pk in seen:
                continue
            seen.add(user.pk)
            recent = Notification.objects.filter(
                user=user, kind=Kind.PRICE_DROP, data__product_id=product.pk,
                created_at__gte=now - timedelta(days=PRICE_DROP_COOLDOWN_DAYS)).exists()
            if recent:
                continue
            title, body = texts(Kind.PRICE_DROP, user.language, title=product.title, old=f"{Decimal(old):g}",
                                new=f"{Decimal(new):g}", currency=product.currency, percent=percent,
                                size=item.size_label)
            notify(user, Kind.PRICE_DROP, title, body, Action.OPEN_PRODUCT, {"product_id": product.pk})
            notified += 1
    return notified


# --weekly digest--
def send_new_collection_digests(now=None):
    from catalog.models import Product
    from fitting.engine import recommend_size
    now = now or timezone.now()
    fresh = list(Product.objects.filter(owner__isnull=True, created_at__gte=now - timedelta(days=7))
                 .prefetch_related("sizes"))
    if not fresh:
        return 0
    sent = 0
    for user in User.objects.filter(is_active=True, avatars__is_default=True).distinct():
        if not (user.in_app_enabled or user.push_enabled):
            continue
        if Notification.objects.filter(user=user, kind=Kind.NEW_COLLECTION,
                                       created_at__gte=now - timedelta(days=DIGEST_COOLDOWN_DAYS)).exists():
            continue
        avatar = user.avatars.filter(is_default=True).first()
        measurements = avatar.full_measurements()[0]
        count = 0
        for product in fresh:
            if product.gender not in (avatar.gender, "unisex"):
                continue
            rec = recommend_size(product, measurements)
            if rec and rec["compatibility"] >= DIGEST_MIN_COMPAT:
                count += 1
        if count < DIGEST_MIN_ITEMS:
            continue
        title, body = texts(Kind.NEW_COLLECTION, user.language, count=count)
        notify(user, Kind.NEW_COLLECTION, title, body, Action.OPEN_CATALOG,
               {"min_compat": DIGEST_MIN_COMPAT, "ordering": "new"})
        sent += 1
    return sent
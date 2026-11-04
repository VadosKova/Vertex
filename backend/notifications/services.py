from datetime import timedelta

from django.conf import settings
from django.db.models import Max, Q
from django.utils import timezone

from accounts.models import User

from .models import Notification

TEXT = {
    "uk": ("Час оновити заміри", "Ваші параметри не оновлювались понад місяць. Оновіть їх для точної примірки."),
    "en": ("Time to update your measurements", "Your measurements haven't been updated for over a month. Update them for accurate fitting."),
}
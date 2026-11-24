from catalog.models import ZONES

LOOSE_LIMIT_CM = 6.0
LOOSE_TOLERANCE_CM = 1.0
WEIGHTS = {"chest": 1.0, "waist": 1.0, "hips": 1.0, "shoulders": 0.7, "inseam": 0.5, "sleeve": 0.7}
STRETCH_ZONES = {"chest", "waist", "hips"}
COLORS = {"perfect": "#22C55E", "loose": "#FACC15", "tight": "#EF4444"}

LOCATIVE = {
    "uk": {"chest": "у грудях", "waist": "у талії", "hips": "у стегнах", "shoulders": "у плечах", "inseam": "по довжині ноги",
           "sleeve": "по довжині рукавів"},
    "en": {"chest": "in the chest", "waist": "at the waist", "hips": "at the hips", "shoulders": "in the shoulders", "inseam": "in leg length",
           "sleeve": "in sleeve length"},
}


def evaluate_zone(zone, value, lo, hi, stretch):
    cap = hi * (1 + stretch)
    if value > cap:
        over = value - cap
        return {"zone": zone, "status": "tight", "delta_cm": round(value - hi, 1),
                "intensity": round(min(1.0, 0.4 + over / 8), 2), "penalty": 3 * over + 0.5 * (cap - hi)}
    if value > hi:
        return {"zone": zone, "status": "perfect", "delta_cm": 0.0, "intensity": 0.0, "penalty": 0.5 * (value - hi)}
    if value >= lo:
        return {"zone": zone, "status": "perfect", "delta_cm": 0.0, "intensity": 0.0, "penalty": 0.0}
    slack = lo - value
    if slack < LOOSE_TOLERANCE_CM:
        return {"zone": zone, "status": "perfect", "delta_cm": 0.0, "intensity": 0.0, "penalty": 0.0}
    return {"zone": zone, "status": "loose", "delta_cm": round(slack, 1),
            "intensity": round(min(1.0, slack / LOOSE_LIMIT_CM), 2), "penalty": slack}


NOT_FITTING_CAP = 79


def compatibility(score, fits):
    pct = max(0, 100 - int(round(score)))
    return pct if fits else min(pct, NOT_FITTING_CAP)


def _cm(x):
    return max(1, int(x + 0.5))


def _join(items, lang):
    word = " і " if lang == "uk" else " and "
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + word + items[-1]


def _sleeve_phrase(zone, label_lang):
    n = _cm(zone["delta_cm"])
    if label_lang == "uk":
        return f"рукави довші на {n} см" if zone["status"] == "loose" else f"рукави коротші на {n} см"
    return f"sleeves are {n} cm too long" if zone["status"] == "loose" else f"sleeves are {n} cm too short"


def build_verdict(label, zones, lang="uk"):
    lang = lang if lang in LOCATIVE else "uk"
    uk = lang == "uk"
    loc = LOCATIVE[lang]
    perfect = [z for z in zones if z["status"] == "perfect"]
    problems = [z for z in zones if z["status"] != "perfect"]
    if not problems:
        return f"Розмір {label} сидить ідеально по всіх зонах." if uk else f"Size {label} fits perfectly in all zones."

    sleeve = next((z for z in problems if z["zone"] == "sleeve"), None)
    body = [z for z in problems if z["zone"] != "sleeve"]

    if perfect:
        issues = []
        for z in body:
            n = _cm(z["delta_cm"])
            if z["status"] == "loose":
                issues.append(f"{loc[z['zone']]} є запас {n} см" if uk
                              else f"there is {n} cm of extra room {loc[z['zone']]}")
            else:
                issues.append(f"{loc[z['zone']]} тисне (бракує {n} см)" if uk
                              else f"it is tight {loc[z['zone']]} (short by {n} cm)")
        if sleeve:
            issues.append(_sleeve_phrase(sleeve, lang))
        good = _join([loc[z["zone"]] for z in perfect], lang)
        lead = f"Розмір {label} сидить ідеально " if uk else f"Size {label} fits perfectly "
        return lead + good + (", але " if uk else ", but ") + ", ".join(issues) + "."

    loose = [z for z in body if z["status"] == "loose"]
    tight = [z for z in body if z["status"] == "tight"]
    parts = []
    if loose:
        items = _join([f"{_cm(z['delta_cm'])} см {loc[z['zone']]}" if uk else f"{_cm(z['delta_cm'])} cm {loc[z['zone']]}"
                       for z in loose], lang)
        parts.append(("запас " if uk else "extra room: ") + items)
    if tight:
        items = _join([f"{_cm(z['delta_cm'])} см {loc[z['zone']]}" if uk else f"{_cm(z['delta_cm'])} cm {loc[z['zone']]}"
                       for z in tight], lang)
        parts.append(("бракує " if uk else "short by ") + items)
    text = (", але " if uk else ", but ").join(parts)
    if sleeve:
        text = (text + ", " if text else "") + _sleeve_phrase(sleeve, lang)
    statuses = {z["status"] for z in problems}
    if statuses == {"loose"}:
        head = f"Розмір {label} сидить вільно" if uk else f"Size {label} fits loosely"
    elif statuses == {"tight"}:
        head = f"Розмір {label} тисне" if uk else f"Size {label} is tight"
    else:
        head = f"Розмір {label}" if uk else f"Size {label}"
    return f"{head}: {text}."


def evaluate_size(size, measurements, stretch, lang="uk"):
    zones = []
    for zone, key in ZONES.items():
        rng = size.range(zone)
        value = measurements.get(key)
        if rng is None or value is None:
            continue
        zones.append(evaluate_zone(zone, value, rng[0], rng[1], stretch if zone in STRETCH_ZONES else 0.0))
    score = sum(WEIGHTS[z["zone"]] * z["penalty"] for z in zones)
    fits = bool(zones) and all(z["status"] != "tight" for z in zones) and not any(
        z["status"] == "loose" and z["delta_cm"] > LOOSE_LIMIT_CM for z in zones)
    public = [{k: v for k, v in z.items() if k != "penalty"} | {"color": COLORS[z["status"]]} for z in zones]
    return {"label": size.label, "order": size.order, "score": round(score, 2), "fits": fits,
            "compatibility": compatibility(score, fits), "zones": public,
            "verdict": build_verdict(size.label, public, lang)}


def evaluate_product(product, measurements, lang="uk"):
    sizes = list(product.sizes.all())
    results = [evaluate_size(s, measurements, product.fabric_stretch, lang) for s in sizes]
    return [r for r in results if r["zones"]]


def recommend_size(product, measurements, lang="uk"):
    results = evaluate_product(product, measurements, lang)
    if not results:
        return None
    return min(results, key=lambda r: (r["score"], -r["order"]))
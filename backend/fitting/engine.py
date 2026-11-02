from catalog.models import ZONES

LOOSE_LIMIT_CM = 6.0
LOOSE_TOLERANCE_CM = 1.0
WEIGHTS = {"chest": 1.0, "waist": 1.0, "hips": 1.0, "shoulders": 0.7, "inseam": 0.5}
COLORS = {"perfect": "#22C55E", "loose": "#FACC15", "tight": "#EF4444"}

LOCATIVE = {
    "uk": {"chest": "у грудях", "waist": "у талії", "hips": "у стегнах", "shoulders": "у плечах", "inseam": "по довжині ноги"},
    "en": {"chest": "in the chest", "waist": "at the waist", "hips": "at the hips", "shoulders": "in the shoulders", "inseam": "in leg length"},
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


def _cm(x):
    return max(1, int(x + 0.5))


def build_verdict(label, zones, lang="uk"):
    lang = lang if lang in LOCATIVE else "uk"
    loc = LOCATIVE[lang]
    perfect = [loc[z["zone"]] for z in zones if z["status"] == "perfect"]
    issues = []
    for z in zones:
        if z["status"] == "loose":
            issues.append(f"{loc[z['zone']]} є запас {_cm(z['delta_cm'])} см" if lang == "uk"
                          else f"there is {_cm(z['delta_cm'])} cm of extra room {loc[z['zone']]}")
        elif z["status"] == "tight":
            issues.append(f"{loc[z['zone']]} тисне (бракує {_cm(z['delta_cm'])} см)" if lang == "uk"
                          else f"it is tight {loc[z['zone']]} (short by {_cm(z['delta_cm'])} cm)")
    if not issues:
        return (f"Розмір {label} сидить ідеально по всіх зонах." if lang == "uk"
                else f"Size {label} fits perfectly in all zones.")
    if not perfect:
        return f"Розмір {label}: " + ", ".join(issues) + "." if lang == "uk" else f"Size {label}: " + ", ".join(issues) + "."
    joiner = " і " if lang == "uk" else " and "
    lead = f"Розмір {label} сидить ідеально " if lang == "uk" else f"Size {label} fits perfectly "
    but = ", але " if lang == "uk" else ", but "
    return lead + joiner.join(perfect) + but + ", ".join(issues) + "."


def evaluate_size(size, measurements, stretch, lang="uk"):
    zones = []
    for zone, key in ZONES.items():
        rng = size.range(zone)
        value = measurements.get(key)
        if rng is None or value is None:
            continue
        zones.append(evaluate_zone(zone, value, rng[0], rng[1], stretch))
    score = sum(WEIGHTS[z["zone"]] * z["penalty"] for z in zones)
    fits = bool(zones) and all(z["status"] != "tight" for z in zones) and not any(
        z["status"] == "loose" and z["delta_cm"] > LOOSE_LIMIT_CM for z in zones)
    public = [{k: v for k, v in z.items() if k != "penalty"} | {"color": COLORS[z["status"]]} for z in zones]
    return {"label": size.label, "order": size.order, "score": round(score, 2), "fits": fits,
            "zones": public, "verdict": build_verdict(size.label, public, lang)}
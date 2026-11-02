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
SPEC = {
    "head_circumference": ("head_neck", 48, 66, "Стрічка по лобі над бровами та навколо потилиці", "Tape across the forehead above the brows and around the back of the head"),
    "face_length": ("head_neck", 15, 27, "Від лінії росту волосся до підборіддя", "Hairline to chin"),
    "face_width": ("head_neck", 10, 18, "Між виличними кістками", "Between the cheekbones"),
    "neck_circumference": ("head_neck", 28, 50, "Біля основи шиї, стрічка не тисне", "Around the base of the neck, tape not tight"),
    "shoulder_width": ("torso", 30, 60, "Між кістковими точками плечей ззаду", "Between the shoulder bone points across the back"),
    "chest_circumference": ("torso", 60, 160, "По найвищих точках грудей, стрічка паралельна підлозі", "Over the fullest part of the chest, tape parallel to the floor"),
    "underbust_circumference": ("torso", 55, 140, "Одразу під грудьми", "Directly under the bust"),
    "waist_circumference": ("torso", 45, 160, "У найвужчому місці тулуба", "At the narrowest part of the torso"),
    "abdomen_circumference": ("torso", 50, 170, "На рівні пупка / нижнього преса", "At navel level / lower abdomen"),
    "torso_length": ("torso", 30, 60, "Від сьомого шийного хребця до талії", "C7 vertebra to the waist"),
    "arm_length": ("arms", 45, 80, "Від плечового суглоба до зап'ястя", "Shoulder joint to wrist"),
    "bicep_relaxed": ("arms", 18, 50, "Найширше місце плеча, рука розслаблена", "Widest part of the upper arm, relaxed"),
    "bicep_flexed": ("arms", 20, 55, "Те саме з напруженим біцепсом", "Same with the biceps flexed"),
    "forearm_circumference": ("arms", 17, 40, "Найширше місце передпліччя", "Widest part of the forearm"),
    "wrist_circumference": ("arms", 10, 24, "Над кісточкою зап'ястя", "Just above the wrist bone"),
    "hip_circumference": ("lower", 70, 170, "По найвипнутіших точках сідниць", "Over the fullest part of the buttocks"),
    "inseam": ("lower", 55, 100, "Внутрішній шов: від паху до кісточки", "Crotch to ankle bone"),
    "outseam": ("lower", 80, 130, "Зовнішній шов: від талії до підлоги", "Waist to floor along the outer leg"),
    "thigh_circumference": ("lower", 35, 95, "У верхній третині стегна", "Upper third of the thigh"),
    "knee_circumference": ("lower", 25, 55, "Навколо коліна", "Around the knee"),
    "calf_circumference": ("lower", 25, 60, "Найширше місце литки", "Widest part of the calf"),
    "ankle_circumference": ("lower", 15, 35, "Над кісточкою", "Just above the ankle bone"),
    "foot_length": ("foot", 20, 33, "Від п'яти до найдовшого пальця", "Heel to the longest toe"),
    "foot_size_eu": ("foot", 34, 50, "Розмір на взутті (EU), або за довжиною стопи", "Size on your shoe (EU), or from your foot length"),
    "foot_width": ("foot", 7, 14, "У найширшому місці стопи", "Widest part of the foot"),
}

REQUIRED = ("chest_circumference", "waist_circumference", "hip_circumference")

HEIGHT_RANGE = (100, 250)
WEIGHT_RANGE = (30, 250)
AGE_RANGE = (12, 100)

_RATIOS = {
    "shoulder_width": (0.259, 0.230),
    "neck_circumference": (0.215, 0.185),
    "torso_length": (0.300, 0.290),
    "arm_length": (0.330, 0.320),
    "inseam": (0.450, 0.450),
    "outseam": (0.600, 0.600),
    "head_circumference": (0.325, 0.315),
    "foot_length": (0.150, 0.145),
    "foot_width": (0.057, 0.054),
}


def validate_measurements(data: dict) -> dict:
    errors = {}
    for key, value in data.items():
        if key not in SPEC:
            errors[key] = "Unknown measurement."
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors[key] = "Must be a number."
            continue
        lo, hi = SPEC[key][1], SPEC[key][2]
        if not lo <= value <= hi:
            errors[key] = f"Must be between {lo} and {hi} cm."
    if errors:
        return errors

    def pair(a, b, ok, msg):
        if a in data and b in data and not ok(data[a], data[b]):
            errors[a] = msg

    pair("underbust_circumference", "chest_circumference", lambda u, c: u <= c, "Underbust cannot exceed chest.")
    pair("bicep_relaxed", "bicep_flexed", lambda r, f: r <= f, "Relaxed bicep cannot exceed flexed.")
    pair("inseam", "outseam", lambda i, o: i < o, "Inseam must be shorter than outseam.")
    pair("foot_width", "foot_length", lambda w, l: w < l, "Foot width must be smaller than length.")
    pair("wrist_circumference", "forearm_circumference", lambda w, f: w <= f, "Wrist cannot exceed forearm.")
    return errors


def validate_bmi(height_cm, weight_kg):
    bmi = weight_kg / (height_cm / 100) ** 2
    return None if 12 <= bmi <= 60 else "Height/weight combination looks implausible."


def eu_to_length_cm(eu):
    return round(eu * 2 / 3 - 1.0, 1)


def length_to_eu(length_cm):
    return round((length_cm + 1.0) * 1.5)


def estimate_missing(height_cm: float, gender: str, measurements: dict):
    idx = 0 if gender == "male" else 1
    full, estimated = dict(measurements), []
    for key, ratios in _RATIOS.items():
        if key not in full and key != "foot_length":
            full[key] = round(height_cm * ratios[idx], 1)
            estimated.append(key)
    if "foot_length" not in full:
        if "foot_size_eu" in full:
            full["foot_length"] = eu_to_length_cm(full["foot_size_eu"])
        else:
            full["foot_length"] = round(height_cm * _RATIOS["foot_length"][idx], 1)
        estimated.append("foot_length")
    if "foot_size_eu" not in full:
        full["foot_size_eu"] = length_to_eu(full["foot_length"])
        estimated.append("foot_size_eu")
    if "thigh_circumference" not in full and "hip_circumference" in full:
        full["thigh_circumference"] = round(full["hip_circumference"] * 0.58, 1)
        estimated.append("thigh_circumference")
    return full, estimated


_WIZARD_ROWS = [
    (2, False, ["shoulder_width", "chest_circumference", "underbust_circumference", "waist_circumference",
                "abdomen_circumference", "neck_circumference", "arm_length", "bicep_relaxed"]),
    (3, False, ["hip_circumference", "inseam", "thigh_circumference", "knee_circumference", "calf_circumference",
                "foot_size_eu"]),
    (2, True, ["bicep_flexed", "forearm_circumference", "wrist_circumference", "torso_length",
               "head_circumference", "face_length", "face_width"]),
    (3, True, ["outseam", "ankle_circumference", "foot_length", "foot_width"]),
]
WIZARD = {}
for _step, _adv, _keys in _WIZARD_ROWS:
    for _key in _keys:
        WIZARD[_key] = (_step, _adv, len(WIZARD) + 1)

_LENGTHS = {"arm_length", "torso_length", "inseam", "outseam", "face_length", "foot_length"}
_WIDTHS = {"shoulder_width", "face_width", "foot_width"}
_PREP = {
    "circumference": ("Станьте прямо, розслабте м'язи й дихайте спокійно.", "Stand straight, relax and breathe calmly."),
    "length": ("Станьте прямо, ноги разом, дивіться перед собою.", "Stand straight, feet together, look ahead."),
    "width": ("Станьте прямо й розслабтеся.", "Stand straight and relax."),
}
_CHECK = {
    "circumference": ("Стрічка прилягає щільно, але не стискає. Зніміть значення на видиху.",
                      "The tape should be snug, not tight. Read the value as you exhale."),
    "length": ("Тримайте стрічку рівно, без провисання. Запишіть значення з точністю до 0,5 см.",
               "Keep the tape straight, without sagging. Record to the nearest 0.5 cm."),
    "width": ("Не стискайте стрічку, міряйте по прямій. Запишіть значення з точністю до 0,5 см.",
              "Do not press the tape; measure in a straight line. Record to the nearest 0.5 cm."),
}
_EU_STEPS = {
    "uk": ["Зніміть взуття й станьте на рівну поверхню.",
           "Скористайтеся розміром (EU) на вашому взутті. Якщо його не знаєте, виміряйте довжину стопи.",
           "Для півтора розміру між двома оберіть більший. Значення з вказаного діапазону."],
    "en": ["Take off your shoes and stand on a flat surface.",
           "Use the EU size on your shoes. If you do not know it, measure your foot length instead.",
           "Between two sizes, choose the bigger one. Values are limited to the allowed range."],
}


def kind_of(key):
    return "length" if key in _LENGTHS else "width" if key in _WIDTHS else "circumference"


def spec_payload():
    rows = []
    for key, (group, lo, hi, uk, en) in SPEC.items():
        step, advanced, order = WIZARD[key]
        kind = kind_of(key)
        steps = _EU_STEPS if key == "foot_size_eu" else {
            "uk": [_PREP[kind][0], uk, _CHECK[kind][0]], "en": [_PREP[kind][1], en, _CHECK[kind][1]]}
        rows.append({"key": key, "group": group, "min": lo, "max": hi,
                     "unit": "EU" if key == "foot_size_eu" else "cm", "step": step, "advanced": advanced,
                     "order": order, "hint": {"uk": uk, "en": en}, "steps": steps})
    return sorted(rows, key=lambda r: r["order"])
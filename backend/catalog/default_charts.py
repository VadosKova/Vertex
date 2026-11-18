FAMILY = {"tshirts": "tops", "hoodies": "tops", "jeans": "jeans", "dresses": "dresses"}

_TOPS_MALE = {
    "XS": ((82, 88), (68, 74), (86, 92)), "S": ((88, 92), (74, 78), (92, 96)),
    "M": ((92, 100), (78, 86), (96, 102)), "L": ((100, 108), (86, 94), (102, 110)),
    "XL": ((108, 116), (94, 102), (110, 118)), "2XL": ((116, 124), (102, 110), (118, 126)),
    "3XL": ((124, 132), (110, 118), (126, 134)), "4XL": ((132, 140), (118, 126), (134, 142)),
    "5XL": ((140, 148), (126, 134), (142, 150)), "6XL": ((148, 156), (134, 142), (150, 158)),
}
_TOPS_FEMALE = {
    "XS": ((80, 84), (62, 66), (86, 90)), "S": ((84, 88), (66, 70), (90, 94)),
    "M": ((88, 94), (70, 76), (94, 100)), "L": ((94, 100), (76, 82), (100, 106)),
    "XL": ((100, 108), (82, 90), (106, 114)), "2XL": ((108, 116), (90, 98), (114, 122)),
    "3XL": ((116, 124), (98, 106), (122, 130)), "4XL": ((124, 132), (106, 114), (130, 138)),
    "5XL": ((132, 140), (114, 122), (138, 146)), "6XL": ((140, 148), (122, 130), (146, 154)),
}
_DRESSES_FEMALE = _TOPS_FEMALE

_JEANS_MALE = {
    "26": ((66, 70), (84, 88)), "28": ((70, 74), (88, 92)), "30": ((74, 79), (92, 97)),
    "32": ((79, 85), (97, 102)), "34": ((85, 91), (102, 108)), "36": ((91, 97), (108, 114)),
    "38": ((97, 103), (114, 120)), "40": ((103, 109), (120, 126)), "42": ((109, 115), (126, 132)),
    "44": ((115, 121), (132, 138)), "46": ((121, 127), (138, 144)),
}
_JEANS_FEMALE = {
    "24": ((58, 62), (84, 88)), "25": ((62, 66), (88, 92)), "26": ((66, 70), (92, 96)),
    "27": ((70, 74), (96, 100)), "28": ((74, 78), (100, 104)), "29": ((78, 82), (104, 108)),
    "30": ((82, 86), (108, 112)), "31": ((86, 90), (112, 116)), "32": ((90, 94), (116, 120)),
    "34": ((94, 98), (120, 124)), "36": ((98, 102), (124, 128)), "38": ((102, 108), (128, 134)),
    "40": ((108, 114), (134, 140)), "42": ((114, 120), (140, 146)),
}


def _entries(chart, jeans=False):
    out = []
    zones = ("waist", "hips") if jeans else ("chest", "waist", "hips")
    for order, (label, ranges) in enumerate(chart.items()):
        entry = {"label": label, "order": order}
        for zone, (lo, hi) in zip(zones, ranges):
            entry[f"{zone}_min"], entry[f"{zone}_max"] = float(lo), float(hi)
        out.append(entry)
    return out


def default_chart(category_slug, gender):
    family = FAMILY.get(category_slug)
    if family is None:
        return None
    if family == "dresses":
        return _entries(_DRESSES_FEMALE) if gender in ("female", "unisex") else None
    male = gender in ("male", "unisex")
    if family == "tops":
        return _entries(_TOPS_MALE if male else _TOPS_FEMALE)
    return _entries(_JEANS_MALE if male else _JEANS_FEMALE, jeans=True)
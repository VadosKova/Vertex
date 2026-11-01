import numpy as np
from PIL import Image

MIN_SIDE = 480
BLUR_THRESHOLD = 60.0
DARK_THRESHOLD = 55
BRIGHT_THRESHOLD = 210


def assess(img: Image.Image) -> dict:
    w, h = img.size
    issues = []
    if min(w, h) < MIN_SIDE:
        issues.append("too_small")
    probe = img.convert("L")
    probe.thumbnail((640, 640))
    g = np.asarray(probe, dtype=np.float32)
    lap = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    blur = float(lap.var())
    brightness = float(g.mean())
    if blur < BLUR_THRESHOLD:
        issues.append("blurry")
    if brightness < DARK_THRESHOLD:
        issues.append("too_dark")
    elif brightness > BRIGHT_THRESHOLD:
        issues.append("too_bright")
    return {"ok": not issues, "issues": issues, "blur_score": round(blur, 1),
            "brightness": round(brightness, 1), "width": w, "height": h}
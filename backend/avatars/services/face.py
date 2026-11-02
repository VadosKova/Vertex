import io

import numpy as np
from PIL import Image


class BasicFaceAnalyzer:
    def analyze(self, photo_bytes: bytes) -> dict:
        img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
        w, h = img.size
        crop = img.crop((int(w * .35), int(h * .30), int(w * .65), int(h * .55)))
        r, g, b = (float(x) for x in np.asarray(crop).reshape(-1, 3).mean(axis=0))
        return {"engine": "basic", "skin_rgb": [round(r), round(g), round(b)], "landmarks": None}
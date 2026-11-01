import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PIXELS = 40_000_000
MAX_SIDE = 1600
ALLOWED_FORMATS = ("JPEG", "PNG")


class InvalidPhoto(Exception):
    pass


def load_and_sanitise(data: bytes):
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ALLOWED_FORMATS:
            raise InvalidPhoto("Only JPEG and PNG images are accepted.")
        if img.size[0] * img.size[1] > MAX_PIXELS:
            raise InvalidPhoto("Image resolution is too large.")
        img.load()
    except InvalidPhoto:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise InvalidPhoto("Only valid JPEG and PNG images are accepted.")
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return img, buf.getvalue()
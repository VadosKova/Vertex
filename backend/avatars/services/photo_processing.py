import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PIXELS = 40_000_000
MAX_SIDE = 1600
ALLOWED_FORMATS = ("JPEG", "PNG")


class InvalidPhoto(Exception):
    pass
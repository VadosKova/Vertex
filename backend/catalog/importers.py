import ipaddress
import json
import re
import socket
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings

MEASURE_SYNONYMS = {
    "chest": ("chest", "bust", "груд"),
    "waist": ("waist", "тал"),
    "hips": ("hip", "стег", "сідн"),
    "shoulders": ("shoulder", "плеч"),
    "inseam": ("inseam", "внутріш", "довжина ноги"),
}
SIZE_HEADERS = ("size", "розмір")
CATEGORY_KEYWORDS = {
    "tshirts": ("t-shirt", "tee", "футболк"),
    "hoodies": ("hoodie", "sweatshirt", "худі", "світшот"),
    "jeans": ("jeans", "denim", "джинс"),
    "dresses": ("dress", "сукн", "плат"),
}
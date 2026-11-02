import ipaddress
import json
import re
import socket
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings

MEASURE_SYNONYMS = {
    "chest": ("chest", "bust", "груди"),
    "waist": ("waist", "талія"),
    "hips": ("hip", "стегна", "сідн"),
    "shoulders": ("shoulder", "плечі"),
    "inseam": ("inseam", "внутріш", "довжина ноги"),
}
SIZE_HEADERS = ("size", "розмір")
CATEGORY_KEYWORDS = {
    "tshirts": ("t-shirt", "tee", "футболка"),
    "hoodies": ("hoodie", "sweatshirt", "худі", "світшот"),
    "jeans": ("jeans", "denim", "джинси"),
    "dresses": ("dress", "сукня", "плаття"),
}
from urllib.parse import urlparse

from .importers import ADAPTERS

SHOPS = [
    {"name": "Rozetka", "domain": "rozetka.com.ua"},
    {"name": "Zara", "domain": "zara.com"},
    {"name": "H&M", "domain": "hm.com"},
    {"name": "ASOS", "domain": "asos.com"},
]


def _mode(domain):
    return "adapter" if domain in ADAPTERS else "universal"


def listed_shops():
    return [{**shop, "mode": _mode(shop["domain"])} for shop in SHOPS]


def shop_for(url):
    host = (urlparse(url).hostname or "").lower()
    for shop in SHOPS:
        if host == shop["domain"] or host.endswith("." + shop["domain"]):
            return {"name": shop["name"], "domain": shop["domain"]}
    bare = host[4:] if host.startswith("www.") else host
    return {"name": bare, "domain": bare}
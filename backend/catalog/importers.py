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


class PageImportError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def assert_public_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise PageImportError("invalid_url", "Only http(s) URLs are allowed.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror:
        raise PageImportError("unresolvable", "Host cannot be resolved.")
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise PageImportError("forbidden_host", "URL points to a non-public address.")


def fetch_html(url: str) -> str:
    headers = {"User-Agent": "VertexBot/1.0 (+size-chart-import)"}
    for _ in range(4):
        assert_public_url(url)
        try:
            resp = requests.get(url, headers=headers, timeout=(3, 8), stream=True, allow_redirects=False)
        except requests.RequestException:
            raise PageImportError("fetch_failed", "Could not download the page.")
        if resp.is_redirect and resp.headers.get("Location"):
            url = urljoin(url, resp.headers["Location"])
            continue
        if resp.status_code >= 400:
            raise PageImportError("fetch_failed", f"Remote site answered {resp.status_code}.")
        body = resp.raw.read(settings.IMPORT_MAX_BYTES + 1, decode_content=True)
        if len(body) > settings.IMPORT_MAX_BYTES:
            raise PageImportError("too_large", "Page is too large.")
        return body.decode(resp.encoding or "utf-8", errors="replace")
    raise PageImportError("too_many_redirects", "Too many redirects.")


_RANGE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)")
_NUM = re.compile(r"(\d+(?:[.,]\d+)?)")
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


def parse_range(text: str, inches=False):
    f = 2.54 if inches else 1.0
    m = _RANGE.search(text)
    if m:
        a, b = (float(x.replace(",", ".")) * f for x in m.groups())
        return (min(a, b), max(a, b))
    m = _NUM.search(text)
    if m:
        v = float(m.group(1).replace(",", ".")) * f
        return (v - 2, v + 2)
    return None


def _find_product_jsonld(soup):
    def walk(node):
        if isinstance(node, list):
            for n in node:
                found = walk(n)
                if found:
                    return found
        elif isinstance(node, dict):
            t = node.get("@type")
            if t == "Product" or (isinstance(t, list) and "Product" in t):
                return node
            return walk(node.get("@graph", []))
        return None

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            found = walk(json.loads(tag.string or ""))
        except (ValueError, TypeError):
            continue
        if found:
            return found
    return None


def _parse_size_table(soup):
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["th", "td"])]
        size_col = next((i for i, h in enumerate(headers)
                         if any(h.startswith(s) for s in SIZE_HEADERS)), None)
        cols = {}
        for i, h in enumerate(headers):
            for zone, syns in MEASURE_SYNONYMS.items():
                if i != size_col and zone not in cols and any(s in h for s in syns):
                    cols[zone] = (i, bool(re.search(r"\b(in|inch|inches)\b", h)) or '"' in h)
        if size_col is None or not cols:
            continue
        sizes = []
        for order, row in enumerate(rows[1:]):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) <= size_col or not cells[size_col]:
                continue
            entry = {"label": cells[size_col][:10].upper(), "order": order}
            for zone, (i, inches) in cols.items():
                rng = parse_range(cells[i], inches) if i < len(cells) else None
                if rng:
                    entry[f"{zone}_min"], entry[f"{zone}_max"] = round(rng[0], 1), round(rng[1], 1)
            if len(entry) > 2:
                sizes.append(entry)
        if sizes:
            return sizes
    return []


def parse_product_page(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    ld = _find_product_jsonld(soup) or {}
    title = ld.get("name") or (soup.find("meta", property="og:title") or {}).get("content") \
        or (soup.title.string.strip() if soup.title and soup.title.string else "")
    brand = ld.get("brand")
    brand = brand.get("name") if isinstance(brand, dict) else brand
    image = ld.get("image") or (soup.find("meta", property="og:image") or {}).get("content", "")
    if isinstance(image, list):
        image = image[0] if image else ""
    return {"title": (title or "").strip()[:200], "brand": (brand or "Unknown").strip()[:80],
            "image_url": image if isinstance(image, str) else "", "sizes": _parse_size_table(soup)}


def guess_category_slug(title: str):
    low = title.lower()
    for slug, words in CATEGORY_KEYWORDS.items():
        if any(w in low for w in words):
            return slug
    return None
"""
CORE_ENGINE/ITEM_ART.PY  --  Item images for the visual gear view. (W3-12)

Finds the 2D art for an item the same way a browser would: fetch its poe2db
page (uniques by name, everything else by base type) and read the og:image /
first item-art <img>. Results cache to data_engine/item_art/<slug>.png so
each item is fetched at most once, ever. Fully guarded: no requests library,
no network, no match -> returns None and the gear card stays text-styled.

Call from worker threads only (network + disk).
"""

import os
import re

try:
    import requests
except Exception:
    requests = None

ART_DIR = os.path.join("data_engine", "item_art")
UA = {"User-Agent": "Mozilla/5.0 (KalandraOverlay art cache)"}
_IMG_RE = re.compile(
    r'(?:property="og:image"\s+content="([^"]+)"|'
    r'content="([^"]+)"\s+property="og:image"|'
    r'<img[^>]+src="([^"]*(?:2DItems|gen/image)[^"]*)")', re.I)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_") or "item"


def cached_path(name):
    return os.path.join(ART_DIR, slugify(name) + ".png")


def get_art(name, base="", fetch=True, timeout=12):
    """Return a local image path for the item, or None.

    Checks the cache first (by unique name, then base). With fetch=True and
    network available, tries poe2db pages for the name then the base."""
    for key in (name, base):
        if key:
            p = cached_path(key)
            if os.path.exists(p) and os.path.getsize(p) > 200:
                return p
    if not fetch or requests is None:
        return None
    os.makedirs(ART_DIR, exist_ok=True)
    for key in (name, base):
        if not key:
            continue
        page = "https://poe2db.tw/us/" + key.strip().replace(" ", "_")
        try:
            r = requests.get(page, headers=UA, timeout=timeout)
            if r.status_code != 200:
                continue
            m = _IMG_RE.search(r.text)
            if not m:
                continue
            img_url = next(g for g in m.groups() if g)
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif img_url.startswith("/"):
                img_url = "https://poe2db.tw" + img_url
            ir = requests.get(img_url, headers=UA, timeout=timeout)
            if ir.status_code == 200 and len(ir.content) > 200:
                p = cached_path(key)
                with open(p, "wb") as f:
                    f.write(ir.content)
                return p
        except Exception:
            continue
    return None

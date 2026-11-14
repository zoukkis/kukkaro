"""Real S-Group products for product cards and the order (public zone: no customer data).

A product is read from an S-kaupat product page that Exa found: the name from the page title, the
picture from the page's preview image, and the price from the page text ("n. Noin 1,89 €"). The
price is parsed in code, never written by a model, and a product without a readable price is never
priced or added to an order. Products are kept server-side by id (data/cache/products), so the order
endpoint prices them itself and never trusts a price sent by the browser.

Own-brand alternatives: the synthetic receipts know each branded item's store-brand twin
(receipts/catalog.csv); `own_brand_for(twin)` searches S-kaupat for the real S-Group own-brand
product of that kind. The search text comes from the static map below, never from customer data.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

from kukkaro.butler import exa_client

OWN_BRANDS = ("Rainbow", "Kotimaista", "X-tra", "Xtra")  # S-Group's own brands
STORE = "S-kaupat"
_PRODUCT_URL = re.compile(r"^https?://(www\.)?s-kaupat\.fi/tuote/", re.IGNORECASE)
# S-kaupat pages say "n. Noin 1,89 €" (about 1.89 € in the chosen store). The first such price is the product's.
_PRICE = re.compile(r"Noin\s+(\d{1,4}(?:[  ]\d{3})*,\d{2})\s*€", re.IGNORECASE)

# Store-brand twin in the synthetic receipt catalog -> Finnish search for the real own-brand product.
TWIN_QUERIES = {
    "Store brand milk 1 l": "Rainbow maito 1 l",
    "Store brand lactose-free milk 1 l": "Rainbow laktoositon maitojuoma 1 l",
    "Store brand oat drink 1 l": "Rainbow kaurajuoma 1L",
    "Store brand yoghurt 1 kg": "Rainbow maustamaton jogurtti 1 kg",
    "Store brand butter 500 g": "Kotimaista voi 500 g",
    "Store brand cheese 1 kg": "Kotimaista edam 1 kg juusto",
    "Store brand eggs 10 pcs": "Kotimaista kananmuna 10 kpl",
    "Store brand rye bread 500 g": "Kotimaista ruisleipä",
    "Store brand toast bread 500 g": "Rainbow paahtoleipä 500 g",
    "Store brand oatmeal 1 kg": "Rainbow kaurahiutale 1 kg",
    "Store brand pasta 500 g": "Rainbow makaroni 500 g",
    "Store brand rice 1 kg": "Rainbow riisi 1 kg",
    "Store brand crushed tomatoes 400 g": "Rainbow tomaattimurska 400 g",
    "Store brand muesli 500 g": "Rainbow mysli 500 g",
    "Store brand ground coffee 500 g": "Rainbow kahvi 500 g",
    "Store brand minced meat 400 g": "Kotimaista jauheliha 400 g",
    "Store brand chicken fillet 450 g": "Kotimaista broilerin fileesuikale",
    "Store brand cold cuts 300 g": "Kotimaista leikkele 300 g",
    "Store brand frozen vegetables 500 g": "Rainbow pakastevihannes 500 g",
    "Store brand toilet paper 8 rolls": "X-tra wc-paperi 8 rl",
    "Store brand dish soap 500 ml": "Xtra astianpesuaine 500 ml",
    "Store brand laundry detergent 1 l": "Rainbow nestemäinen pyykinpesuaine 1 l",
}


def _registry_dir():
    from kukkaro.data.settings import data_dir
    d = data_dir() / "cache" / "products"
    d.mkdir(parents=True, exist_ok=True)
    return d


def parse_price(text: str) -> float | None:
    m = _PRICE.search(text or "")
    if not m:
        return None
    return float(Decimal(m.group(1).replace(" ", "").replace(" ", "").replace(",", ".")))


def is_own_brand(name: str) -> bool:
    return (name or "").strip().lower().startswith(tuple(b.lower() for b in OWN_BRANDS))


def product_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def from_page(title: str, url: str, text: str, image: str | None, replaces: str | None = None) -> dict[str, Any] | None:
    """A product from one S-kaupat product page, or None if the page is not a product page."""
    if not _PRODUCT_URL.match(url or ""):
        return None
    name = (title or "").split(" | ")[0].strip()
    if not name:
        return None
    p = {"id": product_id(url), "name": name, "price_eur": parse_price(text), "image": image or None, "url": url,
         "store": STORE, "own_brand": is_own_brand(name), "price_source": "the product page on s-kaupat.fi"}
    if replaces:
        p["replaces"] = replaces
    _save(p)
    return p


def _save(p: dict[str, Any]) -> None:
    path = _registry_dir() / f"{p['id']}.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    path.write_text(json.dumps({**old, **{k: v for k, v in p.items() if v is not None}}, ensure_ascii=False), encoding="utf-8")


def get(pid: str) -> dict[str, Any] | None:
    """A product previously found on S-kaupat, by id (server-side prices only)."""
    if not re.fullmatch(r"[0-9a-f]{12}", pid or ""):
        return None
    path = _registry_dir() / f"{pid}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def from_sources(sources: list[dict]) -> list[dict[str, Any]]:
    """Product cards from a research result's numbered sources (S-kaupat product pages only)."""
    out = []
    for s in sources:
        p = from_page(s.get("title", ""), s.get("url", ""), s.get("text", ""), s.get("image"))
        if p:
            out.append({**p, "n": s.get("n")})
    return sorted(out, key=lambda p: (not p["own_brand"], p["price_eur"] is None))[:6]  # own brands first


def own_brand_for(twin: str, branded_item: str) -> dict[str, Any] | None:
    """The real S-Group own-brand product for a store-brand twin, with picture and page price, or None."""
    q = TWIN_QUERIES.get(twin)
    if not q:
        return None
    res = exa_client.search(q, ["s-kaupat.fi"], num_results=8)
    found = [from_page(r["title"], r["url"], " ".join(r.get("highlights") or []), r.get("image"), replaces=branded_item)
             for r in res.get("results", [])]
    found = [p for p in found if p and p["price_eur"] is not None]
    size = _size(twin)
    # Best first: own brand with the same package size, then own brand, then the same size, then anything.
    ranked = sorted(found, key=lambda p: (not p["own_brand"] or _size(p["name"]) != size, not p["own_brand"],
                                          _size(p["name"]) != size))
    return ranked[0] if ranked else None


_SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|kpl|pcs|rl|rolls)(?![a-z])", re.IGNORECASE)
_UNIT = {"pcs": "kpl", "rolls": "rl"}


def _size(name: str) -> str | None:
    """'Oat drink 1 l' -> '1l', 'Rainbow kaurajuoma 1L' -> '1l', '10 pcs' -> '10kpl'."""
    m = _SIZE.search(name or "")
    if not m:
        return None
    unit = m.group(2).lower()
    return m.group(1).replace(",", ".") + _UNIT.get(unit, unit)

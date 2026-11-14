"""Thin wrapper over the Exa SDK for the Butler: search + highlights, Finnish focus, disk cache.

- `type="auto"` (about 1 s) with highlights: Exa's own advice for interactive use (500 characters of
  highlights are about as accurate as 8,000 characters of page text).
- Optional domain filters, e.g. official Finnish sites (OFFICIAL_DOMAINS), and a Finland user location.
- Every response is cached on disk in data/cache/exa/ (gitignored), keyed by query + options, so a
  repeated query (the recorded demo) is instant and free. A new query (a judge's) always goes live.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from kukkaro.data.settings import data_dir

log = logging.getLogger("kukkaro.exa")

OFFICIAL_DOMAINS = ["kela.fi", "vero.fi", "kkv.fi", "suomi.fi", "finlex.fi", "energiavirasto.fi",
                    "kuluttajariitalautakunta.fi", "oikeus.fi", "ara.fi", "hel.fi", "espoo.fi", "vantaa.fi"]
# S-Group rule (root AGENTS.md §7): grocery and everyday-product searches only use S-Group's own sites,
# and competitor grocery sites are never searched or cited.
S_GROUP_DOMAINS = ["s-kaupat.fi", "s-ryhma.fi", "alepa.fi", "sale.fi", "prisma.fi", "s-market.fi"]
COMPETITOR_GROCERY_DOMAINS = ["k-ruoka.fi", "kesko.fi", "k-citymarket.fi", "k-supermarket.fi", "k-market.fi",
                              "lidl.fi", "tokmanni.fi", "minimani.fi", "halpa-halli.fi", "wolt.com"]
CACHE_MAX_AGE_H = 24
TIMEOUT_S = 12

_client = None


def _exa():
    global _client
    if _client is None:
        from exa_py import Exa
        key = os.environ.get("EXA_API_KEY")
        if not key:
            raise RuntimeError("EXA_API_KEY is not set")
        _client = Exa(api_key=key)
    return _client


def _cache_path(key: dict):
    h = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:24]
    d = data_dir() / "cache" / "exa"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{h}.json"


def search(query: str, domains: list[str] | None = None, num_results: int = 5, search_type: str = "auto",
           highlights_chars: int = 1200, max_age_h: float = CACHE_MAX_AGE_H,
           exclude: list[str] | None = None) -> dict[str, Any]:
    """Returns {query, domains, results: [{title, url, published_date, highlights[]}], cached, seconds}.
    Errors come back as {"error": ...} with no results, never raised. Exa allows include OR exclude
    domains, so `exclude` only applies when `domains` is empty."""
    exclude = None if domains else exclude
    key = {"q": query.strip(), "d": sorted(domains or []), "n": num_results, "t": search_type, "h": highlights_chars}
    if exclude:
        key["x"] = sorted(exclude)
    path = _cache_path(key)
    if path.exists() and (time.time() - path.stat().st_mtime) < max_age_h * 3600:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {**data, "cached": True, "seconds": 0.0}
    t0 = time.monotonic()
    try:
        resp = _exa().search(
            query.strip(), type=search_type, num_results=num_results, include_domains=domains or None,
            exclude_domains=exclude or None, user_location="FI", contents={"highlights": {"max_characters": highlights_chars}}, timeout=TIMEOUT_S)
    except Exception as e:
        key_s = os.environ.get("EXA_API_KEY") or ""
        msg = f"{type(e).__name__}: {str(e).replace(key_s, '<key>') if key_s else e}"[:300]
        log.warning("Exa search failed for %r: %s", query, msg)
        return {"query": query, "domains": domains or [], "results": [], "error": msg, "cached": False,
                "seconds": round(time.monotonic() - t0, 2)}
    results = [{"title": (r.title or r.url or "").strip(), "url": r.url, "published_date": r.published_date,
                "highlights": [h.strip() for h in (r.highlights or []) if h and h.strip()]}
               for r in resp.results if getattr(r, "url", None)]
    data = {"query": query, "domains": domains or [], "results": results}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return {**data, "cached": False, "seconds": round(time.monotonic() - t0, 2)}


def search_many(queries: list[dict]) -> list[dict]:
    """Run several searches in parallel. Each item: {query, domains?, exclude?}."""
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(queries)))) as ex:
        return list(ex.map(lambda q: search(q["query"], q.get("domains"), exclude=q.get("exclude")), queries))

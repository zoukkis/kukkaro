"""Public-zone research worker (root AGENTS.md §4): Exa + Gemini, no customer data.

`research(question)` takes ONE anonymised question that has already passed the privacy gateway
(`kukkaro.coach.privacy`), and returns `{facts: [{text, sources: [n]}], sources: [{n, title, url}]}`.

1. Plan 1-3 Exa searches from the question alone (Gemini, JSON) and classify it: official topic,
   market price (electricity, phone...) or grocery/everyday product.
2. Search: official topics use official Finnish domains; grocery questions use S-Group domains only
   (S-Group rule); market questions exclude competitor grocery sites.
3. Gemini writes short facts ONLY from the retrieved pages, each citing its source numbers.

Code guards: facts must cite real sources; for grocery questions, sources on competitor domains and
facts naming competitor chains are dropped. Results are cached on disk per question (24 h).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date
from typing import Any

from kukkaro.butler import exa_client
from kukkaro.coach import llm
from kukkaro.coach.prompts import S_GROUP_RULE

MAX_SOURCES = 8
TEXT_CHARS_PER_SOURCE = 900
CACHE_MAX_AGE_H = 24
PROVIDER = "gemini"  # the public zone's model; it only ever sees the anonymised question and web pages

_GROCERY = re.compile(
    r"\b(grocer\w*|supermarket|food|milk|oat|bread|cheese|eggs?|coffee|snacks?|candy|meat|vegetables?|fruit|"
    r"store[- ]brand|shopping|shop|product|ruoka\w*|maito\w*|kauppa\w*|kaupa\w*|leipä\w*|ostos\w*|tuote\w*|"
    r"diapers?|detergent|shampoo|toilet paper)\b", re.IGNORECASE)
_COMPETITORS = re.compile(r"\b(K[- ]?(?:market|citymarket|supermarket|ruoka|kauppa|rauta)|Kesko|Lidl|Tokmanni|"
                          r"Minimani|Halpa-?Halli|Wolt Market)\b", re.IGNORECASE)


def is_grocery(question: str) -> bool:
    return bool(_GROCERY.search(question or ""))


def competitor_mentions(text: str) -> list[str]:
    return sorted({m.group(0) for m in _COMPETITORS.finditer(text or "")})


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return (m.group(1).lower() if m else "").removeprefix("www.")


def _is_competitor_url(url: str) -> bool:
    d = _domain(url)
    return any(d == c or d.endswith("." + c) for c in exa_client.COMPETITOR_GROCERY_DOMAINS)


PLAN_SYSTEM = """You plan web searches for a research worker in a Finnish banking app. You receive one general \
question (no personal data). Classify it and plan 1 to 3 short search queries that find current, specific facts.
- kind "official": benefits, laws, rent rules, taxes, consumer rights, debt advice (Kela, Finlex, KKV, suomi.fi, \
Energiavirasto). Use Finnish queries, plus English if useful.
- kind "grocery": where to buy groceries or everyday products, product prices. Search S-Group's shops only \
(S-kaupat, S-market, Prisma, Alepa, Sale); Finnish queries work best on s-kaupat.fi.
- kind "market": other market prices and offers, e.g. electricity or phone contracts, where comparison sites help."""

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["official", "grocery", "market"]},
        "searches": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string"}},
    },
    "required": ["kind", "searches"],
}

FACTS_SYSTEM = f"""You are a research worker. You receive a general question and numbered web sources. \
Write 2 to 6 short facts that help answer the question, using ONLY the sources. Every fact lists the numbers \
of the sources it comes from. Copy numbers exactly as the sources give them (with their units and dates); do not \
calculate. If the sources do not answer the question, return no facts. You know nothing about the person asking.
{S_GROUP_RULE}"""

FACTS_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {"type": "array", "maxItems": 6, "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "sources": {"type": "array", "items": {"type": "integer"}}},
            "required": ["text", "sources"]}},
    },
    "required": ["facts"],
}


def _cache_path(question: str):
    from kukkaro.data.settings import data_dir
    d = data_dir() / "cache" / "research"
    d.mkdir(parents=True, exist_ok=True)
    key = " ".join(question.lower().split())
    return d / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.json"


def _numbered_sources(results: list[dict], grocery: bool) -> list[dict]:
    seen, out = set(), []
    for res in results:
        for r in res.get("results", []):
            if r["url"] in seen or not r.get("highlights") or (grocery and _is_competitor_url(r["url"])):
                continue
            seen.add(r["url"])
            out.append({"n": len(out) + 1, "title": r["title"], "url": r["url"], "published_date": r.get("published_date"),
                        "text": " … ".join(r["highlights"])[:TEXT_CHARS_PER_SOURCE]})
            if len(out) >= MAX_SOURCES:
                return out
    return out


def research(question: str, use_cache: bool = True) -> dict[str, Any]:
    """Facts with sources for one anonymised question. Never raises; failures come back with `error`.
    The returned sources carry `text` (the page highlights) for the caller's guards; `public_view()`
    strips it for the model and the API."""
    t0 = time.monotonic()
    q = " ".join(str(question).split())
    path = _cache_path(q)
    if use_cache and path.exists() and time.time() - path.stat().st_mtime < CACHE_MAX_AGE_H * 3600:
        return {**json.loads(path.read_text(encoding="utf-8")), "cached": True, "seconds": round(time.monotonic() - t0, 2)}

    today = date.today().isoformat()  # web facts are about the real present, not the dataset's last date
    plan, plan_run = llm.complete_json(PLAN_SYSTEM, f"Today is {today}.\nQuestion: {q}", PLAN_SCHEMA, PROVIDER)
    kind = (plan or {}).get("kind") or "market"
    grocery = kind == "grocery" or is_grocery(q)  # the code decides too: a grocery question never leaves S-Group
    kind = "grocery" if grocery else kind
    domains = (exa_client.S_GROUP_DOMAINS if grocery else exa_client.OFFICIAL_DOMAINS if kind == "official" else None)
    exclude = None if domains else exa_client.COMPETITOR_GROCERY_DOMAINS
    queries = [{"query": s, "domains": domains, "exclude": exclude} for s in ((plan or {}).get("searches") or [q])[:3]]
    results = exa_client.search_many(queries)
    sources = _numbered_sources(results, grocery)
    base = {"question": q, "kind": kind, "searches": [{"query": r["query"], "domains": r.get("domains") or [],
                                                       "results": len(r.get("results", [])), "error": r.get("error")}
                                                      for r in results]}
    if not sources:
        return {**base, "facts": [], "sources": [], "model": plan_run.model, "cached": False,
                "seconds": round(time.monotonic() - t0, 2), "error": "no sources"}

    src_block = "\n\n".join(f"[{s['n']}] {s['title']} ({s['url']}, published {s['published_date'] or 'unknown'})\n{s['text']}"
                            for s in sources)
    out, run = llm.complete_json(FACTS_SYSTEM, f"Today is {today}.\nQuestion: {q}\n\nSources:\n{src_block}",
                                 FACTS_SCHEMA, PROVIDER)
    valid = {s["n"] for s in sources}
    facts = []
    for f in (out or {}).get("facts") or []:
        cites = sorted({int(n) for n in f.get("sources") or [] if int(n) in valid})
        text = llm.plain(str(f.get("text") or ""))
        if not cites or not text or (grocery and competitor_mentions(text)):
            continue
        facts.append({"text": text, "sources": cites})
    cited = {n for f in facts for n in f["sources"]}
    result = {**base, "facts": facts, "sources": [s for s in sources if s["n"] in cited] if facts else sources,
              "model": run.model, "cached": False, "seconds": round(time.monotonic() - t0, 2),
              "error": None if facts else (run.error or "no facts in the sources")}
    if facts:
        path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def public_view(r: dict[str, Any]) -> dict[str, Any]:
    """What goes back to the trusted zone (Gemma) and the UI: facts and sources, no page text."""
    return {"question_sent": r.get("question"), "kind": r.get("kind"), "facts": r.get("facts") or [],
            "sources": [{k: s.get(k) for k in ("n", "title", "url", "published_date")} for s in r.get("sources") or []],
            "error": r.get("error")}

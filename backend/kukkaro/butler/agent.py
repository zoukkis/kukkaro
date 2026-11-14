"""Kukkaro Butler: finds money the user is missing on the live web (Exa), always with sources.

`run(customer_id, task)` does four steps:
1. Context from DATA tools only (age, postal code, rent, utility bills and their change, salary).
2. Plan 1-4 Exa searches (Gemini, JSON), official Finnish sites first.
3. Run them in parallel (cached on disk) and number the sources.
4. Answer from the sources only (Gemini, JSON): every claim cites [n]; next steps; and a ready-to-send
   draft (email or form prep) that the user reviews and sends from their own app. The Butler never
   sends or submits anything, and never says someone "is eligible".

Code-level guards: citations must point at real sources, a draft's `to` address must appear in a
source, and numbers in the answer must come from the user's data or the sources (else listed in
`unverified_numbers`).
"""
from __future__ import annotations

import re
import time
from datetime import date
from typing import Any

from kukkaro.butler import exa_client
from kukkaro.coach import llm, numbers
from kukkaro.data import metrics

MAX_SOURCES = 8
HIGHLIGHT_CHARS_PER_SOURCE = 900


def user_context(customer_id: str) -> dict[str, Any]:
    """The user's situation, from DATA tools only (no names exist in the data)."""
    p = metrics.customer_profile(customer_id)
    r = metrics.recurring_payments(customer_id)
    streams = {s["category"]: s for s in r["recurring"] if not s["name"].startswith(s["category"] + " merchant")}
    housing, utilities = streams.get("Housing"), streams.get("Utilities")
    return {
        "age": p["age"], "age_band": p["age_band"], "postal_code": p["postal_code"],
        "data_period": r["period"],
        "rent_typical_monthly_eur": housing["typical_monthly_eur"] if housing else None,
        "rent_latest_month_eur": housing["latest_month_eur"] if housing else None,
        "utility_bills_typical_monthly_eur": utilities["typical_monthly_eur"] if utilities else None,
        "utility_bills_latest_month_eur": utilities["latest_month_eur"] if utilities else None,
        "utility_bills_change_pct": utilities["change_pct"] if utilities else None,
        "latest_month": utilities["latest_month"] if utilities else None,
        "salary_average_monthly_eur": r["salary"]["average_monthly_eur"],
        "salary_last_eur": r["salary"]["last_eur"],
        "other_income_6_months_eur": r["other_income"]["total_eur"],
        "notes": "Bank data only. Utility bills have no merchant, so electricity, water and internet cannot be told apart.",
    }


PLAN_SYSTEM = """You plan web searches for Kukkaro Butler, an assistant inside a Finnish banking app that finds \
money people are missing: benefits, fair prices and their consumer rights. The user lives in Finland. \
Plan 1 to 4 short search queries that will find current, specific information for the task. Use Finnish \
for official Finnish topics (benefits, housing, taxes, consumer rights) and add an English query if useful. \
Set official_only=true for benefits, laws, taxes and rights (Kela, Vero, KKV, Finlex, suomi.fi); set it false \
for market prices and offers (e.g. electricity contracts), where comparison and seller sites are needed."""

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "searches": {"type": "array", "minItems": 1, "maxItems": 4, "items": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "official_only": {"type": "boolean"}},
            "required": ["query", "official_only"]}},
    },
    "required": ["searches"],
}

ANSWER_SYSTEM = """You are Kukkaro Butler inside the S-mobiili banking app. You do the digging; the user decides.
Rules:
1. Use ONLY the numbered sources and the user's bank data given to you. Put [n] after every claim taken from \
source n. If the sources do not answer something, or disagree, say so plainly.
2. Never say the user "is eligible" or "qualifies". Say "you may be eligible" and explain how to check, \
with the official page. When a source gives a limit or a price, say plainly where the user's own figure falls \
(above, below, close to it) without calculating new numbers, e.g. "your average salary in your bank data \
(X €) is above the Y € limit for one adult [n]", with X from the bank data and Y from the source.
3. Numbers: only numbers that appear in the sources or in the user's bank data. Do not calculate.
4. Keep "answer" under 150 words, friendly and concrete. Say that figures about the user come from their bank data.
5. "next_steps": 2 to 5 short, concrete steps the user can take.
6. "draft": write the one thing that gets this done, ready to send, so the user only has to review and send it \
from their own email or the official service: an email (to a landlord, an energy company, a seller) or, for a \
benefit application, kind "form_prep": a short list of what the application asks for, filled in with the user's \
own figures. Write the draft in Finnish if the recipient is Finnish, followed by an English translation. \
For price questions (electricity, phone, insurance), use kind "form_prep": a ready switching checklist \
(what to look up on the current bill, the offers to compare with their prices and sources, how to switch) and \
set source_n to the best comparison or offer page. Put "to" ONLY if that exact email address appears in a source; \
otherwise leave it empty. Use placeholders like [your name] and [address] for details the bank data does not have. \
Set source_n to the source with the official page, form or offer. Use kind "none" only for a pure information \
question where nothing can be prepared.
7. You are not a lawyer or a licensed financial advisor; never recommend loans, investments or specific \
financial products."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "next_steps": {"type": "array", "items": {"type": "string"}},
        "draft": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["email", "form_prep", "none"]},
            "to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"},
            "source_n": {"type": "integer"}},
            "required": ["kind", "subject", "body"]},
    },
    "required": ["answer", "next_steps", "draft"],
}

_ELIGIBLE = re.compile(r"\b(you|you're|you are)\s+(are\s+)?(eligible|entitled|qualif(y|ied))\b", re.IGNORECASE)
_CITE = re.compile(r"\[(\d+)\]")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _soften_eligibility(text: str) -> str:
    def repl(m: re.Match) -> str:
        word = m.group(3).lower()
        word = "eligible" if word.startswith("qualif") else word
        out = f"you may be {word}"
        return out[0].upper() + out[1:] if m.group(0)[0].isupper() else out
    return _ELIGIBLE.sub(repl, text)


def _sources(results: list[dict]) -> list[dict]:
    seen, out = set(), []
    for res in results:
        for r in res.get("results", []):
            if r["url"] in seen or not r.get("highlights"):
                continue
            seen.add(r["url"])
            out.append({"n": len(out) + 1, "title": r["title"], "url": r["url"], "published_date": r.get("published_date"),
                        "text": " … ".join(r["highlights"])[:HIGHLIGHT_CHARS_PER_SOURCE]})
            if len(out) >= MAX_SOURCES:
                return out
    return out


def run(customer_id: str, task: str, provider: str | None = "gemini") -> dict[str, Any]:
    t0 = time.monotonic()
    ctx = user_context(customer_id)  # raises UnknownCustomer -> 404
    today = date.today().isoformat()  # web facts are about the real present, not the dataset's last date

    plan, plan_run = llm.complete_json(PLAN_SYSTEM, f"Today is {today}.\nTask: {task}\nUser context: {llm.dumps(ctx)}",
                                       PLAN_SCHEMA, provider)
    searches = (plan or {}).get("searches") or [{"query": task, "official_only": False}]
    queries = [{"query": s["query"], "domains": exa_client.OFFICIAL_DOMAINS if s.get("official_only") else None}
               for s in searches[:4]]
    t_search = time.monotonic()
    results = exa_client.search_many(queries)
    search_s = round(time.monotonic() - t_search, 2)
    sources = _sources(results)

    base = {"customer_id": customer_id, "task": task, "context": ctx,
            "searches": [{"query": r["query"], "official_only": bool(r["domains"]), "cached": r.get("cached", False),
                          "results": len(r.get("results", [])), "error": r.get("error")} for r in results]}
    if not sources:
        return {**base, "answer": "I couldn't find reliable sources for this right now, so I won't guess. Please try "
                "again in a moment or rephrase the question.", "sources": [], "next_steps": [], "draft": None,
                "unverified_numbers": [], "model": plan_run.model, "seconds": round(time.monotonic() - t0, 2),
                "error": "no sources"}

    src_block = "\n\n".join(f"[{s['n']}] {s['title']} ({s['url']}, published {s['published_date'] or 'unknown'})\n{s['text']}"
                            for s in sources)
    prompt = (f"Today is {today}.\nTask from the user: {task}\n\nThe user's bank data (from Kukkaro's tools):\n"
              f"{llm.dumps(ctx)}\n\nSources:\n{src_block}")
    out, ans_run = llm.complete_json(ANSWER_SYSTEM, prompt, ANSWER_SCHEMA, provider)
    if not out:
        return {**base, "answer": llm.FALLBACK_TEXT, "sources": [{k: s[k] for k in ("n", "title", "url", "published_date")}
                for s in sources], "next_steps": [], "draft": None, "unverified_numbers": [], "model": ans_run.model,
                "seconds": round(time.monotonic() - t0, 2), "error": ans_run.error}

    valid = {s["n"] for s in sources}
    answer = _soften_eligibility(_CITE.sub(lambda m: m.group(0) if int(m.group(1)) in valid else "", out["answer"])).strip()
    cited = {int(n) for n in _CITE.findall(answer)}
    all_text = " ".join(s["text"] + " " + s["url"] for s in sources)

    draft = out.get("draft") or {}
    if draft.get("kind") in (None, "none") or not draft.get("body"):
        draft = None
    else:
        to = (draft.get("to") or "").strip()
        if to and (not _EMAIL.fullmatch(to) or to.lower() not in all_text.lower()):
            to = ""  # never invent an address
        src = next((s for s in sources if s["n"] == draft.get("source_n")), None) or \
            next((s for s in sources if any(d in s["url"] for d in exa_client.OFFICIAL_DOMAINS)), None)
        body = _soften_eligibility(draft["body"])
        draft = {"kind": draft["kind"], "to": to or None, "subject": draft.get("subject", ""), "body": body,
                 "open_url": src["url"] if src else None, "source_url": src["url"] if src else None,
                 "mailto": None}
        if draft["kind"] == "email":
            from urllib.parse import quote
            draft["mailto"] = f"mailto:{quote(to)}?subject={quote(draft['subject'])}&body={quote(body)}"

    checked_text = answer + " " + " ".join(out.get("next_steps") or []) + " " + (draft["body"] if draft else "")
    checked_text = re.sub(r"\[\d+(?:\s*[,\]\[]\s*\d+)*\]", " ", checked_text)  # citation markers are not figures
    unverified = numbers.unverified_numbers(checked_text, [{"name": "context", "args": {}, "result": ctx}],
                                            all_text + " " + today)
    return {
        **base,
        "answer": answer,
        "sources": [{"n": s["n"], "title": s["title"], "url": s["url"], "published_date": s["published_date"],
                     "cited": s["n"] in cited} for s in sources],
        "next_steps": [_soften_eligibility(x) for x in (out.get("next_steps") or [])][:5],
        "draft": draft,
        "unverified_numbers": unverified,
        "model": ans_run.model,
        "seconds": round(time.monotonic() - t0, 2),
        "timing": {"plan_s": plan_run.seconds, "search_s": search_s, "answer_s": ans_run.seconds},
        "error": None,
    }

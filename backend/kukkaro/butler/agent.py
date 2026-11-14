"""Kukkaro Butler: finds money the user is missing on the live web (Exa), always with sources.

Privacy design (root AGENTS.md §4): the Butler crosses both zones through the privacy gateway.
1. Trusted zone: the user's situation from DATA tools only (age, postal code, rent, bills, salary).
2. Gateway (coach/privacy.py): the task is checked in code and sent on as ONE anonymised question with
   banded context ("Espoo region, age 20–25"); a leaking task is rewritten once by Gemma, else refused.
3. Public zone (butler/research.py): Exa + Gemini find facts with sources from that question only.
4. Trusted zone: Gemma (Gemini as backup) combines the facts with the user's own figures: every claim
   cites [n]; next steps; and a ready-to-send draft (email or form prep) that the user reviews and sends
   from their own app. The Butler never sends or submits anything, and never says someone "is eligible".

Code-level guards: citations must point at real sources, a draft's `to` address must appear in a
source, and numbers in the answer must come from the user's data or the sources (else listed in
`unverified_numbers`).
"""
from __future__ import annotations

import re
import time
from datetime import date
from typing import Any

from kukkaro.butler import exa_client, research
from kukkaro.coach import llm, numbers, privacy
from kukkaro.coach.prompts import S_GROUP_RULE
from kukkaro.data import metrics

TRUSTED_PROVIDER = "gemma"    # sees the customer's data (root AGENTS.md §4)
FALLBACK_PROVIDER = "gemini"  # backup for the trusted step, only if Gemma fails



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


ANSWER_SYSTEM = """You are Kukkaro Butler inside the S-mobiili banking app. You do the digging; the user decides.
Rules:
1. Use ONLY the numbered sources and the user's bank data given to you. Put [n] after every claim taken from \
source n. Prefer official sources (kela.fi, kkv.fi, finlex.fi, vero.fi, suomi.fi, energiavirasto.fi) whenever \
they cover the point. If the sources do not answer something, or disagree, say so plainly.
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
For tax and benefit questions, "form_prep" is the checklist for the official e-service (OmaVero, OmaKela): \
what to enter, where, and with which of the user's figures. Set source_n to the source with the official page, \
form or offer. Use kind "none" only if truly nothing can be prepared.
7. You are not a lawyer or a licensed financial advisor; never recommend loans, investments or specific \
financial products."""
ANSWER_SYSTEM += "\n8. " + S_GROUP_RULE

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


SUGGESTION_THRESHOLD_PCT = 25
_SUGGESTION_TASKS = {
    # Bills have no merchant in the data, so say "utility bills", never "electricity".
    "Utilities": ("utility bills", "My utility bills went up a lot last month. Why might that be, and how can I pay less?"),
    "Housing": ("rent", "My rent went up. Is that allowed, and what can I do?"),
}


def suggestions(customer_id: str, threshold_pct: float = SUGGESTION_THRESHOLD_PCT) -> dict[str, Any]:
    """Proactive Butler cards: recurring bills whose latest complete month rose at least
    `threshold_pct` above their typical month (Revolut explains price moves in your stocks; Kukkaro
    explains the ones in your bills). Numbers come from DATA's recurring_payments; each card carries
    the task to send to the Butler if the user taps it."""
    r = metrics.recurring_payments(customer_id)
    cards = []
    for s in r["recurring"]:
        if s["category"] not in _SUGGESTION_TASKS or s["change_pct"] is None or s["change_pct"] < threshold_pct:
            continue
        what, task = _SUGGESTION_TASKS[s["category"]]
        cards.append({"kind": "bill_went_up", "category": s["category"], "what": what,
                      "title": f"Your {what} went up", "latest_month": s["latest_month"],
                      "latest_month_eur": s["latest_month_eur"], "typical_monthly_eur": s["typical_monthly_eur"],
                      "change_pct": s["change_pct"], "task": task,
                      "source": f"your bank data, {s['latest_month']} vs the 3 months before"})
    cards.sort(key=lambda c: c["change_pct"], reverse=True)
    return {"customer_id": customer_id, "threshold_pct": threshold_pct, "suggestions": cards}


ANSWER_CACHE_MAX_AGE_H = 24


def _answer_cache_path(customer_id: str, task: str):
    import hashlib
    from kukkaro.data.settings import data_dir
    key = f"{customer_id}|{' '.join(task.lower().split())}"
    d = data_dir() / "cache" / "butler"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.json"


def run(customer_id: str, task: str, use_cache: bool = True) -> dict[str, Any]:
    """The Butler answer. The same task for the same customer within 24 h comes back from the disk
    cache (`cached: true`, under a second), so the recorded demo is repeatable; new tasks go live."""
    import json
    t0 = time.monotonic()
    metrics.customer_profile(customer_id)  # raises UnknownCustomer -> 404 before any cache or web call
    path = _answer_cache_path(customer_id, task)
    if use_cache and path.exists() and time.time() - path.stat().st_mtime < ANSWER_CACHE_MAX_AGE_H * 3600:
        out = json.loads(path.read_text(encoding="utf-8"))
        return {**out, "cached": True, "seconds": round(time.monotonic() - t0, 2)}
    out = _run_live(customer_id, task, t0, use_cache)
    if not out.get("error"):  # never cache a failure
        path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return {**out, "cached": False}


ANON_SYSTEM = """Rewrite the user's request as ONE general web-search question that contains no personal details: \
no names, IDs, emails, phone numbers, addresses, postal codes, exact ages or exact euro amounts. Keep the topic. \
Round any amount to tens ("around 140 €") and use an age band ("age 20–25") or a region instead."""
ANON_SCHEMA = {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}


def anonymised_question(task: str, ctx: dict[str, Any]) -> tuple[str | None, list[str]]:
    """The privacy gateway for the Butler: the user's task, checked in code (coach/privacy.py) before it
    leaves the trusted zone, plus banded context. If the task leaks something, the trusted-zone model
    (Gemma) rewrites it once; if that still leaks, nothing is sent. Returns (question or None, problems)."""
    v = privacy.check(task, [ctx])
    if not v.ok:
        out, _ = llm.complete_json(ANON_SYSTEM, task, ANON_SCHEMA, TRUSTED_PROVIDER)
        v2 = privacy.check((out or {}).get("question", ""), [ctx])
        if not v2.ok:
            return None, v.problems
        v = v2
    with_ctx = privacy.check(f"{v.question} ({privacy.banded_context(ctx)})", [ctx])
    return (with_ctx.question if with_ctx.ok else v.question), []


def _run_live(customer_id: str, task: str, t0: float, use_cache: bool = True) -> dict[str, Any]:
    ctx = user_context(customer_id)                       # trusted zone: the customer's own data
    today = date.today().isoformat()                      # web facts are about the real present
    question, blocked = anonymised_question(task, ctx)    # privacy gateway
    base = {"customer_id": customer_id, "task": task, "context": ctx, "zones": ["trusted"], "fallback": False,
            "research": {"question_sent": question, "blocked": blocked}}
    if question is None:
        return {**base, "answer": privacy.REFUSAL_TEXT, "sources": [], "next_steps": [], "draft": None,
                "unverified_numbers": [], "model": None, "seconds": round(time.monotonic() - t0, 2), "error": "blocked"}

    found = research.research(question, use_cache=use_cache)   # public zone: Exa + Gemini, question only
    sources = found["sources"]
    base.update(zones=["trusted", "public"], searches=found.get("searches", []),
                research={"question_sent": question, "blocked": [], "kind": found.get("kind"), "facts": found["facts"]})
    if not sources:
        return {**base, "answer": "I couldn't find reliable sources for this right now, so I won't guess. Please try "
                "again in a moment or rephrase the question.", "sources": [], "next_steps": [], "draft": None,
                "unverified_numbers": [], "model": found.get("model"), "seconds": round(time.monotonic() - t0, 2),
                "error": "no sources"}

    facts = "\n".join("- " + f["text"] + " " + "".join(f"[{n}]" for n in f["sources"]) for f in found["facts"]) or "(none)"
    src_block = "\n\n".join(f"[{s['n']}] {s['title']} ({s['url']}, published {s['published_date'] or 'unknown'})\n{s['text']}"
                            for s in sources)
    prompt = (f"Today is {today}.\nTask from the user: {task}\n\nThe user's bank data (from Kukkaro's tools):\n"
              f"{llm.dumps(ctx)}\n\nFacts found by the research service:\n{facts}\n\nSources:\n{src_block}")
    # Trusted zone again: Gemma combines the public facts with the customer's own figures; Gemini is the backup.
    out, ans_run = llm.complete_json(ANSWER_SYSTEM, prompt, ANSWER_SCHEMA, TRUSTED_PROVIDER, FALLBACK_PROVIDER)
    base["fallback"] = ans_run.fallback_used
    if not out:
        return {**base, "answer": llm.FALLBACK_TEXT, "sources": [{k: s[k] for k in ("n", "title", "url", "published_date")}
                for s in sources], "next_steps": [], "draft": None, "unverified_numbers": [], "model": ans_run.model,
                "seconds": round(time.monotonic() - t0, 2), "error": ans_run.error}

    valid = {s["n"] for s in sources}
    answer = llm.plain(_soften_eligibility(_CITE.sub(lambda m: m.group(0) if int(m.group(1)) in valid else "",
                                                     str(out.get("answer") or ""))))
    cited = {int(n) for n in _CITE.findall(answer)}
    all_text = " ".join(s["text"] + " " + s["url"] for s in sources) + " " + facts

    draft = out.get("draft") if isinstance(out.get("draft"), dict) else {}
    if not isinstance(out.get("next_steps"), list):
        out["next_steps"] = []
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
                                            all_text + " " + today + " " + task)  # the user's own numbers count
    return {
        **base,
        "answer": answer,
        "sources": [{"n": s["n"], "title": s["title"], "url": s["url"], "published_date": s["published_date"],
                     "cited": s["n"] in cited} for s in sources],
        "next_steps": [llm.plain(_soften_eligibility(str(x))) for x in (out.get("next_steps") or [])][:5],
        "draft": draft,
        "unverified_numbers": unverified,
        "model": ans_run.model,
        "host": ans_run.host,
        "seconds": round(time.monotonic() - t0, 2),
        "timing": {"research_s": found.get("seconds"), "answer_s": ans_run.seconds},
        "error": None,
    }

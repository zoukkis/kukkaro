"""Coach eval: 15 fixed questions for the demo customer, checked automatically.

Usage (from backend/):  python -m kukkaro.coach.eval              # the privacy design: Gemma, Gemini as backup
                        python -m kukkaro.coach.eval --provider gemini   # one model only, no fallback
Writes a JSON report to data/cache/eval/ (gitignored) and prints a summary line for docs/DECISIONS.md.

A question passes when:
- the coach answered (no LLM error),
- every number in the answer appears in the tool outputs (coach/numbers.py, the same check the API uses),
- it called one of the expected tools (or no tool, for questions the data cannot answer),
- it names no other grocery chain (S-Group rule).
The report counts how many turns Gemma (trusted zone) answered and how many fell back to Gemini.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import datetime

from kukkaro.data import metrics
from kukkaro.data.settings import data_dir

NONE: frozenset[str] = frozenset()  # must not use any tool
ANY = None                           # any tools or none; only the number check applies
# (question, tools: the answer must use at least one of these | NONE | ANY)
QUESTIONS: list[tuple[str, frozenset[str] | None]] = [
    # S-Bank's brief, verbatim
    ("Where did my money go?", frozenset({"spending_summary"})),
    ("What kind of spender am I?", frozenset({"spender_profile"})),
    ("What can I safely spend this week?", frozenset({"safe_to_spend"})),
    ("How could I save more?", frozenset({"what_if", "spender_profile", "spending_summary"})),
    # Everyday questions
    ("How much did I spend on taxis last month?", frozenset({"category_spend"})),
    ("What if I halve my restaurant spending?", frozenset({"what_if"})),
    ("How much did I spend on groceries in September 2026?", frozenset({"category_spend", "spending_summary"})),
    ("Compare my everyday spending in August and September.", frozenset({"spending_summary"})),
    ("Did any of my bills go up recently?", frozenset({"recurring_payments"})),
    ("How much is my rent?", frozenset({"recurring_payments", "category_spend", "spending_summary"})),
    ("What if I spent 20% less on entertainment?", frozenset({"what_if"})),
    ("How much did I spend on fast food in the last three months?", frozenset({"category_spend"})),
    ("What were my unexpected necessities this month?", frozenset({"spending_summary", "category_spend"})),
    # Receipts (synthetic) and one the data cannot answer (the coach must say so, not invent numbers)
    ("How much would halving energy drinks save me?", frozenset({"item_what_if", "item_spend", "leak_items"})),  # receipts
    # Privacy design: outside facts through the gateway (research_web), combined with the user's own numbers
    ("Am I overpaying for electricity?", frozenset({"research_web"})),
    ("Where can I buy cheap oat milk?", frozenset({"research_web"})),
    ("What's my credit score?", NONE),
]


def check(question: str, expected: frozenset[str] | None, out: dict) -> dict:
    from kukkaro.butler.research import competitor_mentions
    used = {c["name"] for c in out["tool_calls"]}
    if out.get("error"):
        reason = "error"
    elif competitor_mentions(out["answer"]):
        reason = f"names {competitor_mentions(out['answer'])}"
    elif out["unverified_numbers"]:
        reason = f"unverified numbers {out['unverified_numbers']}"
    elif expected is not None and not expected and used:
        reason = f"used tools {sorted(used)} for a question the data cannot answer"
    elif expected and not (used & expected):
        reason = f"expected one of {sorted(expected)}, used {sorted(used) or 'none'}"
    else:
        reason = ""
    return {"question": question, "pass": not reason, "reason": reason, "tools": sorted(used),
            "seconds": out["seconds"], "model": out["model"], "host": out["host"], "answer": out["answer"],
            "fallback": out.get("fallback", False), "zones": out.get("zones"),
            "research": [x.get("question_sent") for x in out.get("research") or []],
            "unverified_numbers": out["unverified_numbers"]}


# Gemma on Google's API (stage 1) has a low per-minute quota (429s without a pause); Verda (stage 2) has none.
PAUSE_S = {"gemini": 0, "gemma": 0 if os.environ.get("GEMMA_BASE_URL") else 8}
PAUSE_S["privacy"] = PAUSE_S["gemma"]


def run_eval(provider: str, customer_id: str, pause_s: float | None = None) -> dict:
    from kukkaro.coach.router import answer
    pause = PAUSE_S.get(provider, 0) if pause_s is None else pause_s
    rows = []
    for i, (q, expected) in enumerate(QUESTIONS):
        if i and pause:
            time.sleep(pause)
        out = (answer(customer_id, q, []) if provider == "privacy"
               else answer(customer_id, q, [], trusted=provider, fallback=None))
        rows.append({**check(q, expected, out), "error": out.get("error"), "number_check": out.get("number_check")})
        r = rows[-1]
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['seconds']:>5.1f}s {'↩ ' if r['fallback'] else ''}{q}"
              + (f"  -> {r['reason']}" if r["reason"] else ""))
    answered = [r for r in rows if not r["error"]]
    secs = [r["seconds"] for r in answered] or [0.0]
    return {"provider": provider, "model": rows[0]["model"], "host": rows[0]["host"], "customer_id": customer_id,
            "passed": sum(r["pass"] for r in rows), "total": len(rows),
            "answered": len(answered), "passed_of_answered": sum(r["pass"] for r in answered),
            "errors": [r["error"][:80] for r in rows if r["error"]],
            "retried": sum(r.get("number_check") == "retried" for r in rows),
            "withheld": sum(r.get("number_check") == "withheld" for r in rows),
            "fallback": sum(bool(r.get("fallback")) for r in rows),
            "fallback_rate_pct": round(100 * sum(bool(r.get("fallback")) for r in rows) / len(rows), 1),
            "research_turns": sum(1 for r in rows if r.get("research")),
            "median_s": round(statistics.median(secs), 1), "max_s": round(max(secs), 1), "rows": rows}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--provider", choices=["privacy", "gemini", "gemma", "both"], default="privacy",
                   help="privacy = Gemma with Gemini as backup (the app); gemini/gemma = one model, no fallback")
    p.add_argument("--customer", default=os.environ.get("DEMO_CUSTOMER_ID") or "CUST02979")
    a = p.parse_args()
    metrics.warm_up(a.customer)
    reports = []
    for prov in (["gemini", "gemma"] if a.provider == "both" else [a.provider]):
        print(f"\n== {prov}")
        t = time.time()
        reports.append(run_eval(prov, a.customer))
        print(f"   {reports[-1]['passed']}/{reports[-1]['total']} passed in {time.time() - t:.0f}s")
    out_dir = data_dir() / "cache" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"eval_{datetime.now():%Y%m%d_%H%M}.json"
    path.write_text(json.dumps(reports, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nReport: {path}")
    for r in reports:
        print(f"DECISIONS: eval {r['provider']} ({r['model']}, {r['host']}) on {r['customer_id']}: "
              f"{r['passed']}/{r['total']} pass; {r['passed_of_answered']}/{r['answered']} of answered; "
              f"{len(r['errors'])} errors; number check retried {r['retried']}, withheld {r['withheld']}; "
              f"fallback to Gemini {r['fallback']}/{r['total']} ({r['fallback_rate_pct']}%); "
              f"median {r['median_s']} s, max {r['max_s']} s (answered only)")


if __name__ == "__main__":
    main()

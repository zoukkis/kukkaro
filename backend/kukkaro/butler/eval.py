"""Butler eval: the 3 demo tasks plus 10 phrasings the agent was not tuned on, run live.

Usage (from backend/):  python -m kukkaro.butler.eval [--cached]
A task passes when the Butler answered (no error), cites at least one source, every number it uses is
in the user's data or the sources, it never says "you are eligible", and it prepared a draft.
`--cached` reruns from the answer cache to prove repeat demo queries are fast (< 2 s).
Writes data/cache/eval/butler_*.json (gitignored) and prints a line for docs/DECISIONS.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
from datetime import datetime

from kukkaro.data import metrics
from kukkaro.data.settings import data_dir

DEMO = [
    "Am I possibly eligible for Kela housing allowance?",
    "My rent went up. Is that allowed, and what can I do?",
    "Am I overpaying for electricity?",
]
UNSEEN = [
    "Can Kela help me pay my rent?",
    "Voinko saada asumistukea?",
    "My landlord wants 50 euros more per month from January. Can he do that?",
    "Is my electricity contract too expensive?",
    "How do I switch electricity company in Finland?",
    "My utility bill doubled last month. Why, and what can I do?",
    "What tax deductions could I claim as a young worker in Finland?",
    "Am I paying too much for my phone plan?",
    "Can I get my rental deposit back when I move out?",
    "Are there benefits for young people with a low income in Espoo?",
]


def check(task: str, r: dict) -> dict:
    cited = [s for s in r.get("sources", []) if s.get("cited")]
    text = " ".join([r.get("answer", "")] + r.get("next_steps", []) + [(r.get("draft") or {}).get("body", "")])
    if r.get("error"):
        reason = f"error: {r['error'][:80]}"
    elif not cited:
        reason = "no cited source"
    elif r.get("unverified_numbers"):
        reason = f"unverified numbers {r['unverified_numbers']}"
    elif re.search(r"\byou are eligible\b|\byou qualify\b", text, re.IGNORECASE):
        reason = "says the user is eligible"
    elif not r.get("draft"):
        reason = "no draft"
    else:
        reason = ""
    return {"task": task, "pass": not reason, "reason": reason, "seconds": r.get("seconds"), "cached": r.get("cached"),
            "sources": len(r.get("sources", [])), "cited": len(cited), "draft_kind": (r.get("draft") or {}).get("kind"),
            "official": sum(1 for s in cited if any(d in s["url"] for d in ("kela.fi", "kkv.fi", "finlex.fi", "vero.fi", "suomi.fi", "energiavirasto.fi", "sahkonhinta.fi"))),
            "answer": r.get("answer")}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--customer", default=os.environ.get("DEMO_CUSTOMER_ID") or "CUST02979")
    p.add_argument("--cached", action="store_true", help="use the answer cache (repeat-demo speed check)")
    a = p.parse_args()
    from kukkaro.butler.agent import run
    metrics.warm_up()
    rows = []
    for group, tasks in (("demo", DEMO), ("unseen", UNSEEN)):
        for t in tasks:
            r = check(t, run(a.customer, t, use_cache=a.cached))
            r["group"] = group
            rows.append(r)
            print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['seconds']:>5.1f}s {group:6} cited={r['cited']} official={r['official']} "
                  f"draft={r['draft_kind']} {t}" + (f"  -> {r['reason']}" if r["reason"] else ""))
    secs = [r["seconds"] for r in rows]
    out_dir = data_dir() / "cache" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"butler_{'cached_' if a.cached else ''}{datetime.now():%Y%m%d_%H%M}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    demo = [r for r in rows if r["group"] == "demo"]
    unseen = [r for r in rows if r["group"] == "unseen"]
    print(f"\nReport: {path}")
    print(f"DECISIONS: butler eval{' (cached rerun)' if a.cached else ''} on {a.customer}: demo {sum(r['pass'] for r in demo)}/{len(demo)}, "
          f"unseen {sum(r['pass'] for r in unseen)}/{len(unseen)}; median {statistics.median(secs):.1f} s, max {max(secs):.1f} s")


if __name__ == "__main__":
    main()

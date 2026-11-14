"""Upcoming payments before payday (the Home "Coming up" card).

The S-Bank dataset has no e-invoices or due dates, so this is a forecast built from two existing
DATA functions, never from the LLM:
- `safe_to_spend` gives, per regular-essentials group, what is still expected before the next
  salary (typical month minus what was already paid since the last salary);
- `recurring_payments` gives when that bill was last paid and whether it rose (`change_pct`).

The expected date is "about one month after the last payment", only shown when it falls between
today and payday. In S-mobiili this would read the e-invoices the bank already receives
(docs/PRODUCTION_PATH.md), so dates and amounts would be exact.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from kukkaro.data import metrics

RISING_PCT = 25  # same bar as the Butler's "your bill went up" cards


def _next_around(last_payment: str | None, today: date, until: date) -> str | None:
    if not last_payment:
        return None
    d = metrics.add_months(date.fromisoformat(last_payment), 1)
    return d.isoformat() if today <= d <= until else None


def upcoming_payments(customer_id: str, today: date | str | None = None) -> dict[str, Any]:
    sts = metrics.safe_to_spend(customer_id, today)
    rec = metrics.recurring_payments(customer_id, today)
    t = date.fromisoformat(sts["today"])
    until = date.fromisoformat(sts["until_date"])
    streams = {s["name"]: s for s in rec["recurring"]}
    streams.update({s["category"]: s for s in rec["recurring"] if s["category"] not in streams})

    # Bills = regular essentials that are paid as recurring payments (housing, utility bills).
    # Groceries and commuting are regular essentials too, but not bills: they go in one "other" line.
    items, other, other_names = [], 0.0, []
    for e in sts["explanation_inputs"]["regular_essentials"]:
        if e["still_expected_eur"] <= 0:
            continue
        s = streams.get(e["name"])
        if not s:
            other += e["still_expected_eur"]
            other_names.append(e["name"])
            continue
        change = s["change_pct"]
        items.append({
            "name": e["name"],
            "expected_eur": e["still_expected_eur"],
            "typical_monthly_eur": e["typical_monthly_eur"],
            "expected_around": _next_around(s["last_payment_date"], t, until),
            "last_payment_date": s["last_payment_date"],
            "change_pct": change,
            "rising": change is not None and change >= RISING_PCT,
        })
    items.sort(key=lambda i: (i["expected_around"] or "9999", -i["expected_eur"]))
    return {
        "customer_id": customer_id,
        "today": sts["today"],
        "until_date": sts["until_date"],
        "items": items,
        "other_essentials_eur": round(other, 2),
        "other_essentials": other_names,
        "total_expected_eur": sts["explanation_inputs"]["regular_essentials_still_expected_eur"],
        "left_after_eur": sts["amount_eur"],
        "this_week_eur": sts["this_week_eur"],
        "estimated": True,
        "source": "Estimated from your last 3 months (no e-invoices in the demo data).",
    }

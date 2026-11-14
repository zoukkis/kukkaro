"""Concept demo: "Kukkaro, order my usual groceries" with robot delivery.

The coach prepares a planned grocery order from the customer's own (synthetic) receipts and checks
it against safe-to-spend; the customer approves it. Nothing is ordered or paid in this project:
Kukkaro never moves money (root AGENTS.md §7) and payments are out of scope (§8). In production the
order would go to the grocery web shop and be approved in the banking app; in Finland S Group's
online store already delivers with robots in many cities.

Why it belongs to the money coach: online orders are planned, store trips carry the impulse buys
(docs/WHY_RECEIPTS.md, reason 5). The planned order leaves out the everyday "leak" items unless the
customer adds them back, and shows what that saves per week.

All numbers are computed here, in whole cents, from the receipts and DATA's safe_to_spend.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from kukkaro.data import metrics
from kukkaro.receipts.provider import SyntheticReceiptProvider

MIN_TRIPS = 3  # an item is part of "your usual groceries" if it was on at least this many receipts
# Concept delivery options. Fees are example values for the demo, labelled as such in the UI.
DELIVERY = {
    "robot": {"label": "Delivery robot", "eta": "about 30-60 min, where robot delivery is available", "fee_cents": 390},
    "home": {"label": "Home delivery", "eta": "a 1-hour slot today", "fee_cents": 690},
    "pickup": {"label": "Pick up at the store", "eta": "ready in about 2 hours", "fee_cents": 0},
}
CONCEPT_NOTE = ("Concept demo with synthetic receipts: nothing is ordered or paid. In production you would "
                "approve the order in your banking app and the grocery web shop would deliver it.")

_provider = SyntheticReceiptProvider()


def _cents(eur: float | Decimal) -> int:
    return int((Decimal(str(eur)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _eur(cents: int) -> float:
    return float(Decimal(cents) / 100)


def _weekly_qty(total_qty: float, days: int, by_weight: bool) -> float:
    q = Decimal(str(total_qty)) * 7 / days
    if by_weight:
        return float(max(Decimal("0.5"), q.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)))
    return float(max(Decimal(1), q.quantize(Decimal(1), rounding=ROUND_HALF_UP)))


def plan_grocery_order(customer_id: str, include_treats: bool = False, delivery: str = "robot") -> dict[str, Any]:
    """A week of the customer's usual groceries, from the last 3 complete months of receipts."""
    if delivery not in DELIVERY:
        raise metrics.DataError(f"delivery must be one of {', '.join(DELIVERY)}")
    metrics.customer_profile(customer_id)  # UnknownCustomer -> 404
    today = metrics.get_today()
    start, end, _ = metrics.complete_months(today, 3)
    days = (end - start).days + 1
    receipts, _ = _provider.grocery_receipts(customer_id, start, end)
    if not receipts:
        raise metrics.DataError("No grocery receipts to plan from")

    stats: dict[str, dict] = defaultdict(lambda: {"trips": 0, "qty": 0.0, "unit_cents": 0, "basket": "", "category": ""})
    for r in sorted(receipts, key=lambda r: r.timestamp):  # later receipts set the latest price
        seen = set()
        for it in r.items:
            s = stats[it.name]
            s["qty"] += it.qty
            s["unit_cents"] = _cents(it.unit_price_eur)
            s["basket"], s["category"] = it.basket, it.category
            if it.name not in seen:
                s["trips"] += 1
                seen.add(it.name)

    usual, treats = [], []
    for name, s in stats.items():
        if s["trips"] < MIN_TRIPS or s["basket"] not in ("MANDATORY_REGULAR", "EVERYDAY"):
            continue
        by_weight = "by weight" in name
        qty = _weekly_qty(s["qty"], days, by_weight)
        line = {"name": name, "category": s["category"], "basket": s["basket"], "qty": qty,
                "unit": "kg" if by_weight else "pcs", "unit_price_eur": _eur(s["unit_cents"]),
                "line_total_eur": _eur(int((Decimal(s["unit_cents"]) * Decimal(str(qty))).quantize(Decimal(1), rounding=ROUND_HALF_UP))),
                "bought_on_trips": s["trips"]}
        (treats if s["basket"] == "EVERYDAY" else usual).append(line)
    usual.sort(key=lambda x: (-x["bought_on_trips"], x["name"]))
    treats.sort(key=lambda x: -x["line_total_eur"])

    items = usual + (treats if include_treats else [])
    items_cents = sum(_cents(i["line_total_eur"]) for i in items)
    treats_cents = sum(_cents(t["line_total_eur"]) for t in treats)
    fee_cents = DELIVERY[delivery]["fee_cents"]
    total_cents = items_cents + fee_cents
    safe = metrics.safe_to_spend(customer_id, today)
    week_cents = _cents(safe["this_week_eur"])
    plan = {
        "customer_id": customer_id,
        "based_on": {"start": start.isoformat(), "end": end.isoformat(), "receipts": len(receipts), "min_trips": MIN_TRIPS},
        "items": items,
        "left_out": [] if include_treats else treats,
        "include_treats": include_treats,
        "items_total_eur": _eur(items_cents),
        "treats_per_week_eur": _eur(treats_cents),
        "delivery": {"option": delivery, **{k: v for k, v in DELIVERY[delivery].items() if k != "fee_cents"},
                     "fee_eur": _eur(fee_cents), "fee_is_example": True},
        "delivery_options": [{"option": k, "label": v["label"], "eta": v["eta"], "fee_eur": _eur(v["fee_cents"])}
                             for k, v in DELIVERY.items()],
        "order_total_eur": _eur(total_cents),
        "safe_to_spend_this_week_eur": _eur(week_cents),
        "left_this_week_after_order_eur": _eur(week_cents - total_cents),
        "fits_this_week": total_cents <= week_cents,
        "synthetic": True,
        "concept": True,
        "note": CONCEPT_NOTE,
    }
    plan["plan_id"] = hashlib.sha256(json.dumps(
        [plan["items"], plan["delivery"]["option"], plan["order_total_eur"]], sort_keys=True).encode()).hexdigest()[:12]
    return plan


def approve_order(customer_id: str, plan_id: str, include_treats: bool, delivery: str) -> dict[str, Any]:
    """Simulated approval: re-plans on the server (never trusts client totals), checks the plan is
    unchanged, and returns a confirmation. No order is placed, no money moves."""
    plan = plan_grocery_order(customer_id, include_treats, delivery)
    if plan["plan_id"] != plan_id:
        raise metrics.DataError("The order changed since you reviewed it. Please review it again.")
    return {
        "status": "approved_simulation",
        "order_ref": "DEMO-" + plan_id[:6].upper(),
        "items": len(plan["items"]),
        "order_total_eur": plan["order_total_eur"],
        "delivery": plan["delivery"],
        "left_this_week_after_order_eur": plan["left_this_week_after_order_eur"],
        "synthetic": True,
        "concept": True,
        "note": CONCEPT_NOTE,
    }

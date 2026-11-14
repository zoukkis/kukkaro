"""Receipt-based insights (pure functions over synthetic receipts; COACH uses them as tools).

All money is summed in whole cents, so every split adds up to the card data exactly.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from kukkaro.data import metrics
from kukkaro.data.db import get_conn
from kukkaro.receipts.generator import catalog
from kukkaro.receipts.provider import SyntheticReceiptProvider

SPENDING = ("MANDATORY_REGULAR", "MANDATORY_IRREGULAR", "EVERYDAY")
_provider = SyntheticReceiptProvider()


def _cents(eur: float) -> int:
    return int(round(eur * 100))


def _eur(cents: int) -> float:
    return round(cents / 100, 2)


def _receipts(customer_id: str, start, end):
    s, e = metrics._period(start, end)
    metrics._check_customer(get_conn(), customer_id)
    receipts, without = _provider.grocery_receipts(customer_id, s, e)
    return s, e, receipts, without


def basket_split(customer_id: str, start: date | str, end: date | str) -> dict[str, Any]:
    """Grocery spend split into baskets by receipt item, for the With/Without receipts toggle.

    Contract (DECISIONS.md): grocery_total_eur equals the card Groceries total for the period, and
    sum(split) + without_receipt_eur == grocery_total_eur to the cent."""
    s, e, receipts, without = _receipts(customer_id, start, end)
    per_basket = {b: 0 for b in SPENDING}
    leaks: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in receipts:
        for it in r.items:
            c = _cents(it.line_total_eur)
            per_basket[it.basket] += c
            if it.basket == "EVERYDAY":
                leaks[it.name][0] += c
                leaks[it.name][1] += it.qty
    without_c = sum(_cents(-float(t["tx_amount_eur"])) for t in without)
    total_c = sum(_cents(r.total_eur) for r in receipts) + without_c
    top = sorted(leaks.items(), key=lambda kv: -kv[1][0])[:5]
    return {
        "customer_id": customer_id, "start": s.isoformat(), "end": e.isoformat(),
        "grocery_total_eur": _eur(total_c),
        "without_receipt_eur": _eur(without_c),
        "receipts": len(receipts), "trips_without_receipt": len(without),
        "split": [{"basket": b, "total_eur": _eur(per_basket[b])} for b in SPENDING],
        "top_leak_items": [{"name": n, "total_eur": _eur(c), "qty": q} for n, (c, q) in top],
        "synthetic": True,
    }


def leak_items(customer_id: str, start: date | str, end: date | str, top: int = 5) -> dict[str, Any]:
    """Top Everyday-spending items inside grocery trips, by euros."""
    s, e, receipts, _ = _receipts(customer_id, start, end)
    leaks: dict[str, list] = defaultdict(lambda: [0, 0, 0])  # cents, qty, trips
    for r in receipts:
        seen = set()
        for it in r.items:
            if it.basket == "EVERYDAY":
                leaks[it.name][0] += _cents(it.line_total_eur)
                leaks[it.name][1] += it.qty
                if it.name not in seen:
                    leaks[it.name][2] += 1
                    seen.add(it.name)
    total = sum(v[0] for v in leaks.values())
    ranked = sorted(leaks.items(), key=lambda kv: -kv[1][0])[:top]
    return {"customer_id": customer_id, "start": s.isoformat(), "end": e.isoformat(),
            "everyday_in_groceries_eur": _eur(total), "trips": len(receipts),
            "items": [{"name": n, "total_eur": _eur(c), "qty": q, "trips": t} for n, (c, q, t) in ranked],
            "synthetic": True}


def item_spend(customer_id: str, item_or_category: str, start: date | str, end: date | str) -> dict[str, Any]:
    """Spend on items whose name or category contains the text (case-insensitive)."""
    s, e, receipts, _ = _receipts(customer_id, start, end)
    q = item_or_category.strip().lower()
    cents, qty, trips, names = 0, 0.0, 0, set()
    for r in receipts:
        hit = False
        for it in r.items:
            if q in it.name.lower() or q == it.category.lower():
                cents += _cents(it.line_total_eur)
                qty += it.qty
                names.add(it.name)
                hit = True
        trips += hit
    return {"customer_id": customer_id, "query": item_or_category, "start": s.isoformat(),
            "end": e.isoformat(), "total_eur": _eur(cents), "qty": round(qty, 3), "trips": trips,
            "matched_items": sorted(names), "synthetic": True}


def store_brand_savings(customer_id: str, months: int = 3) -> dict[str, Any]:
    """What switching branded items to their store-brand twins would save, per month and per year,
    based on the last `months` complete months."""
    s, e, n = metrics.complete_months(metrics.get_today(), months)
    _, _, receipts, _ = _receipts(customer_id, s, e)
    cat = catalog()
    per_item: dict[str, list] = defaultdict(lambda: [0, 0.0, ""])  # saving cents, qty, twin
    for r in receipts:
        for it in r.items:
            p = cat.get(it.name)
            if p and p.twin and p.twin in cat:
                diff = p.price_cents - cat[p.twin].price_cents
                if diff > 0:
                    per_item[it.name][0] += int(diff * it.qty)
                    per_item[it.name][1] += it.qty
                    per_item[it.name][2] = p.twin
    period_c = sum(v[0] for v in per_item.values())
    monthly_c = round(period_c / max(n, 1))
    ranked = sorted(per_item.items(), key=lambda kv: -kv[1][0])[:5]
    return {"customer_id": customer_id, "start": s.isoformat(), "end": e.isoformat(), "months": n,
            "monthly_saving_eur": _eur(monthly_c), "yearly_saving_eur": _eur(monthly_c * 12),
            "top_swaps": [{"item": k, "store_brand_twin": t, "saving_in_period_eur": _eur(c), "qty": q}
                          for k, (c, q, t) in ranked],
            "synthetic": True}

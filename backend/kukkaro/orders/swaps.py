"""Store-brand swap: "same food, smaller bill" (docs/WHY_RECEIPTS.md, reason 6).

The receipts say which branded items the customer keeps buying and what switching them to the
store-brand twin would have saved (receipts.insights.store_brand_savings, synthetic receipt prices).
For each top swap, the public zone finds the real S-Group own-brand product on S-kaupat with its
picture and today's page price (butler.products), so the card can show it and add it to the order.

Two kinds of numbers, never mixed: the saving comes from the customer's (synthetic) receipts; the
product price comes from the S-kaupat page and is shown with that page as its source.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from kukkaro.butler import products

MAX_SWAPS = 4


def _eur(cents: int) -> float:
    return float(Decimal(cents) / 100)


def _cents(eur: float) -> int:
    return int((Decimal(str(eur)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def swaps(customer_id: str) -> dict[str, Any]:
    from kukkaro.receipts.insights import store_brand_savings
    s = store_brand_savings(customer_id)  # UnknownCustomer -> 404 before any web call
    months = max(int(s["months"]), 1)
    top = s["top_swaps"][:MAX_SWAPS]
    with ThreadPoolExecutor(max_workers=max(1, len(top))) as ex:
        found = list(ex.map(lambda x: products.own_brand_for(x["store_brand_twin"], x["item"]), top))
    out = []
    for x, prod in zip(top, found):
        monthly_c = int((Decimal(_cents(x["saving_in_period_eur"])) / months).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        out.append({"item": x["item"], "store_brand_twin": x["store_brand_twin"],
                    "saving_in_period_eur": x["saving_in_period_eur"], "monthly_saving_eur": _eur(monthly_c),
                    "qty_in_period": x["qty"], "product": prod})
    return {"customer_id": customer_id, "start": s["start"], "end": s["end"], "months": s["months"],
            "monthly_saving_eur": s["monthly_saving_eur"], "yearly_saving_eur": s["yearly_saving_eur"],
            "swaps": out, "synthetic": True,
            "note": "Savings are from your synthetic receipts; product prices are read from the S-kaupat page."}

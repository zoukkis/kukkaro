"""Data endpoints (root AGENTS.md §5.4): thin wrappers around kukkaro.data.metrics.

The only thing done here is naming: field names follow what WEB built on
(overseer decision, docs/DECISIONS.md 14 Nov 12:31). All numbers come from DATA unchanged.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from kukkaro.data import metrics

router = APIRouter(tags=["data"])


def web_summary(s: dict[str, Any], month: str) -> dict[str, Any]:
    """DATA's spending_summary in WEB's names, keeping DATA's extra fields."""
    return {
        "customer_id": s["customer_id"],
        "month": month,
        "period": s["period"],
        "income_eur": s["income_eur"],
        "spending_eur": s["spending_total_eur"],
        "balance_eur": s["balance_eur"],
        "balance_date": s["balance_date"],
        "transfers_out_eur": s["transfers_out_eur"],
        "transfers_in_eur": s["transfers_in_eur"],
        "tx_count": s["transactions"],
        "baskets": [
            {"basket": b["basket"], "label": b["label"], "total_eur": b["spent_eur"],
             "share_pct": b["share_pct"], "tx_count": b["transactions"]}
            for b in s["baskets"]
        ],
        "top_categories": [
            {"category": c["name"], "basket": c["basket"], "total_eur": c["spent_eur"], "tx_count": c["transactions"]}
            for c in s["top_categories"]
        ],
        "receipts": s.get("receipts"),
        **({"synthetic": True} if s.get("synthetic") else {}),
    }


@router.get("/customers/{customer_id}/summary")
def summary(customer_id: str, month: str | None = None, receipts: bool = False) -> dict[str, Any]:
    """Spending per basket and top categories for one month (default: the month of 'today').
    `?receipts=true` gives the With-receipts view: grocery spend split by (synthetic) receipt items."""
    m = month or metrics.get_today().strftime("%Y-%m")
    start, end = metrics.month_bounds(m)
    s = metrics.spending_summary(customer_id, start, end)
    if receipts:
        try:
            from kukkaro.receipts.insights import basket_split
        except ImportError:
            raise HTTPException(status_code=503, detail="The receipt split is not available yet (RECEIPTS module not merged).") from None
        s = metrics.merge_grocery_split(s, basket_split(customer_id, start, end))
    return web_summary(s, m)


@router.get("/customers/{customer_id}/transactions")
def transactions(customer_id: str, limit: int = 50, offset: int = 0, basket: str | None = None,
                 month: str | None = None) -> dict[str, Any]:
    """Paged tx_enriched rows, newest first: {items, total, limit, offset}."""
    return metrics.transactions_page(customer_id, limit=limit, offset=offset, basket=basket, month=month)


@router.get("/customers/{customer_id}/safe-to-spend")
def safe_to_spend(customer_id: str) -> dict[str, Any]:
    """DATA's safe_to_spend unchanged: the weekly card shows `this_week_eur`, with `amount_eur` until `until_date`."""
    return metrics.safe_to_spend(customer_id)


class WhatIfRequest(BaseModel):
    category_or_item: str = Field(min_length=1, max_length=80)
    change_pct: float = Field(ge=-100, le=1000)


@router.post("/customers/{customer_id}/what-if")
def what_if(customer_id: str, body: WhatIfRequest) -> dict[str, Any]:
    """Monthly and yearly impact of changing spending on a card category (e.g. "Restaurants") or, if no
    category matches, on a receipt item (e.g. "Energy drink 0.5 l", synthetic). `monthly_eur`/`yearly_eur` per §5.4."""
    from kukkaro.coach.tools import item_what_if
    try:
        r = metrics.what_if(customer_id, body.category_or_item, body.change_pct)
    except metrics.UnknownCustomer:
        raise
    except metrics.DataError as category_error:
        if not str(category_error).startswith("Unknown category"):
            raise
        try:
            r = item_what_if(customer_id, body.category_or_item, body.change_pct)
        except metrics.DataError:
            raise metrics.DataError(f"No category or receipt item matches {body.category_or_item!r}") from None
    return {"monthly_eur": r["monthly_change_eur"], "yearly_eur": r["yearly_change_eur"], **r}

"""Concept demo endpoints: plan and (simulated) approval of a grocery order with robot delivery.
Nothing is ordered or paid. See kukkaro/orders/planner.py."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from kukkaro.orders import planner, swaps

router = APIRouter(tags=["orders (concept)"])
Delivery = Literal["robot", "home", "pickup"]


@router.get("/customers/{customer_id}/grocery-order")
def plan(customer_id: str, include_treats: bool = False, delivery: Delivery = "robot",
         extra: list[str] = Query(default=[], max_length=10), swap: list[str] = Query(default=[], max_length=10)) -> dict:
    """`extra` = products added from the Butler, `swap` = own-brand products replacing a branded item (by id)."""
    return planner.plan_grocery_order(customer_id, include_treats, delivery, extra, swap)


@router.get("/customers/{customer_id}/swaps")
def store_brand_swaps(customer_id: str) -> dict:
    """Same food, smaller bill: branded items from the receipts with the real S-Group own-brand product."""
    return swaps.swaps(customer_id)


class ApproveRequest(BaseModel):
    plan_id: str = Field(min_length=6, max_length=64)
    include_treats: bool = False
    delivery: Delivery = "robot"
    extras: list[str] = Field(default_factory=list, max_length=10)
    swaps: list[str] = Field(default_factory=list, max_length=10)


@router.post("/customers/{customer_id}/grocery-order/approve")
def approve(customer_id: str, body: ApproveRequest) -> dict:
    return planner.approve_order(customer_id, body.plan_id, body.include_treats, body.delivery, body.extras, body.swaps)

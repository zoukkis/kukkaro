"""Concept demo endpoints: plan and (simulated) approval of a grocery order with robot delivery.
Nothing is ordered or paid. See kukkaro/orders/planner.py."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from kukkaro.orders import planner

router = APIRouter(tags=["orders (concept)"])
Delivery = Literal["robot", "home", "pickup"]


@router.get("/customers/{customer_id}/grocery-order")
def plan(customer_id: str, include_treats: bool = False, delivery: Delivery = "robot") -> dict:
    return planner.plan_grocery_order(customer_id, include_treats, delivery)


class ApproveRequest(BaseModel):
    plan_id: str = Field(min_length=6, max_length=64)
    include_treats: bool = False
    delivery: Delivery = "robot"


@router.post("/customers/{customer_id}/grocery-order/approve")
def approve(customer_id: str, body: ApproveRequest) -> dict:
    return planner.approve_order(customer_id, body.plan_id, body.include_treats, body.delivery)

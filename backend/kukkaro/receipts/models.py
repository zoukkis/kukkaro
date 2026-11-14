"""Receipt models, exactly the JSON contract in AGENTS.md §5.3. All receipt data is synthetic."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BasketName = Literal["MANDATORY_REGULAR", "MANDATORY_IRREGULAR", "EVERYDAY"]


class ReceiptItem(BaseModel):
    name: str
    category: str
    qty: float = Field(gt=0)
    unit_price_eur: float = Field(ge=0)
    line_total_eur: float = Field(ge=0)
    basket: BasketName
    store_brand: bool = False


class Receipt(BaseModel):
    tx_id: str
    store: str
    timestamp: str
    total_eur: float
    synthetic: Literal[True] = True
    channel: Literal["in_store", "online_order"] = "in_store"
    delivery_fee_eur: float = 0.0
    items: list[ReceiptItem]

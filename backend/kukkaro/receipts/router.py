"""Receipt endpoint. Paths have no /api prefix: api/main.py mounts this router under /api."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from kukkaro.receipts.provider import provider

router = APIRouter(tags=["receipts"])


@router.get("/transactions/{tx_id}/receipt")
def get_receipt(tx_id: str) -> dict[str, Any]:
    """Synthetic receipt for a Groceries purchase (≤ 300 €); 404 for anything else."""
    r = provider.get_receipt(tx_id)
    if r is None:
        raise HTTPException(status_code=404, detail="No receipt: not a grocery purchase, or a trip above 300 €.")
    return r.model_dump()

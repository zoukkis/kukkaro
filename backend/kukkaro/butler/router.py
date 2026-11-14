"""POST /api/butler (root AGENTS.md §5.4, with `draft` per overseer decision 14 Nov 12:31)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from kukkaro.butler import agent

router = APIRouter(tags=["butler"])


class ButlerRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=40)
    task: str = Field(min_length=3, max_length=500)


@router.post("/butler")
def butler(body: ButlerRequest) -> dict:
    """{answer, sources[{n, title, url, published_date, cited}], next_steps[], draft, ...}"""
    return agent.run(body.customer_id, body.task)

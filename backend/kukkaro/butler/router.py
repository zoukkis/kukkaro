"""POST /api/butler (root AGENTS.md §5.4, with `draft` per overseer decision 14 Nov 12:31)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from kukkaro.butler import agent, watchlist

router = APIRouter(tags=["butler"])


class ButlerRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=40)
    task: str = Field(min_length=3, max_length=500)


@router.post("/butler")
def butler(body: ButlerRequest) -> dict:
    """{answer, sources[{n, title, url, published_date, cited}], next_steps[], draft, ...}"""
    return agent.run(body.customer_id, body.task)


@router.get("/customers/{customer_id}/butler/suggestions")
def butler_suggestions(customer_id: str) -> dict:
    """Proactive cards ("Your utility bills went up"), each with the Butler task to run on tap."""
    return agent.suggestions(customer_id)


class WatchRequest(BaseModel):
    task: str = Field(min_length=3, max_length=500)


@router.post("/customers/{customer_id}/watchlist")
def watch(customer_id: str, body: WatchRequest) -> dict:
    """Save a Butler question; Kukkaro re-checks its sources later (butler/watchlist.py)."""
    try:
        return watchlist.watch(customer_id, body.task)
    except watchlist.CannotWatch as e:
        raise HTTPException(422, str(e)) from None


@router.get("/customers/{customer_id}/watchlist")
def watches(customer_id: str) -> dict:
    """{items: [{id, task, question_sent, last_checked_at, last_result, sources[]}]}"""
    from kukkaro.data import metrics
    metrics.customer_profile(customer_id)  # unknown customer -> 404
    return {"customer_id": customer_id, "items": watchlist.list_watches(customer_id)}


@router.post("/watchlist/{watch_id}/check")
def check_watch(watch_id: str) -> dict:
    """{changed, new_sources, gone_sources, updated_sources, summary, sources[]} (live Exa, public zone only)."""
    try:
        return watchlist.check(watch_id)
    except watchlist.WatchNotFound:
        raise HTTPException(404, "No such watch") from None


@router.delete("/watchlist/{watch_id}")
def delete_watch(watch_id: str) -> dict:
    try:
        watchlist.delete(watch_id)
    except watchlist.WatchNotFound:
        raise HTTPException(404, "No such watch") from None
    return {"deleted": watch_id}

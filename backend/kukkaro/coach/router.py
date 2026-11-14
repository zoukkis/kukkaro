"""POST /api/chat (root AGENTS.md §5.4, plus `provider` in and `model`/`host` out: overseer 14 Nov 12:31)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from kukkaro.coach import llm, numbers
from kukkaro.coach.prompts import system_prompt
from kukkaro.coach.tools import SPECS, executor
from kukkaro.data import metrics

router = APIRouter(tags=["coach"])


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=40)
    message: str = Field(min_length=1, max_length=1000)
    history: list[Turn] = Field(default_factory=list, max_length=20)
    provider: Literal["gemini", "gemma"] | None = None


def answer(customer_id: str, message: str, history: list[dict], provider: str | None = None) -> dict:
    """One coach answer. Shared by the route and eval.py."""
    metrics.customer_profile(customer_id)  # 404 for an unknown customer before any LLM call
    today = metrics.get_today()
    r = llm.run(system_prompt(today), history, message, SPECS, executor(customer_id), provider)
    r.text = llm.plain(r.text)
    calls = [{"name": c["name"], "args": c["args"]} for c in r.tool_calls]
    return {
        "answer": r.text,
        "tool_calls": calls,
        "figures": numbers.figures(r.text, r.tool_calls) if not r.error else [],
        "unverified_numbers": numbers.unverified_numbers(r.text, r.tool_calls, today.isoformat()) if not r.error else [],
        "model": r.model,
        "host": r.host,
        "provider": r.provider,
        "seconds": r.seconds,
        "round_seconds": r.round_seconds,
        "error": r.error,
        "_tool_results": r.tool_calls,  # stripped by the route; used by eval.py
    }


@router.post("/chat")
def chat(body: ChatRequest) -> dict:
    out = answer(body.customer_id, body.message, [t.model_dump() for t in body.history], body.provider)
    out.pop("_tool_results")
    return out

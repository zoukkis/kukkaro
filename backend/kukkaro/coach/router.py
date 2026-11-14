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


WITHHELD_TEXT = ("I couldn't check every number in my answer against your data, so I won't guess. "
                 "Try asking about a specific month, basket or category.")


def answer(customer_id: str, message: str, history: list[dict], provider: str | None = None) -> dict:
    """One coach answer. Shared by the route and eval.py.

    "The LLM never invents numbers" is enforced here, not only in the prompt: if the answer contains
    a number that no tool produced, the model is asked once more (tools first); if the second answer
    still has one, the answer is withheld and the user gets an honest message instead."""
    metrics.customer_profile(customer_id)  # 404 for an unknown customer before any LLM call
    today = metrics.get_today()
    system, execute = system_prompt(today), executor(customer_id)
    r = llm.run(system, history, message, SPECS, execute, provider)
    r.text = llm.plain(r.text)
    unverified = numbers.unverified_numbers(r.text, r.tool_calls, today.isoformat()) if not r.error else []
    first_seconds, retried, withheld = r.seconds, False, False
    if unverified:
        retried = True
        nudge = (f"Your previous answer used numbers that did not come from a tool result ({', '.join(unverified)}). "
                 f"Answer my question again: call the right tool first and use only numbers from its result. "
                 f"My question was: {message}")
        r2 = llm.run(system, history + [{"role": "user", "content": message}, {"role": "assistant", "content": r.text}],
                     nudge, SPECS, execute, provider)
        r2.text = llm.plain(r2.text)
        unverified2 = numbers.unverified_numbers(r2.text, r2.tool_calls, today.isoformat()) if not r2.error else ["error"]
        r2.seconds = round(first_seconds + r2.seconds, 2)
        if not r2.error and not unverified2:
            r, unverified = r2, []
        else:
            withheld = True
            r.text, r.seconds = WITHHELD_TEXT, r2.seconds
    calls = [{"name": c["name"], "args": c["args"]} for c in r.tool_calls]
    return {
        "answer": r.text,
        "tool_calls": calls,
        "figures": numbers.figures(r.text, r.tool_calls) if not (r.error or withheld) else [],
        "unverified_numbers": unverified if not withheld else [],
        "number_check": "withheld" if withheld else ("retried" if retried else "ok"),
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

"""POST /api/chat (root AGENTS.md §5.4): one assistant, split by who may see what data.

- Trusted zone: Gemma 4 (`TRUSTED_PROVIDER`) answers with the customer's own data through the tools.
  When it needs current outside facts it calls `research_web`, which goes through the privacy gateway
  (coach/privacy.py) to the public zone (butler/research.py: Exa + Gemini, no customer data).
- Fallback: if Gemma errors, times out or its answer fails the number check, it gets one retry; then
  Gemini (`FALLBACK_PROVIDER`) answers that turn, and the response says so (`fallback: true`).

There is no model picker: the response carries `zones` and `fallback` so the UI can label each answer.
"""
from __future__ import annotations

import threading
import time
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from kukkaro.coach import llm, numbers, privacy
from kukkaro.coach.prompts import system_prompt
from kukkaro.coach.tools import SPECS, executor
from kukkaro.data import metrics

router = APIRouter(tags=["coach"])

TRUSTED_PROVIDER = "gemma"
FALLBACK_PROVIDER = "gemini"
# A failed Gemma call is retried only if it failed fast (a refused or broken call); a slow failure
# (timeout) goes straight to the fallback so the demo never hangs.
RETRY_IF_FAILED_WITHIN_S = 20

STATS = {"turns": 0, "trusted": 0, "fallback": 0, "withheld": 0, "research_calls": 0, "research_blocked": 0}
_stats_lock = threading.Lock()


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=40)
    message: str = Field(min_length=1, max_length=1000)
    history: list[Turn] = Field(default_factory=list, max_length=20)


WITHHELD_TEXT = ("I couldn't check every number in my answer against your data, so I won't guess. "
                 "Try asking about a specific month, basket or category.")


def _problems(r: llm.RunResult, today: str) -> list[str]:
    """Why an answer can't be shown: numbers no tool produced, or (S-Group rule) other grocery chains."""
    if r.error:
        return ["error"]
    # Web facts write numbers the Finnish way ("1,19 €", "2 000 €"): read them like answers are read.
    facts = " ".join(f.get("text", "") for c in r.tool_calls if c["name"] == "research_web"
                     for f in (c.get("result") or {}).get("facts") or [])
    out = numbers.unverified_numbers(r.text, r.tool_calls, f"{today} {facts}")
    from kukkaro.butler.research import competitor_mentions
    out += [f"names {c}" for c in competitor_mentions(r.text)]
    return out


def _nudge(problems: list[str], message: str) -> str:
    return (f"Your previous answer had problems ({', '.join(problems)}). Answer my question again: call the right tool "
            f"first, use only numbers from tool results, and follow the S-Group rule. My question was: {message}")


def _turn(provider: str, customer_id: str, system: str, history: list[dict], message: str, today: str):
    """One provider's best answer: a run, one retry (a fast error, or a nudge after a failed number
    check). Returns (result, problems, retried, executor)."""
    ex = executor(customer_id)
    r = llm.run(system, history, message, SPECS, ex, provider)
    r.text = llm.plain(r.text)
    probs = _problems(r, today)
    if not probs:
        return r, [], False, ex
    if r.error:
        if r.seconds > RETRY_IF_FAILED_WITHIN_S:
            return r, probs, False, ex
        ex = executor(customer_id)
        r2 = llm.run(system, history, message, SPECS, ex, provider)
    else:
        r2 = llm.run(system, history + [{"role": "user", "content": message}, {"role": "assistant", "content": r.text}],
                     _nudge(probs, message), SPECS, ex, provider)
    r2.text = llm.plain(r2.text)
    r2.seconds = round(r.seconds + r2.seconds, 2)
    probs2 = _problems(r2, today)
    return r2, probs2, True, ex


def answer(customer_id: str, message: str, history: list[dict], trusted: str | None = None,
           fallback: str | None = FALLBACK_PROVIDER) -> dict:
    """One assistant answer. Shared by the route and eval.py. `trusted` / `fallback` exist for tests and
    the eval; the API always uses Gemma, then Gemini."""
    profile = metrics.customer_profile(customer_id)  # 404 for an unknown customer before any LLM call
    t0 = time.monotonic()
    today = metrics.get_today()
    system = system_prompt(today, privacy.banded_context(profile))
    primary = trusted or TRUSTED_PROVIDER
    r, probs, retried, ex = _turn(primary, customer_id, system, history, message, today.isoformat())
    used_fallback, primary_error = False, None
    if probs and fallback and fallback != primary:
        primary_error = (r.error if r.error else "; ".join(probs))[:300]
        used_fallback = True
        r, probs, retried2, ex = _turn(fallback, customer_id, system, history, message, today.isoformat())
        retried = retried or retried2
    withheld = bool(probs) and not r.error
    if withheld:
        r.text = WITHHELD_TEXT
    sent = [x for x in ex.research_log if x["question_sent"]]
    sources, seen = [], set()
    for x in sent:
        for s in x["sources"]:
            if s["url"] not in seen:
                seen.add(s["url"])
                sources.append(s)
    with _stats_lock:
        STATS["turns"] += 1
        STATS["fallback" if used_fallback else "trusted"] += 1
        STATS["withheld"] += int(withheld)
        STATS["research_calls"] += len(sent)
        STATS["research_blocked"] += sum(1 for x in ex.research_log if x["blocked"])
    calls = [{"name": c["name"], "args": c["args"]} for c in r.tool_calls]
    ok = not (r.error or withheld)
    return {
        "answer": r.text,
        "tool_calls": calls,
        "figures": numbers.figures(r.text, [c for c in r.tool_calls if c["name"] != "research_web"]) if ok else [],
        "unverified_numbers": [] if withheld or r.error else probs,
        "check_problems": probs if withheld else [],
        "number_check": "withheld" if withheld else ("retried" if retried else "ok"),
        # Privacy labels (no model picker): which zones took part, and whether the backup model answered.
        "zones": ["trusted", "public"] if sent else ["trusted"],
        "fallback": used_fallback,
        "trusted_host": r.host if not used_fallback else None,  # "verda" = Gemma in the EU; "google" = open model via Google
        "research": [{"question_sent": x["question_sent"], "blocked": x["blocked"], "kind": x.get("kind")}
                     for x in ex.research_log],
        "sources": sources,
        "model": r.model,
        "host": r.host,
        "provider": r.provider,
        "seconds": round(time.monotonic() - t0, 2),
        "round_seconds": r.round_seconds,
        "error": r.error,
        "primary_error": primary_error,
        "_tool_results": r.tool_calls,  # stripped by the route; used by eval.py
    }


@router.post("/chat")
def chat(body: ChatRequest) -> dict:
    out = answer(body.customer_id, body.message, [t.model_dump() for t in body.history])
    out.pop("_tool_results")
    return out


@router.get("/chat/stats")
def chat_stats() -> dict:
    """Since the server started: how many turns Gemma answered vs the backup model."""
    with _stats_lock:
        s = dict(STATS)
    s["fallback_rate_pct"] = round(100 * s["fallback"] / s["turns"], 1) if s["turns"] else 0.0
    return s

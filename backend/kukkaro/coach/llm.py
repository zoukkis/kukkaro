"""The single LLM interface for Kukkaro (COACH; BUTLER uses it too).

`run(system, history, message, tools, execute, provider=None)` runs the whole tool loop: the model
picks tools, `execute(name, args)` computes them (deterministic Python, never the LLM), the results
go back to the model, until it answers in text. The loop lives here, inside each provider's native
message format, because Gemini's thinking models sign their tool calls and the model's previous
turn must be passed back unchanged.

Providers (`LLM_PROVIDER` in .env, or per request):
- gemini: Google Gen AI SDK, model `GEMINI_MODEL` (default gemini-4-hydrogen), thinking "low".
- gemma:  Stage 1 = Gemma 4 through the same Gemini API and key (`GEMMA_MODEL`); thinking level is
          not supported there, so it is left out. Stage 2 = vLLM on Verda via `GEMMA_BASE_URL` (not
          wired yet; see docs/DECISIONS.md).

Errors and timeouts never raise: the caller gets a friendly fallback text and `error` set.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("kukkaro.llm")

FALLBACK_TEXT = "Sorry, I couldn't reach the coach just now. Please try again in a moment."
MAX_TOOL_ROUNDS = 5
# Seconds per model call and per whole answer. Gemma through Google's API (stage 1) is slower, and
# Google ends a call at our deadline (504), so it gets more room; the UI shows a loading state.
TIMEOUTS = {"gemini": (15, 30), "gemma": (35, 60)}
# If the primary model fails (timeout, 5xx), the whole answer is redone once with this model, as long
# as this many seconds are left. A fresh run, because signed tool calls belong to the model that made them.
FALLBACK_MODELS = {"gemini": "gemini-3.8-flash", "gemma": None}
MIN_SECONDS_FOR_FALLBACK = 10


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON schema (type: object)


@dataclass
class RunResult:
    text: str
    tool_calls: list[dict] = field(default_factory=list)  # [{name, args, result}]
    model: str = ""
    host: str = ""
    provider: str = ""
    seconds: float = 0.0
    round_seconds: list[float] = field(default_factory=list)  # per model call, for tuning latency
    error: str | None = None


def provider_config(provider: str | None = None) -> dict[str, str]:
    p = (provider or os.environ.get("LLM_PROVIDER") or "gemini").strip().lower()
    if p not in ("gemini", "gemma"):
        raise ValueError(f"Unknown provider {p!r}; use gemini or gemma")
    if p == "gemini":
        return {"provider": p, "model": os.environ.get("GEMINI_MODEL") or "gemini-4-hydrogen", "host": "google"}
    if os.environ.get("GEMMA_BASE_URL"):
        return {"provider": p, "model": os.environ.get("GEMMA_MODEL") or "gemma-4-26b-a4b-it", "host": "verda"}
    return {"provider": p, "model": os.environ.get("GEMMA_MODEL") or "gemma-4-26b-a4b-it", "host": "google"}


_clients: dict[str, Any] = {}


def _google_client(provider: str):
    if provider not in _clients:
        from google import genai
        from google.genai import types
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _clients[provider] = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUTS[provider][0] * 1000))
    return _clients[provider]


def _safe_execute(execute: Callable[[str, dict], dict], name: str, args: dict) -> dict:
    try:
        return execute(name, args)
    except Exception as e:  # a tool bug must not crash the chat; the model sees the error
        log.warning("tool %s failed: %s", name, e)
        return {"error": str(e)}


def _run_google(cfg: dict, system: str, history: list[dict], message: str, tools: list[ToolSpec],
                execute: Callable[[str, dict], dict], deadline: float, result: RunResult) -> None:
    from google.genai import types

    client = _google_client(cfg["provider"])
    contents = [types.Content(role="user" if h["role"] == "user" else "model", parts=[types.Part(text=h["content"])])
                for h in history if h.get("content")]
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
    gen_cfg = types.GenerateContentConfig(
        system_instruction=system,
        tools=[types.Tool(function_declarations=[
            types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=t.parameters)
            for t in tools])] if tools else None,
        thinking_config=types.ThinkingConfig(thinking_level="low") if cfg["provider"] == "gemini" else None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    for _ in range(MAX_TOOL_ROUNDS + 1):
        if time.monotonic() > deadline:
            raise TimeoutError("coach took too long")
        t = time.monotonic()
        resp = client.models.generate_content(model=cfg["model"], contents=contents, config=gen_cfg)
        result.round_seconds.append(round(time.monotonic() - t, 2))
        calls = resp.function_calls or []
        if not calls:
            parts = resp.candidates[0].content.parts if resp.candidates and resp.candidates[0].content else []
            result.text = "".join(p.text for p in parts or [] if getattr(p, "text", None) and not getattr(p, "thought", False)).strip()
            return
        contents.append(resp.candidates[0].content)  # unchanged: keeps thought signatures
        replies = []
        for fc in calls:
            args = dict(fc.args or {})
            out = _safe_execute(execute, fc.name, args)
            result.tool_calls.append({"name": fc.name, "args": args, "result": out})
            replies.append(types.Part.from_function_response(name=fc.name, response=out))
        contents.append(types.Content(role="user", parts=replies))
    raise RuntimeError("too many tool rounds")


def run(system: str, history: list[dict], message: str, tools: list[ToolSpec],
        execute: Callable[[str, dict], dict], provider: str | None = None) -> RunResult:
    cfg = provider_config(provider)
    t0 = time.monotonic()
    deadline = t0 + TIMEOUTS[cfg["provider"]][1]
    models = [cfg["model"]] + ([FALLBACK_MODELS[cfg["provider"]]] if FALLBACK_MODELS.get(cfg["provider"]) and cfg["host"] == "google" else [])
    errors: list[str] = []
    result = RunResult(text="", model=cfg["model"], host=cfg["host"], provider=cfg["provider"])
    for i, model in enumerate(models):
        if i > 0 and deadline - time.monotonic() < MIN_SECONDS_FOR_FALLBACK:
            break
        result = RunResult(text="", model=model, host=cfg["host"], provider=cfg["provider"])
        try:
            if cfg["host"] == "verda":
                raise NotImplementedError("Gemma on Verda (stage 2) is not wired yet")
            _run_google({**cfg, "model": model}, system, history, message, tools, execute, deadline, result)
            if not result.text:
                raise RuntimeError("empty answer")
            break
        except Exception as e:
            key = os.environ.get("GEMINI_API_KEY") or ""
            msg = f"{model}: {type(e).__name__}: {str(e).replace(key, '<key>') if key else e}"[:300]
            errors.append(msg)
            log.warning("LLM run failed (%s): %s", cfg["provider"], msg)
            result.text = ""
    if not result.text:
        result.text = FALLBACK_TEXT
        result.error = " | ".join(errors) or "no answer"
    elif errors:
        log.info("answered by fallback model %s after: %s", result.model, errors)
    result.seconds = round(time.monotonic() - t0, 2)
    return result


def complete_json(system: str, prompt: str, schema: dict, provider: str | None = None) -> tuple[dict | None, RunResult]:
    """One structured answer (JSON matching `schema`) with no tools; used by the Butler.
    Same timeouts and fallback model as `run()`. Returns (parsed JSON or None, RunResult)."""
    from google.genai import types

    cfg = provider_config(provider)
    t0 = time.monotonic()
    deadline = t0 + TIMEOUTS[cfg["provider"]][1]
    models = [cfg["model"]] + ([FALLBACK_MODELS[cfg["provider"]]] if FALLBACK_MODELS.get(cfg["provider"]) else [])
    errors: list[str] = []
    result = RunResult(text="", model=cfg["model"], host="google", provider=cfg["provider"])
    parsed = None
    for i, model in enumerate(models):
        if i > 0 and deadline - time.monotonic() < MIN_SECONDS_FOR_FALLBACK:
            break
        result = RunResult(text="", model=model, host="google", provider=cfg["provider"])
        try:
            gen_cfg = types.GenerateContentConfig(
                system_instruction=system, response_mime_type="application/json", response_json_schema=schema,
                thinking_config=types.ThinkingConfig(thinking_level="low") if cfg["provider"] == "gemini" else None)
            t = time.monotonic()
            resp = _google_client(cfg["provider"]).models.generate_content(model=model, contents=prompt, config=gen_cfg)
            result.round_seconds.append(round(time.monotonic() - t, 2))
            result.text = resp.text or ""
            parsed = json.loads(result.text)
            break
        except Exception as e:
            key = os.environ.get("GEMINI_API_KEY") or ""
            errors.append(f"{model}: {type(e).__name__}: {str(e).replace(key, '<key>') if key else e}"[:300])
            log.warning("JSON completion failed: %s", errors[-1])
    if parsed is None:
        result.error = " | ".join(errors) or "no answer"
    result.seconds = round(time.monotonic() - t0, 2)
    return parsed, result


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)

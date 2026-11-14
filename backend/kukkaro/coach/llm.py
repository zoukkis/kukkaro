"""The single LLM interface for Kukkaro (COACH; BUTLER uses it too).

`run(system, history, message, tools, execute, provider=None)` runs the whole tool loop: the model
picks tools, `execute(name, args)` computes them (deterministic Python, never the LLM), the results
go back to the model, until it answers in text. The loop lives here, inside each provider's native
message format, because Gemini's thinking models sign their tool calls and the model's previous
turn must be passed back unchanged.

Providers (`LLM_PROVIDER` in .env, or per request):
- gemini: Google Gen AI SDK, model `GEMINI_MODEL` (default gemini-4-hydrogen), thinking "low".
- gemma:  Stage 1 = Gemma 4 through the same Gemini API and key (`GEMMA_MODEL`); thinking level is
          not supported there, so it is left out. Stage 2 = vLLM on Verda via `GEMMA_BASE_URL`
          (OpenAI-compatible), used whenever it is set.

Privacy design (root AGENTS.md §4): Gemma is the trusted-zone model (it sees customer data); Gemini is
the public-zone research model and the per-turn backup (coach/router.py decides which runs).

Errors and timeouts never raise: the caller gets a friendly fallback text and `error` set.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("kukkaro.llm")

FALLBACK_TEXT = "Sorry, I couldn't reach the coach just now. Please try again in a moment."
MAX_TOOL_ROUNDS = 5
# Seconds per model call and per whole answer. Gemma through Google's API (stage 1) is slower, and
# Google ends a call at our deadline (504), so it gets more room; the UI shows a loading state.
TIMEOUTS = {"gemini": (15, 30), "gemma": (35, 60)}
# Gemma through Google's API (stage 1) often runs into Google's own deadline (504) on longer turns; in the
# privacy design Gemini then answers the turn, so give up sooner instead of making the user wait.
STAGE1_GEMMA_TIMEOUTS = (25, 40)


def timeouts(provider: str) -> tuple[int, int]:
    if provider == "gemma" and not os.environ.get("GEMMA_BASE_URL"):
        return STAGE1_GEMMA_TIMEOUTS
    return TIMEOUTS[provider]
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
    fallback_used: bool = False  # complete_json: the fallback provider answered


def provider_config(provider: str | None = None) -> dict[str, str]:
    p = (provider or os.environ.get("LLM_PROVIDER") or "gemini").strip().lower()
    if p not in ("gemini", "gemma"):
        raise ValueError(f"Unknown provider {p!r}; use gemini or gemma")
    if p == "gemini":
        return {"provider": p, "model": os.environ.get("GEMINI_MODEL") or "gemini-4-hydrogen", "host": "google"}
    if os.environ.get("GEMMA_BASE_URL"):
        # Stage 2: an OpenAI-compatible server (vLLM on Verda). GEMMA_HOST only exists so a test against
        # another OpenAI-compatible endpoint is not labelled "verda".
        return {"provider": p, "model": os.environ.get("GEMMA_MODEL") or "gemma-4-26b-a4b-it",
                "host": os.environ.get("GEMMA_HOST") or "verda"}
    return {"provider": p, "model": os.environ.get("GEMMA_MODEL") or "gemma-4-26b-a4b-it", "host": "google"}


_clients: dict[str, Any] = {}


def _google_client(provider: str):
    if provider not in _clients:
        from google import genai
        from google.genai import types
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _clients[provider] = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=timeouts(provider)[0] * 1000))
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


_THINK = re.compile(r"<(thought|think|thinking)>.*?</\1>", re.DOTALL | re.IGNORECASE)
_CHANNEL = re.compile(r"<\|channel\>.*?<channel\|>", re.DOTALL)  # Gemma 4's own reasoning channel tokens (vLLM)


def strip_thinking(text: str) -> str:
    """Some OpenAI-compatible servers return the model's reasoning inline (<thought>…</thought>, or
    Gemma 4's <|channel>thought…<channel|>). The user must only see the answer; an unclosed block at
    the start is dropped too."""
    text = _CHANNEL.sub("", _THINK.sub("", text))
    if re.match(r"\s*(<(thought|think|thinking)>|<\|channel\>)", text, re.IGNORECASE):
        text = ""  # reasoning that never closed: there is no answer in it
    return text.strip()


def _run_openai(cfg: dict, system: str, history: list[dict], message: str, tools: list[ToolSpec],
                execute: Callable[[str, dict], dict], deadline: float, result: RunResult) -> None:
    """Stage 2: Gemma on vLLM (Verda) through the OpenAI chat-completions API with native tool calls."""
    from openai import OpenAI

    if "openai" not in _clients:
        _clients["openai"] = OpenAI(base_url=os.environ["GEMMA_BASE_URL"], api_key=os.environ.get("GEMMA_API_KEY") or "none",
                                    timeout=TIMEOUTS["gemma"][0], max_retries=0)
    client = _clients["openai"]
    msgs: list[dict] = [{"role": "system", "content": system}]
    msgs += [{"role": "user" if h["role"] == "user" else "assistant", "content": h["content"]} for h in history if h.get("content")]
    msgs.append({"role": "user", "content": message})
    oa_tools = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
                for t in tools]
    nudged = False
    for _ in range(MAX_TOOL_ROUNDS + 2):
        if time.monotonic() > deadline:
            raise TimeoutError("coach took too long")
        t = time.monotonic()
        # A cap on reply length stops runaway reasoning early (then the nudge below asks for the answer).
        resp = client.chat.completions.create(model=cfg["model"], messages=msgs, tools=oa_tools or None,
                                              tool_choice="auto" if oa_tools else None, temperature=0.2,
                                              max_tokens=int(os.environ.get("GEMMA_MAX_TOKENS") or 1500))
        result.round_seconds.append(round(time.monotonic() - t, 2))
        msg = resp.choices[0].message
        if not msg.tool_calls:
            result.text = strip_thinking(msg.content or "")
            if result.text or nudged:
                return
            # Gemma 4 sometimes spends the whole reply on reasoning. Ask once for just the answer.
            nudged = True
            msgs.append({"role": "user", "content": "Reply now with only the final answer for me, under 120 words, "
                                                    "using only the numbers from the tool results. No reasoning."})
            continue
        msgs.append({"role": "assistant", "content": msg.content or "",
                     "tool_calls": [{"id": tc.id, "type": "function",
                                     "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
                                    for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            out = _safe_execute(execute, tc.function.name, args)
            result.tool_calls.append({"name": tc.function.name, "args": args, "result": out})
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(out, ensure_ascii=False, default=str)})
    raise RuntimeError("too many tool rounds")


def run(system: str, history: list[dict], message: str, tools: list[ToolSpec],
        execute: Callable[[str, dict], dict], provider: str | None = None) -> RunResult:
    cfg = provider_config(provider)
    t0 = time.monotonic()
    deadline = t0 + timeouts(cfg["provider"])[1]
    openai_compatible = bool(os.environ.get("GEMMA_BASE_URL")) and cfg["provider"] == "gemma"
    models = [cfg["model"]] + ([FALLBACK_MODELS[cfg["provider"]]] if FALLBACK_MODELS.get(cfg["provider"]) and not openai_compatible else [])
    errors: list[str] = []
    result = RunResult(text="", model=cfg["model"], host=cfg["host"], provider=cfg["provider"])
    for i, model in enumerate(models):
        if i > 0 and deadline - time.monotonic() < MIN_SECONDS_FOR_FALLBACK:
            break
        result = RunResult(text="", model=model, host=cfg["host"], provider=cfg["provider"])
        try:
            backend = _run_openai if openai_compatible else _run_google
            backend({**cfg, "model": model}, system, history, message, tools, execute, deadline, result)
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


def _parse_json(text: str) -> dict:
    t = strip_thinking(text or "")
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t.strip())
    m = re.search(r"\{.*\}", t, re.DOTALL)
    return json.loads(m.group(0) if m else t)


def _complete_json_openai(cfg: dict, system: str, prompt: str, schema: dict) -> tuple[dict | None, RunResult]:
    """Gemma on vLLM (Verda): JSON mode through the OpenAI-compatible API, schema given in the prompt."""
    from openai import OpenAI

    t0 = time.monotonic()
    result = RunResult(text="", model=cfg["model"], host=cfg["host"], provider=cfg["provider"])
    try:
        if "openai" not in _clients:
            _clients["openai"] = OpenAI(base_url=os.environ["GEMMA_BASE_URL"], api_key=os.environ.get("GEMMA_API_KEY") or "none",
                                        timeout=TIMEOUTS["gemma"][0], max_retries=0)
        msgs = [{"role": "system", "content": f"{system}\n\nReply with only one JSON object matching this JSON schema, "
                                              f"no other text:\n{json.dumps(schema)}"},
                {"role": "user", "content": prompt}]
        t = time.monotonic()
        resp = _clients["openai"].chat.completions.create(model=cfg["model"], messages=msgs, temperature=0.2,
                                                          response_format={"type": "json_object"},
                                                          max_tokens=int(os.environ.get("GEMMA_MAX_TOKENS") or 1500))
        result.round_seconds.append(round(time.monotonic() - t, 2))
        result.text = resp.choices[0].message.content or ""
        parsed = _parse_json(result.text)
    except Exception as e:
        key = os.environ.get("GEMMA_API_KEY") or ""
        result.error = f"{cfg['model']}: {type(e).__name__}: {str(e).replace(key, '<key>') if key else e}"[:300]
        log.warning("JSON completion failed: %s", result.error)
        parsed = None
    result.seconds = round(time.monotonic() - t0, 2)
    return parsed, result


def complete_json(system: str, prompt: str, schema: dict, provider: str | None = None,
                  fallback_provider: str | None = None) -> tuple[dict | None, RunResult]:
    """One structured answer (JSON matching `schema`) with no tools; used by the Butler and the research
    worker. Same timeouts and fallback model as `run()`. If it fails and `fallback_provider` is given,
    that provider answers instead (`result.fallback_used`). Returns (parsed JSON or None, RunResult)."""
    parsed, result = _complete_json_one(system, prompt, schema, provider)
    if parsed is None and fallback_provider and fallback_provider != result.provider:
        first_error, first_s = result.error, result.seconds
        parsed, result = _complete_json_one(system, prompt, schema, fallback_provider)
        result.fallback_used = True
        result.seconds = round(first_s + result.seconds, 2)
        log.info("JSON answered by fallback %s after: %s", fallback_provider, first_error)
    return parsed, result


def _complete_json_one(system: str, prompt: str, schema: dict, provider: str | None) -> tuple[dict | None, RunResult]:
    from google.genai import types

    cfg = provider_config(provider)
    if cfg["provider"] == "gemma" and os.environ.get("GEMMA_BASE_URL"):
        return _complete_json_openai(cfg, system, prompt, schema)
    t0 = time.monotonic()
    deadline = t0 + timeouts(cfg["provider"])[1]
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
            parsed = _parse_json(result.text) if cfg["provider"] == "gemma" else json.loads(result.text)
            break
        except Exception as e:
            key = os.environ.get("GEMINI_API_KEY") or ""
            errors.append(f"{model}: {type(e).__name__}: {str(e).replace(key, '<key>') if key else e}"[:300])
            log.warning("JSON completion failed: %s", errors[-1])
    if parsed is None:
        result.error = " | ".join(errors) or "no answer"
    result.seconds = round(time.monotonic() - t0, 2)
    return parsed, result


_MD_BOLD = re.compile(r"(\*\*|__)(.+?)\1", re.DOTALL)
_MD_HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s+")


def plain(text: str) -> str:
    """Answers are shown as plain text in S-mobiili-style bubbles: drop Markdown bold and headings
    (bullets and line breaks stay)."""
    return _MD_HEADING.sub("", _MD_BOLD.sub(r"\2", text or "")).strip()


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)

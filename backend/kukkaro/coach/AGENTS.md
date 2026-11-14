# Workstream COACH — `backend/kukkaro/coach/` and `backend/kukkaro/api/`

Read the root `AGENTS.md` first. You own `coach/`, `api/` (the FastAPI app that mounts every
router), `backend/pyproject.toml`, and `backend/tests/test_coach_*.py`.

## Your job
The conversational coach: the user asks in natural language, the LLM picks tools, the tools return
exact numbers from DATA and RECEIPTS, and the LLM explains them kindly and briefly.

## Deliverables (in order)
1. **`api/main.py`**: FastAPI app with `/api` prefix, CORS for the Vite dev server, `/api/health`.
   Mount every endpoint in root AGENTS.md §5.4:
   - `api/routes_data.py` (you write it): summary, transactions, safe-to-spend, what-if. Thin
     wrappers around `kukkaro.data.metrics`, no logic of their own. The summary endpoint takes
     `?receipts=true|false`: with `true`, grocery spend is split by receipt items into baskets
     (via the RECEIPTS helpers). This powers the With/Without receipts toggle (`docs/WHY_RECEIPTS.md`).
   - `kukkaro.receipts.router` (written by RECEIPTS): the receipt endpoint.
   - `kukkaro.coach.router` (yours): `/api/chat`.
   - `kukkaro.butler.router` (written by BUTLER): `/api/butler`.
2. **`llm.py`**: a single interface
   `chat(messages, tools) -> {text, tool_calls}` with two backends chosen by `LLM_PROVIDER`:
   - `gemini`: Google Gen AI SDK, model from `GEMINI_MODEL`, native function calling.
   - `gemma` (two stages, same tools and prompts):
     - **Stage 1 (now):** Gemma 4 through the **Gemini API with the same `GEMINI_API_KEY`**, model
       from `GEMMA_MODEL` (`gemma-4-26b-a4b-it` or `gemma-4-31b-it`). Same Google Gen AI SDK as
       `gemini`, just a different model name. Use this for development and the Gemini-vs-Gemma eval.
     - **Stage 2 (after M2, for the Verda + EU-privacy story):** self-host Gemma 4 from Hugging Face
       with **vLLM** (`vllm/vllm-openai` image) in a **Verda Serverless Container** in project
       "Kukkaro" (Verda's managed inference has no Gemma). Needs `HF_TOKEN` with the Gemma licence
       accepted. Smallest GPU that fits, scale-to-zero on. Set `GEMMA_BASE_URL` / `GEMMA_API_KEY`;
       when `GEMMA_BASE_URL` is set, call it via the OpenAI-compatible client instead of Stage 1.
     If the model's tool calling is unreliable, use a JSON "tool request" prompt format and parse
     it.
3. **`tools.py`**: wraps `kukkaro.data.metrics` and the receipts insight helpers as LLM tools, with
   precise JSON schemas and descriptions. Tools return dicts; never format numbers inside tools.
4. **`prompts.py`**: the system prompt. Must say:
   - You are Kukkaro, a friendly money coach inside S-mobiili; you teach the three baskets.
   - Every number you mention must come from a tool result in this conversation. If no tool gives
     it, say you don't know.
   - Mention the period and basket for every figure. Keep answers under ~120 words, with one
     concrete next step.
   - Receipt-based insights must say they come from synthetic example receipts.
   - No investment, loan or product recommendations; no moving money.
5. **`router.py`**: `POST /api/chat` per §5.4, returning `tool_calls` (name + args) and `figures`
   (the exact numbers used) so the UI can show "how I got this".
6. **Eval script** `coach/eval.py`: 15 fixed questions for `DEMO_CUSTOMER_ID`. The first four are
   S-Bank's own, verbatim: "Where did my money go?", "What kind of spender am I?", "What can I
   safely spend this week?", "How could I save more?". Then others (taxis last month,
   what kind of spender am I, safe to spend this week, halve energy drinks, store-brand savings…).
   Check that every number in each answer appears in the tool outputs. Run it with both providers
   and log the results in DECISIONS.md. This is the evidence for "Gemini vs. Gemma" in the pitch.

## Privacy design (decided 14 Nov; root AGENTS.md §4)
- `router.py`: Gemma (`TRUSTED_PROVIDER`) answers every turn; Gemini (`FALLBACK_PROVIDER`) only after
  Gemma failed (error, timeout, or number check) and one retry. A slow failure (> 20 s) skips the retry.
  The response carries `zones`, `fallback`, `trusted_host`, `research[]`, `sources[]`; `GET /api/chat/stats`
  counts trusted vs fallback turns. No `provider` field in the request any more (no model picker).
- `tools.py`: `research_web(question)` is the only way to outside facts. `Executor` remembers every tool
  result so the gateway can block a question that repeats one of the customer's exact figures.
- `privacy.py`: the gateway's checks, `banded_context()` (region + age band), `REFUSAL_TEXT`.
- The number check also reads web facts ("1,19 €"); an answer naming another grocery chain is retried.
- `eval.py` (default `--provider privacy`) reports the Gemma-vs-fallback rate.

## Stretch (only after the M2 milestone in docs/PLAN.md)
- `POST /api/receipt-scan`: Gemini vision reads a photographed paper receipt into the Receipt
  schema, **in memory only, never stored or logged**. Demo with a receipt handed over on the spot.

## Rules
- The LLM never computes. Sums, averages and percentages all come from tools.
- Timeouts plus a friendly fallback message on LLM errors. The demo must not hang.
- Don't edit `data/`, `receipts/`, `butler/` or `web/` code. Ask via DECISIONS.md if a tool you
  need is missing.

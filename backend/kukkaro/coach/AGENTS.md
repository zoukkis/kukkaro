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
     wrappers around `kukkaro.data.metrics`, no logic of their own.
   - `kukkaro.receipts.router` (written by RECEIPTS): the receipt endpoint.
   - `kukkaro.coach.router` (yours): `/api/chat`.
   - `kukkaro.butler.router` (written by BUTLER): `/api/butler`.
2. **`llm.py`**: a single interface
   `chat(messages, tools) -> {text, tool_calls}` with two backends chosen by `LLM_PROVIDER`:
   - `gemini`: Google Gen AI SDK, model from `GEMINI_MODEL`, native function calling.
   - `gemma`: OpenAI-compatible endpoint (`GEMMA_BASE_URL`, `GEMMA_API_KEY`, `GEMMA_MODEL`).
     Verda's managed inference has **no Gemma** (checked 14 Nov), so we self-host: a **Verda
     Serverless Container** running **vLLM** (`vllm/vllm-openai` image) serving a Gemma model from
     Hugging Face. Needs a Hugging Face token with the Gemma licence accepted. Pick the smallest GPU
     that fits, and enable scale-to-zero so idle time costs nothing. Until that endpoint exists,
     develop against Gemma through the Gemini API key (Google AI Studio serves Gemma models too).
     If the model's tool calling is unreliable, use a JSON "tool request" prompt format and parse
     it. Same tools, same answers.
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
6. **Eval script** `coach/eval.py`: 15 fixed questions for `DEMO_CUSTOMER_ID` (taxis last month,
   what kind of spender am I, safe to spend this week, halve energy drinks, store-brand savings…).
   Check that every number in each answer appears in the tool outputs. Run it with both providers
   and log the results in DECISIONS.md. This is the evidence for "Gemini vs. Gemma" in the pitch.

## Stretch (only after the M2 milestone in docs/PLAN.md)
- `POST /api/receipt-scan`: Gemini vision reads a photographed paper receipt into the Receipt
  schema, **in memory only, never stored or logged**. Demo with a receipt handed over on the spot.

## Rules
- The LLM never computes. Sums, averages and percentages all come from tools.
- Timeouts plus a friendly fallback message on LLM errors. The demo must not hang.
- Don't edit `data/`, `receipts/`, `butler/` or `web/` code. Ask via DECISIONS.md if a tool you
  need is missing.

# Kukkaro: an AI money coach for S-mobiili

Built at **Junction 2026** (Espoo, 13–15 Nov 2026) by team Sisu Warriors. MIT licensed.

**Live demo:** https://135.181.63.207.compute.verda.run (open on a phone; synthetic demo customer)

**System design:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

> All data in this project is **synthetic**: S-Bank's synthetic transaction dataset, plus receipt
> line items we generate ourselves. No real personal or banking data is used.

## What it does
- **Chat with your money.** Ask anything; every number comes from deterministic queries on your
  data, and the AI only explains it.
- **Three baskets.** Mandatory-regular, mandatory-irregular, and everyday spending that slips
  through your fingers.
- **Receipt-level insight.** Splits a grocery payment into essentials and leaks (synthetic receipts
  that mirror S-mobiili's receipt archive).
- **What-if, safe-to-spend, store-brand savings.**
- **Kukkaro Butler.** Finds benefits, fair prices and your rights on the live web with Exa, always with sources.
- **EU privacy mode.** The same coach on the open-weight Gemma model, hosted on Verda in Europe.

## Quick start
```bash
cp .env.example .env            # fill in keys
# put the S-Bank CSVs into data/raw/ (see data/README.md)
cd backend && pip install -e . && python -m kukkaro.data.prepare
uvicorn kukkaro.api.main:app --reload
cd ../web && npm install && npm run dev
```

## For the judges

### S-Pankki: Personal Economic Trainer
- **The four questions from S-Bank's brief, one tap away:** where did my money go, what kind of
  spender am I, what can I safely spend this week, how could I save more. The coach answers in plain
  language; every number comes from deterministic queries (`kukkaro/data/metrics.py`) and "How I got
  this" shows the source. The LLM never computes a number: an answer with a number no tool produced is
  retried, then withheld (`coach/numbers.py`).
- **Teaching angle:** S-Bank's three baskets (🏠 Regular essentials, 🔧 Unexpected necessities,
  ☕ Everyday spending) are visible everywhere. **Receipts** split a grocery payment into essentials and
  everyday treats: for the demo customer, €200.75 of everyday spending was hidden inside €611.16 of
  groceries in September. Try the **With / Without receipts** toggle (`docs/WHY_RECEIPTS.md`).
- **Bank-like Home:** account card, coming-up bills before payday, recent transactions; grocery rows
  open the (synthetic) receipt.
- **Feasibility and S-mobiili fit:** a mobile web view that S-mobiili can embed. In production only
  the bottom layer changes: the bank's own transactions and the receipt archive S-mobiili already has,
  behind the existing `ReceiptProvider` interface (`docs/PRODUCTION_PATH.md`).

### Exa: The Internet Butler
- **For whom:** young adults and anyone facing a money question the bank data can't answer: "Why did
  my utility bill double?", "Can I get housing allowance?", "Is my rent increase allowed?".
- **How Exa is used:** search + contents for current facts, preferring official sources (Kela,
  Vero, Energy Authority, Finnish consumer authorities); one cited source per fact, shown under the
  answer; next-step checklist and an optional draft message; the user makes the final call.
- **Privacy:** only an anonymised question leaves the trusted zone (gateway in `coach/privacy.py`).
- **Watchlist:** save a Butler question ("Watch this") and Kukkaro re-checks it with Exa (the question
  again + pages published since the last check), diffs the sources in code, and speaks up only when they change.
- **Live:** works on questions the judges type; Butler eval: 3/3 demo tasks and 10/10 unseen phrasings
  (incl. Finnish). Code: `backend/kukkaro/butler/`.

### Gemini API
- **Gemini answers the public side:** it turns Exa's pages into a short sourced answer in the Butler
  (`butler/research.py`), and it is the backup coach when the open model fails, so the demo never stops.
- **Function calling over deterministic finance tools:** the coach calls tools such as
  `safe_to_spend`, `spending_summary`, `what_if`, `item_what_if` and never computes numbers itself.
- Eval (`coach/eval.py`, 15 questions on CUST02979): Gemini 15/15, no invented numbers.

### Gemma + Verda
- **Gemma 4 (26B A4B, open weights) is the trusted model:** it is the only model that sees the
  customer's transactions, and it runs on **Verda in Finland** (Serverless Container, vLLM, 1× RTX PRO
  6000 96 GB, OpenAI-compatible endpoint).
- **Eval, same 15 questions, same tools:** Gemma 4 on Verda **15/15**, median ~2 s (vs Gemini 15/15,
  median 6.8 s; Gemma via Google's API 14/15, median 15 s). Numbers retried 0, withheld 0.
- **Verda products used:** Serverless Containers for Gemma (GPU, OpenAI-compatible, scales by
  replicas); a CPU/GPU instance for the public demo (Caddy + uvicorn, deployed with
  `deploy/deploy_demo.sh` in ~5 min).
- **Path to scale:** more container replicas for live chat, and a nightly batch over all customers
  (e.g. a monthly digest per customer, checked by the same number checker) on the same endpoint.
- Process log, measurements and failures: `docs/DECISIONS.md`.

## Privacy design
One assistant, and the models are split by **who may see what data**, not by feature:

| Zone | Who | Sees | Does |
|---|---|---|---|
| Trusted | Gemma 4 (open model; on Verda in the EU when `GEMMA_BASE_URL` is set) | your transactions, through deterministic tools | answers, explains, decides when outside facts are needed |
| Gateway | code (`coach/privacy.py`) | one outgoing question | blocks IDs, postal codes, exact amounts and ages, names, emails, phone numbers; one rewrite, else nothing is sent |
| Public | Exa + Gemini (`butler/research.py`) | only that anonymised question and web pages | finds current facts, one source per fact |

What leaves: one general question such as "Is a monthly utility bill around 140 € high in the Espoo region?".
Why: personal finance data should stay with the model you can host yourself, while the open web is
searched without knowing who asks. If Gemma fails, Gemini answers that turn and the answer says
"Backup model used". Every number still comes from a tool or a cited source.

## Third-party models
Gemma 4 is an open-weight model released by Google under the Apache 2.0 licence; we still follow
Google's Gemma prohibited-use policy as good practice. Kukkaro is a coach, not a licensed financial or
legal advisor, and makes no automated decisions about anyone. Not affiliated with or endorsed by
Google, S-Bank or S-Group.

## Repo layout
See `AGENTS.md` §4. Process log: `docs/DECISIONS.md`.

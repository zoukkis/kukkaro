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
_TODO (Sunday): 3–5 lines: the three baskets, how it fits S-mobiili, feasibility._

### Exa: The Internet Butler
_TODO: the 3 demo tasks, how Exa is used (search + contents, official domains), where the code lives (`backend/kukkaro/butler/`)._

### Gemini API
_TODO: function calling over deterministic finance tools; why Gemini._

### Gemma + Verda
_TODO: the EU privacy mode; the Gemini vs. Gemma eval results (coach/eval.py); the Verda products used and why; batch precompute over 5,100 customers; path to scale._

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
Gemma is provided under and subject to the Gemma Terms of Use found at ai.google.dev/gemma/terms
(use restrictions: ai.google.dev/gemma/prohibited_use_policy). Kukkaro is a coach, not a licensed
financial or legal advisor, and makes no automated decisions about anyone. Not affiliated with or
endorsed by Google, S-Bank or S-Group.

## Repo layout
See `AGENTS.md` §4. Process log: `docs/DECISIONS.md`.

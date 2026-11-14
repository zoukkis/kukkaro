# Kukkaro: an AI money coach for S-mobiili

Built at **Junction 2026** (Espoo, 13–15 Nov 2026) by team Sisu Warriors. MIT licensed.

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

## Third-party models
Gemma is provided under and subject to the Gemma Terms of Use found at ai.google.dev/gemma/terms
(use restrictions: ai.google.dev/gemma/prohibited_use_policy). Kukkaro is a coach, not a licensed
financial or legal advisor, and makes no automated decisions about anyone. Not affiliated with or
endorsed by Google, S-Bank or S-Group.

## Repo layout
See `AGENTS.md` §4. Process log: `docs/DECISIONS.md`.

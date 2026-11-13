# AGENTS.md — Kukkaro (Junction 2026)

You are an AI coding agent working on **Kukkaro**, a hackathon project built at Junction 2026
(Espoo, 13–15 Nov 2026) by team **Sisu Warriors**. Read this whole file before doing anything.
Then read the `AGENTS.md` inside the folder you were asked to work in. Those two files are your
complete brief. If a task is not covered by them, **stop and ask the human** instead of guessing.

## 1. What we are building (one paragraph)

Kukkaro is a mobile-first AI money coach meant to live inside S-Bank's **S-mobiili** app. A user
chats with their own transaction data ("How much did I spend on taxis last month?", "What is safe
to spend this week?"). Spending is sorted into S-Bank's **three baskets**: mandatory-regular,
mandatory-irregular, and everyday spending that slips through your fingers. Because the real
S-mobiili already stores purchase receipts, we add a **synthetic receipt layer** so one grocery trip
can be split into essentials vs. leaks at product level. A second feature, **Kukkaro Butler**, uses
the **Exa** search API to find money the user is missing (benefits, better deals, unfair bills),
always with sources.

## 2. Where we compete (each needs visible proof in the demo)

| Submission | Type | What judges look for |
|---|---|---|
| **Kukkaro** → Personal Economic Trainer (S-Pankki) | Main challenge | Financial literacy and the three-baskets teaching angle, originality of the AI, clarity of the mobile UX, feasibility, fit with S-mobiili (20% each) |
| **Kukkaro Butler** → The Internet Butler (Exa) | Main challenge | Exa finds info a model cannot know, usefulness, clear sources, originality, works on judges' own live queries (20% each) |
| Best Use of Gemini API | Tech challenge (on Kukkaro) | Gemini is essential, not a bolt-on |
| Best Use of Gemma | Tech challenge (on Kukkaro) | Open model used meaningfully |
| Verda Compute Track | Tech challenge (on Kukkaro) | Ambition, right Verda product, working and documented, path to scale (25% each) |

## 3. Junction rules you must never break (disqualification risk)

1. **All code is written during the event** (from Fri 13 Nov 19:30). Never paste in code from a
   project that existed before the event. Open-source libraries via package managers are fine.
2. **Everything is MIT-licensed and the repo will be public.** Never commit secrets, API keys,
   tokens, personal data or the raw dataset.
3. **No real personal or financial data, ever.** Use only: S-Bank's synthetic dataset, synthetic
   data we generate (clearly labelled), and public open data (e.g. Statistics Finland). Never scrape
   or export anything from the real S-mobiili, Kela accounts, banks or anyone's receipts.
4. Not tied to any existing company or product of ours.

## 4. Architecture (decided — do not change without the human's approval)

```
kukkaro/
├── AGENTS.md  CLAUDE.md  GEMINI.md  README.md  LICENSE  .env.example  .gitignore
├── docs/          PLAN.md, COMPLIANCE.md, DECISIONS.md (log), VIDEO.md
├── data/          raw/ and processed/ are gitignored; only README.md is committed
├── backend/       Python 3.11+, FastAPI, DuckDB
│   └── kukkaro/
│       ├── data/       loading, DuckDB views, baskets, metrics   (workstream DATA)
│       ├── receipts/   synthetic receipt generator + provider     (workstream RECEIPTS)
│       ├── coach/      LLM client, tools, prompts, /chat          (workstream COACH)
│       ├── butler/     Exa agent, /butler                         (workstream BUTLER)
│       └── api/        FastAPI app, wires routers together        (owned by COACH)
└── web/           React + Vite + TypeScript, mobile-first        (workstream WEB)
```

**Core principle: the LLM never does arithmetic and never invents numbers.** Every number shown
to the user comes from a deterministic Python function (a "tool") that queries DuckDB. The LLM
chooses tools, then explains the results in plain language. If a tool cannot answer, the LLM
says so.

**LLM providers** (switch with `LLM_PROVIDER` in `.env`):
- `gemini` (default): Gemini API with function calling. Also used for receipt-photo reading (stretch).
- `gemma` ("EU privacy mode"): Gemma open-weight model self-hosted with vLLM in a **Verda**
  Serverless Container (OpenAI-compatible). Same tools, same prompts.

## 5. Shared contracts (all workstreams depend on these — change only via docs/DECISIONS.md + human OK)

### 5.1 Dataset (S-Bank, synthetic, in `data/raw/`, read with encoding `utf-8-sig`)
- `tx_junction_transactions.csv` (~346 MB, Git LFS): `customer_id, bank_account_id, tx_date,
  tx_timestamp, category, tx_amount_eur, balance_after_eur, transaction_type, merchant_id, mcc_code`
- `tx_customers_junction.csv` (5,100 rows): `customer_id, customer_postal_code, customer_age`
- `mtg_negotiation_history.csv`, `mtg_tx_customer_link_and_final_mtg_infio.csv`: mortgage
  applications for 200 customers. **Stretch only**, do not build on them unless the human asks.

DuckDB views (created by DATA in `kukkaro/data/db.py`): `transactions`, `customers`,
`tx_enriched` (= transactions + `basket` column + `tx_id`).
`tx_id` = stable string `"{customer_id}-{row_number}"` assigned once when converting to Parquet.

### 5.2 Baskets (exact enum values)
`MANDATORY_REGULAR` (rent, utilities, insurance, loans, subscriptions),
`MANDATORY_IRREGULAR` (repairs, appliances, healthcare, car service, annual fees),
`EVERYDAY` (the leaks: coffee, snacks, takeaway, taxis, impulse buys), plus `INCOME` and `TRANSFER`
for non-spending rows. Mapping lives in `kukkaro/data/baskets.py` only.

### 5.3 Receipt (JSON, produced by `ReceiptProvider.get_receipt(tx_id)`)
```json
{
  "tx_id": "CUST00042-1187",
  "store": "S-market (synthetic)",
  "timestamp": "2026-05-03T17:42:00",
  "total_eur": 47.10,
  "synthetic": true,
  "items": [
    {"name": "Lactose-free milk 1 l", "category": "dairy", "qty": 2,
     "unit_price_eur": 1.39, "line_total_eur": 2.78, "basket": "MANDATORY_REGULAR",
     "store_brand": false}
  ]
}
```
Invariant: `sum(line_total_eur) == total_eur` to the cent. `synthetic` is always `true` in this project.

### 5.4 HTTP API (FastAPI, prefix `/api`, JSON)
| Method & path | Returns |
|---|---|
| `GET /api/customers/{id}/summary?month=YYYY-MM` | totals per basket, top categories, income, balance |
| `GET /api/customers/{id}/transactions?limit=&offset=&basket=` | paged `tx_enriched` rows |
| `GET /api/transactions/{tx_id}/receipt` | Receipt (5.3) or 404 if not a grocery purchase |
| `GET /api/customers/{id}/safe-to-spend` | `{amount_eur, until_date, explanation_inputs}` |
| `POST /api/customers/{id}/what-if` | body `{category_or_item, change_pct}` → `{monthly_eur, yearly_eur}` |
| `POST /api/chat` | body `{customer_id, message, history[]}` → `{answer, tool_calls[], figures[]}` |
| `POST /api/butler` | body `{customer_id, task}` → `{answer, sources[{title,url}], next_steps[]}` |

Every response that contains synthetic receipt data must include `"synthetic": true` so the UI can label it.

### 5.5 Demo customer
`DEMO_CUSTOMER_ID` in `.env`. DATA picks one customer whose data tells a clear story (regular rent,
visible "everyday" leaks, some irregular expense) and writes the reasoning in docs/DECISIONS.md.

## 6. How to work

- **Stay in your folder.** Only edit files in the workstream folder you were assigned (see its
  AGENTS.md). Need a change elsewhere? Write it in `docs/DECISIONS.md` under "Requests" and tell
  your human. Do not "quickly fix" another workstream's code.
- **Smallest thing that works end to end.** A working demo beats unfinished features. No
  speculative abstractions, no extra frameworks, no new dependencies without a one-line reason in
  DECISIONS.md.
- **Git:** work on branch `ws/<workstream>`; pull `main` often; open small PRs; `main` must always run.
  Commit messages: `<workstream>: <what>`.
- **Secrets:** read keys from environment variables only (`.env`, see `.env.example`). Never print
  keys in logs, never hardcode them, never commit `.env`.
- **Tests:** each workstream keeps a few fast tests in `backend/tests/` (pytest) for its own code,
  especially numeric correctness. Run them before pushing.
- **Log decisions:** append to `docs/DECISIONS.md` (date, who, decision, why). This doubles as the
  "lessons/process log" Verda requires.

## 7. Product rules (apply to every user-facing string)

- Kukkaro is a **coach**, not an advisor: it explains and suggests, it never recommends specific
  investments, loans or financial products, and never moves money.
- Plain, friendly language. English UI is fine; Finnish touches welcome.
- Always show where a number came from (which period, which basket). Butler always shows source links.
- Anything synthetic is visibly labelled "synthetic example data".

## 8. Out of scope — do NOT build

Login or auth, real bank connections or PSD2, native iOS or Android apps, payment features,
investment advice, multi-language i18n framework, admin panels, complex deployment
(Kubernetes etc.), the mortgage features (unless the human asks), anything not in docs/PLAN.md.

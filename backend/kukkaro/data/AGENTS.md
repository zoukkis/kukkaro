# Workstream DATA — `backend/kukkaro/data/`

Read the root `AGENTS.md` first. You own **only** this folder plus `backend/tests/test_data_*.py`
and `data/README.md`.

## Your job
Turn S-Bank's synthetic CSVs into fast, correct numbers that every other workstream can trust.

## Deliverables (in order)
1. **`prepare.py`** (CLI: `python -m kukkaro.data.prepare`): reads `data/raw/*.csv` with
   `encoding="utf-8-sig"`, converts to Parquet in `data/processed/`, assigns `tx_id`
   (`"{customer_id}-{row_number}"`, stable and deterministic). First check that
   `tx_junction_transactions.csv` is real data and not a Git LFS pointer (a file starting with
   `version https://git-lfs`); if it is, print how to download it (see `data/README.md`) and exit.
2. **`db.py`**: `get_conn()` returns a DuckDB connection with views `transactions`, `customers`,
   `tx_enriched` over the Parquet files.
3. **Profile the data before mapping it.** Write `docs/DATA_PROFILE.md` (allowed outside your folder):
   distinct `category`, `transaction_type` and top `mcc_code` values with counts, date range,
   sign convention of `tx_amount_eur` (are expenses negative?), and how income shows up. Base every
   later decision on this file, not on assumptions.
4. **`baskets.py`**: `assign_basket(category, mcc_code, transaction_type, amount) -> Basket` using the
   enum values in root AGENTS.md §5.2. Use an explicit mapping table plus a short comment on each
   rule. Detect recurring payments (same merchant, similar amount, ~monthly) as `MANDATORY_REGULAR`.
5. **`metrics.py`**, pure functions over DuckDB, used as LLM tools by COACH. Each returns a plain dict:
   - `spending_summary(customer_id, start, end)`: per basket, per category, totals
   - `category_spend(customer_id, category, start, end)`
   - `merchant_spend(customer_id, merchant_id, start, end)`
   - `safe_to_spend(customer_id, today)`: balance minus expected mandatory-regular outflows before
     the next income, divided by the days left. Return its inputs too so the UI can explain it.
   - `what_if(customer_id, category, change_pct)`: monthly and yearly impact from the last 3 months' average
   - `spender_profile(customer_id)`: shares per basket vs. the median of customers of the same age band
   - `recurring_payments(customer_id)`
6. **Pick `DEMO_CUSTOMER_ID`**: a customer with regular rent, clear everyday leaks, at least one
   irregular expense and enough grocery transactions for receipts. Log the choice and why in
   `docs/DECISIONS.md`.

## "Today" in a synthetic dataset
The data ends on some fixed date. Every time-relative metric ("this week", "last month") uses
`get_today()`: the `DEMO_TODAY` env value if set, otherwise the latest `tx_date` in the dataset.
Never use the real system date.

## Rules
- Numbers must be correct to the cent. Write pytest checks for each metric against a hand-computed
  example on a tiny fixture.
- Every metric runs on one customer in under 300 ms (index or filter by `customer_id` first).
- No LLM calls in this folder. No web requests.
- Do not edit `coach/`, `receipts/`, `butler/`, `api/` or `web/`.
- Open data benchmarks (Statistics Finland) are allowed later. Store any downloaded file in
  `data/raw/open/` with its source URL in `data/README.md`.

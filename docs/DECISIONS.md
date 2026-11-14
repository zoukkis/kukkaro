# Decisions and process log

This is our process log. Verda's minimum requirement is documenting the process, and the
summary we post to their Discord is built from this file. Append, never rewrite. Format: `YYYY-MM-DD HH:MM · who · decision · why`.

## Decisions
- 2026-11-14 00:30 · team · Architecture per AGENTS.md §4: FastAPI + DuckDB backend, React/Vite web, Gemini default, Gemma on Verda as EU privacy mode · fits S-Bank, Gemini, Gemma and Verda judging at once
- 2026-11-14 00:30 · team · LLM never computes numbers; deterministic tools only · trust and correctness in a finance app
- 2026-11-14 00:30 · team · Synthetic receipt layer behind a `ReceiptProvider` interface · the dataset has no line items; the real S-mobiili archive would plug in later

- 2026-11-14 11:40 · Konsta · S-Bank presenter liked the synthetic receipt idea; brief slides add 4 must-answer questions and basket labels (now in AGENTS.md) · direct sponsor feedback

- 2026-11-14 11:50 · Konsta · S-Bank: no good-enough reason found yet to combine S-Group and bank data → our pitch must prove it; added docs/WHY_RECEIPTS.md and the With/Without receipts toggle as the key demo moment · sponsor's open problem = our differentiator

- 2026-11-14 11:55 · Konsta · Receipt contract adds optional `channel` (in_store | online_order) + `delivery_fee_eur`, mirroring S-mobiili's web-shop order history; synthetic, labelled · enables planned-vs-impulse insight

- 2026-11-14 12:10 · Jusef (DATA) · Basket mapping by category + MCC, table in docs/DATA_PROFILE.md: Groceries, Housing, Utilities, fuel and public transport = Regular essentials; Health, Home & Tech = Unexpected necessities; Restaurants, Entertainment, Lifestyle, Travel, taxis (MCC 4121), parking (7523) = Everyday spending; Invest Deposit/Withdraw, Salary Sweep = Transfers · based on the data profile; card data cannot split a grocery trip, receipts can
- 2026-11-14 12:10 · Jusef (DATA) · The recurring-merchant rule does not reclassify anything: the profile finds no recurring purchases (no subscriptions in the data). `recurring_payments()` reports bills by category instead · a rule that never fires would only add risk
- 2026-11-14 12:10 · Jusef (DATA) · Added `subcategory` (from MCC) to `tx_enriched`; `category_spend` and `what_if` accept categories, subcategories and everyday words ("taxi", "takeaway", "rent") · "taxis" is an MCC inside Transportation, not a category
- 2026-11-14 12:10 · Jusef (DATA) · `tx_id` = `{customer_id}-{n}` in file order; `prepare.py` verifies the running balance chains in that order on all 3.6M rows · stable IDs for receipts
- 2026-11-14 12:10 · Jusef (DATA) · Data is loaded into in-memory DuckDB on the first `get_conn()` (about 5 s); each metric then takes 10–80 ms per customer. `spender_profile` takes about 0.6 s on its first call (age-band medians, then cached) · meets the 300 ms target after warm-up
- 2026-11-14 12:10 · Jusef (DATA) · Demo customer **CUST02979** (22, Espoo 02360). Without receipts they look average (everyday 30.0% of spending vs 26.7% median for ages 18-24), but groceries are their largest category (611.16 € in 9 trips in Sep), so receipts reveal hidden leaks: the With/Without story. Safe to spend is tight but positive (127.05 € this week); utilities rose from a typical 65.70 € to 144.73 € in Sep (+120.3%) for the Butler; taxis 90.76 € in Aug; rent paid all 24 months. Runner-up CUST03538 (24, everyday 48.4% vs 26.7%). `DEMO_TODAY` stays empty = 2026-09-30, the last date in the data · tells S-Bank's four questions and the receipts story on one customer
- 2026-11-14 · WEB · Web stack: Vite + React + TypeScript, plain CSS, no other runtime deps; mock/real API switched by `VITE_USE_MOCK` in `web/src/api.ts` · backend not ready yet, so the switch is one flag

## Requests between workstreams
(Format: `from → to · what is needed · status`)
- DATA → COACH · `backend/pyproject.toml` needs `duckdb` (core), `python-dotenv` (DATA reads `DATA_DIR`/`DEMO_TODAY` from `.env`) and `pytest`. Until it exists, run tests with `cd backend && python -m pytest` · open
- DATA → COACH · Metrics raise `kukkaro.data.metrics.DataError` (user-safe message: unknown customer or category, bad dates). Tools should return `{"error": message}`, and routes should return 404 or 422. Call `get_conn()` and `spender_profile(DEMO_CUSTOMER_ID)` once at startup to warm up. `month_bounds("2026-09")` turns `?month=` into start and end · open
- DATA → RECEIPTS · Grocery rows = `category = 'Groceries'` (4 MCCs; 13,012 rows have no merchant/MCC). Skip or cap implausible trips (68 above 20× the median, largest 15,902 €). The demo persona CUST02979 should have clear leak habits (9 trips, 611.16 € in Sep) · open
- DATA → BUTLER · `recurring_payments()` gives typical vs latest month with `change_pct` (utilities +120.3% for the demo customer) and the salary pattern; `customer_profile()` gives age, age band and postal code. Rent never rises in the data, so "my rent went up" must come from the user's own words · open
- DATA → all · Set `DEMO_CUSTOMER_ID=CUST02979` in your `.env` · open
- WEB → COACH/DATA · Web runs on mock data in `web/src/api.ts` until the API exists. Please return these shapes (or tell WEB what differs): summary `{customer_id, month, income_eur, spending_eur, balance_eur, baskets[{basket, total_eur, share_pct, tx_count}], top_categories[{category, basket, total_eur}]}` (only the 3 spending baskets in `baskets`; `share_pct` computed in the backend); transactions `{items[tx_enriched row], total, limit, offset}`; chat `tool_calls[{name, args}]`, `figures[{label, value, unit: "EUR"|"%"|"count", source}]`, optional `model` (for the privacy toggle). Dev proxy expects the API on `localhost:8000` · open
- WEB → COACH · DATA's `spending_summary` uses different names than the WEB summary shape: `spent_eur`→`total_eur`, `transactions`→`tx_count`, top category `name`→`category`, `spending_total_eur`→`spending_eur`, and `period` instead of `month`. Please map these in the `/summary` route (or tell WEB to adopt DATA's names). Transactions should include `subcategory` (the web shows it, e.g. "Taxis"). WEB mock now uses CUST02979 / 2026-09 · open

## Lessons / failures
- 2026-11-14 12:10 · Jusef (DATA) · Profiling before mapping overturned three assumptions in the brief: taxis are an MCC inside Transportation (not a category), there are no subscriptions or recurring merchants, and rent never really rises (±10%). `transaction_type` values are snake_case (`housing_payment`), and 5% of purchases have no merchant or MCC

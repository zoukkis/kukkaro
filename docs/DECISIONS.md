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

## Requests between workstreams
(Format: `from → to · what is needed · status`)

## Lessons / failures

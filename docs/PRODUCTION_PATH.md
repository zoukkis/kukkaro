# From hackathon demo to S-mobiili: the production data path

The demo uses only S-Bank's synthetic dataset and synthetic receipts (see `AGENTS.md` §3).
This page explains how the same code would get **real** data in production, without changing
the coach, the baskets or the privacy boundary. Nothing here is built in the hackathon: real bank
connections and PSD2 are out of scope on purpose (`AGENTS.md` §8).

## The two inputs Kukkaro needs

| Input | Demo (now) | Production inside S-mobiili | Production outside S-Bank (alternative) |
| --- | --- | --- | --- |
| Card transactions | S-Bank synthetic CSV → DuckDB (`kukkaro/data`) | S-Bank's own transaction data, read inside the bank | PSD2 *Account and Transaction* API, with the customer's consent |
| Grocery receipts (line items) | `SyntheticReceiptProvider` (deterministic, labelled `synthetic: true`) | The receipt archive S-mobiili already offers, opt-in per user | Not available through PSD2 (receipts are retail data, not bank data) |

Only the bottom layer changes. Everything above it stays as it is:

```
            ┌──────────────────────────────────────────────────────┐
            │  Web UI (S-mobiili WebView) · coach · Butler          │  unchanged
            ├──────────────────────────────────────────────────────┤
            │  metrics.py · baskets.py · receipts/insights.py       │  unchanged
            ├───────────────────────────┬──────────────────────────┤
            │  Transaction source        │  ReceiptProvider          │  ← swap here
            │  demo: synthetic CSV       │  demo: Synthetic…         │
            │  prod: bank data / PSD2    │  prod: receipt archive    │
            └───────────────────────────┴──────────────────────────┘
```

## Why this is feasible

- **The seam already exists in code.** `kukkaro/receipts/provider.py` defines a `ReceiptProvider`
  protocol (`get_receipt(tx_id)`). Production adds one class, e.g. `ArchiveReceiptProvider`, that
  reads the S-mobiili receipt archive; the insights, the baskets and the With/Without toggle do
  not change. Transactions already arrive in the shape of `tx_enriched` (§5.1), which maps directly
  onto standard account-transaction fields (date, amount, merchant, MCC).
- **S-Bank already publishes open banking APIs.** Public open banking directories list S-Pankki
  APIs for payment initiation, confirmation of funds, and account and transactions, with a
  developer portal at crosskey.io. Strong customer authentication runs through the S-mobiili app.
  Inside S-mobiili, Kukkaro would not need PSD2 at all: it would run on the bank's own data.
- **Receipts are the part only S-Group can do.** PSD2 gives any fintech the card rows, but not
  what was in the basket. Combining the bank row with the S-Group receipt is the unique part (see
  `docs/WHY_RECEIPTS.md`).

## Consent and privacy in production

- Receipts are **opt-in per user**, off by default, revocable, and used only for the user's own
  coaching (no marketing profiling, no credit decisions).
- Third-party (PSD2) access always needs the customer's explicit consent, given through the bank.
- The privacy boundary does not change: customer data stays in the trusted zone (Gemma on EU
  infrastructure), and only the anonymised question passes the code gateway (`coach/privacy.py`)
  to web research.

## What a pilot would add (not in the demo)

1. `ArchiveReceiptProvider` against a test copy of the receipt archive.
2. A transaction source that reads the bank's own data (or the PSD2 sandbox for an external pilot).
3. A consent screen in S-mobiili with the receipts preview ("with receipts you'd see…").
4. The pilot metrics in `docs/WHY_RECEIPTS.md`.

## Sources

- [Open Banking Tracker: S-Pankki APIs](https://openbankingtracker.com/provider/s-pankki/apis) (directory listing; checked 15 Nov 2026)
- [Enable Banking: open banking specifics in Finland](https://enablebanking.com/docs/markets/fi/) (S-Pankki uses S-mobiili for authentication)

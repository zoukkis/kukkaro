# Workstream RECEIPTS — `backend/kukkaro/receipts/`

Read the root `AGENTS.md` first. You own **only** this folder plus `backend/tests/test_receipts_*.py`.

## Why this exists
The real S-mobiili app already stores purchase receipts, but S-Bank's hackathon dataset has no
line items. We generate **synthetic** receipts that look like that archive, so the coach can split
one grocery payment into essentials vs. leaks. In production the generator would be swapped for the
real receipt archive. That swap is the point of the provider interface.

## Deliverables (in order)
1. **`models.py`**: Pydantic models exactly matching the Receipt JSON in root AGENTS.md §5.3.
2. **`provider.py`**:
   ```python
   class ReceiptProvider(Protocol):
       def get_receipt(self, tx_id: str) -> Receipt | None: ...
   class SyntheticReceiptProvider: ...   # the only implementation we build
   ```
   Add a docstring explaining that a production `SMobiiliReceiptProvider` would read the user's
   consented receipt archive instead. Do **not** implement it.
3. **`catalog.csv`** is **owned by person C, not by the agent.** Only create a ~20-row placeholder
   if it doesn't exist yet, so you can work. Never overwrite C's version. Spec for C: 150–300 Finnish grocery products written at the event. Columns:
   `name, category, unit_price_eur, basket, store_brand, typical_qty`. Prices must be realistic
   for Finland in 2026. Mark leak items (`energy drink`, `candy`, `pastry`, `chips`, `coffee to go`…)
   as `EVERYDAY`; staples as `MANDATORY_REGULAR`. Include store-brand twins for ~30 common items.
4. **`generator.py`**: `generate(tx_row, persona) -> Receipt`
   - Only for grocery transactions (`category` "Groceries" / MCC 5411, confirm in `docs/DATA_PROFILE.md`).
   - **Deterministic**: seed the RNG with `tx_id`, so the same transaction always gets the same receipt.
   - **Persona-consistent**: `persona = make_persona(customer_id, age)`, seeded by `customer_id`,
     fixes stable habits (e.g. buys energy drinks 3×/week, prefers oat milk, buys store brand or
     not). Habits must repeat across weeks so the coach can find real-looking patterns.
   - Items must sum **exactly** to `abs(tx_amount_eur)`. Fill with items, then fix the remainder with
     a final weighted item or a quantity tweak. Never leave a mismatch.
5. **Insights helpers** (pure functions, used as COACH tools):
   - `item_spend(customer_id, item_or_category, start, end)`
   - `leak_items(customer_id, start, end)`: top `EVERYDAY` items by euros
   - `store_brand_savings(customer_id, months=3)`: what switching to store-brand twins would save per year
   - `personal_inflation(customer_id)`: price change of the user's repeated items. Only if the
     generator models a price drift over time; otherwise skip and say so in DECISIONS.md.

6. **`router.py`**: FastAPI router for `GET /api/transactions/{tx_id}/receipt` (root AGENTS.md §5.4).
   Return 404 for non-grocery transactions. COACH mounts it in `api/main.py`.

## Rules
- Every receipt has `"synthetic": true` and a store name ending in `(synthetic)`.
- No real receipts, no scraping, no real S-Group product data dumps. The catalogue is hand-made
  (an LLM can draft it; a human checks the prices).
- Tests: the sum invariant over 1,000 random transactions; determinism (same `tx_id` → identical
  receipt); persona habits recur.
- Do not edit `data/`, `coach/`, `butler/`, `api/`, `web/`. Read data only through `kukkaro.data.db`.

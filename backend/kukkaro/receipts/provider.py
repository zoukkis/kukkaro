"""Where receipts come from.

We only build `SyntheticReceiptProvider`. In production a `SMobiiliReceiptProvider` would read the
receipt archive that S-mobiili already keeps, for users who have opted in (consent), and return the
same `Receipt` objects, so nothing else in Kukkaro changes. It is deliberately NOT implemented here.
"""
from __future__ import annotations

from typing import Protocol

from kukkaro.data.db import get_conn
from kukkaro.receipts.generator import generate, make_persona
from kukkaro.receipts.models import Receipt

TX_SQL = """SELECT t.tx_id, t.customer_id, t.tx_date, t.tx_timestamp, t.category, t.tx_amount_eur,
                   t.merchant_id, t.mcc_code, c.customer_age
            FROM transactions t JOIN customers c USING (customer_id)"""


class ReceiptProvider(Protocol):
    def get_receipt(self, tx_id: str) -> Receipt | None: ...


def _row(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


class SyntheticReceiptProvider:
    """Generated receipts for Groceries purchases (synthetic, labelled as such)."""

    def get_receipt(self, tx_id: str) -> Receipt | None:
        rows = _row(get_conn().execute(TX_SQL + " WHERE t.tx_id = ?", [tx_id]))
        if not rows:
            return None
        tx = rows[0]
        return generate(tx, make_persona(tx["customer_id"], tx["customer_age"]))

    def grocery_receipts(self, customer_id: str, start, end) -> tuple[list[Receipt], list[dict]]:
        """All grocery transactions of a customer in a period: (receipts, transactions without one)."""
        rows = _row(get_conn().execute(
            TX_SQL + " WHERE t.customer_id = ? AND t.category = 'Groceries' AND t.tx_amount_eur < 0"
                     " AND t.tx_date BETWEEN ? AND ? ORDER BY t.tx_id", [customer_id, start, end]))
        receipts, without = [], []
        persona = make_persona(customer_id, rows[0]["customer_age"]) if rows else None
        for tx in rows:
            r = generate(tx, persona)
            (receipts.append(r) if r else without.append(tx))
        return receipts, without


provider: ReceiptProvider = SyntheticReceiptProvider()

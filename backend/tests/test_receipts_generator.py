"""Generator tests that need no database: exact sums, determinism, recurring habits, the 300 € rule."""
from __future__ import annotations

import random
from collections import Counter
from datetime import datetime

from kukkaro.receipts.generator import catalog, generate, make_persona


def tx(tx_id: str, amount: str, category: str = "Groceries", mcc: str | None = "5411") -> dict:
    return {"tx_id": tx_id, "tx_amount_eur": amount, "tx_timestamp": datetime(2026, 9, 16, 17, 42),
            "category": category, "merchant_id": "MRC-GRO-0035", "mcc_code": mcc}


def cents(x: float) -> int:
    return int(round(x * 100))


def test_items_always_sum_exactly_to_the_card_amount():
    rng = random.Random(7)
    persona = make_persona("CUST00001", 34)
    for i in range(1000):
        amount = f"-{rng.randint(1, 30000) / 100:.2f}"
        r = generate(tx(f"CUST00001-{i}", amount), persona)
        assert r is not None
        assert sum(cents(it.line_total_eur) for it in r.items) + cents(r.delivery_fee_eur) == cents(r.total_eur)
        assert cents(r.total_eur) == cents(-float(amount))
        assert r.synthetic is True and r.store.endswith("(synthetic)") and r.channel == "in_store"


def test_same_transaction_gives_the_identical_receipt():
    p = make_persona("CUST00042", 25)
    a = generate(tx("CUST00042-1187", "-47.10"), p)
    b = generate(tx("CUST00042-1187", "-47.10"), make_persona("CUST00042", 25))
    assert a.model_dump() == b.model_dump()
    assert make_persona("CUST00042", 25) == p


def test_persona_habits_recur_across_trips():
    p = make_persona("CUST00777", 23)
    counts = Counter()
    trips = 40
    for i in range(trips):
        r = generate(tx(f"CUST00777-{i}", "-55.00"), p)
        counts.update({it.name for it in r.items if it.basket == "EVERYDAY"})
    top_item, n = counts.most_common(1)[0]
    assert top_item in p.favourite_leaks
    assert n >= trips * 0.3  # the favourite leak shows up again and again
    assert set(counts) <= set(p.favourite_leaks)


def test_no_receipt_for_big_trips_refunds_or_other_categories():
    p = make_persona("CUST00001", 40)
    assert generate(tx("CUST00001-1", "-300.01"), p) is None
    assert generate(tx("CUST00001-2", "12.00"), p) is None
    assert generate(tx("CUST00001-3", "-20.00", category="Restaurants", mcc="5812"), p) is None
    assert generate(tx("CUST00001-4", "-300.00"), p) is not None


def test_demo_customer_has_clear_leak_habits():
    p = make_persona("CUST02979", 22)
    assert p.favourite_leaks[0] == "Energy drink 0.5 l"


def test_catalog_is_consistent():
    cat = catalog()
    assert len(cat) >= 80
    for prod in cat.values():
        assert prod.basket in {"MANDATORY_REGULAR", "MANDATORY_IRREGULAR", "EVERYDAY"}
        assert prod.price_cents > 0
        if prod.twin:
            assert prod.twin in cat and cat[prod.twin].store_brand
            assert cat[prod.twin].price_cents < prod.price_cents

"""Insights on the DATA fixture (needs duckdb): the split must match the card data to the cent."""
from __future__ import annotations

import pytest
from test_data_fixture import data_env  # noqa: F401  (pytest fixture)

from kukkaro.data import metrics
from kukkaro.receipts import insights

SEP = ("2026-09-01", "2026-09-30")


def test_basket_split_matches_card_groceries_and_merges(data_env):
    split = insights.basket_split("C1", *SEP)
    # C1 September groceries: 60 + 40 = 100 € (two trips, both get a receipt)
    assert split["grocery_total_eur"] == 100.00
    assert split["without_receipt_eur"] == 0.00
    assert round(sum(p["total_eur"] for p in split["split"]) + split["without_receipt_eur"], 2) == 100.00
    summary = metrics.spending_summary("C1", *SEP)
    merged = metrics.merge_grocery_split(summary, split)  # raises if anything doesn't add up
    assert merged["spending_total_eur"] == summary["spending_total_eur"]
    assert merged["synthetic"] is True


def test_receipt_endpoint_logic(data_env):
    from kukkaro.receipts.provider import provider
    split_ids = [r.tx_id for r in provider.grocery_receipts("C1", *SEP)[0]]
    assert len(split_ids) == 2
    r = provider.get_receipt(split_ids[0])
    assert r is not None and r.synthetic
    housing = metrics.transactions_page("C1", basket="MANDATORY_REGULAR", month="2026-09")["transactions"]
    rent = next(t for t in housing if t["category"] == "Housing")
    assert provider.get_receipt(rent["tx_id"]) is None


def test_other_insights_run(data_env):
    assert insights.leak_items("C1", *SEP)["synthetic"] is True
    assert insights.item_spend("C1", "milk", *SEP)["query"] == "milk"
    s = insights.store_brand_savings("C1", months=3)
    assert s["yearly_saving_eur"] == pytest.approx(s["monthly_saving_eur"] * 12, abs=0.01)

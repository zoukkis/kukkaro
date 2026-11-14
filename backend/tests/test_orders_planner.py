"""Concept demo: planned grocery order (receipts faked so the arithmetic is checked by hand)."""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from test_data_fixture import data_env  # noqa: F401  (pytest fixture)

from kukkaro.data import metrics
from kukkaro.orders import planner
from kukkaro.receipts.models import Receipt, ReceiptItem


def item(name, qty, price, basket="MANDATORY_REGULAR"):
    return ReceiptItem(name=name, category="x", qty=qty, unit_price_eur=price, line_total_eur=round(qty * price, 2),
                       basket=basket, store_brand=False)


def receipt(day, items):
    total = round(sum(i.line_total_eur for i in items), 2)
    return Receipt(tx_id=f"C1-{day}", store="S-market (synthetic)", timestamp=datetime(2026, 8, day, 12).isoformat(), total_eur=total,
                   synthetic=True, items=items)


# Jul-Sep window = 92 days. Milk on 4 trips (13 l in total), bread on 3, energy drinks on 3 (26 cans),
# candy on only 2 trips (not usual), veg by weight on 3 trips (6.5 kg).
RECEIPTS = [
    receipt(1, [item("Milk 1 l", 4, 1.15), item("Toast bread 500 g", 1, 1.99), item("Energy drink 0.5 l", 9, 1.99, "EVERYDAY"),
                item("Vegetables & fruit (by weight)", 2.0, 3.49)]),
    receipt(8, [item("Milk 1 l", 3, 1.15), item("Toast bread 500 g", 1, 1.99), item("Energy drink 0.5 l", 9, 1.99, "EVERYDAY"),
                item("Pick-and-mix candy 200 g", 2, 2.40, "EVERYDAY"), item("Vegetables & fruit (by weight)", 2.5, 3.49)]),
    receipt(15, [item("Milk 1 l", 3, 1.15), item("Toast bread 500 g", 2, 2.09), item("Energy drink 0.5 l", 8, 1.99, "EVERYDAY"),
                 item("Pick-and-mix candy 200 g", 1, 2.40, "EVERYDAY"), item("Vegetables & fruit (by weight)", 2.0, 3.49)]),
    receipt(22, [item("Milk 1 l", 3, 1.15)]),
]


@pytest.fixture
def fake_receipts(data_env, monkeypatch):
    monkeypatch.setattr(planner._provider, "grocery_receipts", lambda cid, s, e: (RECEIPTS, []))


def test_plan_usual_week(fake_receipts):
    p = planner.plan_grocery_order("C1")
    lines = {i["name"]: (i["qty"], i["unit_price_eur"], i["line_total_eur"]) for i in p["items"]}
    # milk 13 l x 7 / 92 = 0.99 -> 1 pc; bread 4 x 7 / 92 -> 1 (min 1) at the latest price 2.09;
    # veg 6.5 kg x 7 / 92 = 0.49 -> 0.5 kg (minimum) x 3.49 = 1.745 -> 1.75
    assert lines == {"Milk 1 l": (1.0, 1.15, 1.15), "Toast bread 500 g": (1.0, 2.09, 2.09),
                     "Vegetables & fruit (by weight)": (0.5, 3.49, 1.75)}
    # treats: energy drinks 26 x 7 / 92 = 1.98 -> 2 cans = 3.98; candy only on 2 trips -> not usual
    assert [(t["name"], t["qty"], t["line_total_eur"]) for t in p["left_out"]] == [("Energy drink 0.5 l", 2.0, 3.98)]
    assert p["items_total_eur"] == 4.99 and p["treats_per_week_eur"] == 3.98
    # robot fee 3.90 (example) -> 8.89; C1's safe to spend this week on 30 Sep is 2836.40
    assert (p["delivery"]["fee_eur"], p["order_total_eur"]) == (3.9, 8.89)
    assert (p["safe_to_spend_this_week_eur"], p["left_this_week_after_order_eur"], p["fits_this_week"]) == (2836.4, 2827.51, True)
    assert p["synthetic"] and p["concept"] and "nothing is ordered or paid" in p["note"]


def test_treats_and_delivery_options(fake_receipts):
    p = planner.plan_grocery_order("C1", include_treats=True, delivery="pickup")
    assert p["items_total_eur"] == 8.97 and p["order_total_eur"] == 8.97 and p["left_out"] == []
    with pytest.raises(metrics.DataError):
        planner.plan_grocery_order("C1", delivery="drone")


def test_approval_is_simulated_and_checks_the_plan(fake_receipts):
    p = planner.plan_grocery_order("C1")
    ok = planner.approve_order("C1", p["plan_id"], False, "robot")
    assert ok["status"] == "approved_simulation" and ok["order_ref"].startswith("DEMO-") and ok["order_total_eur"] == 8.89
    with pytest.raises(metrics.DataError):
        planner.approve_order("C1", p["plan_id"], True, "robot")    # a different basket than the one reviewed


def test_routes_and_coach_tool(fake_receipts):
    from kukkaro.api.main import app
    from kukkaro.coach.tools import SPECS, executor
    assert "plan_grocery_order" in [s.name for s in SPECS]
    assert executor("C1")("plan_grocery_order", {})["order_total_eur"] == 8.89
    with TestClient(app) as c:
        p = c.get("/api/customers/C1/grocery-order").json()
        r = c.post("/api/customers/C1/grocery-order/approve", json={"plan_id": p["plan_id"]})
        assert r.status_code == 200 and r.json()["status"] == "approved_simulation"
        assert c.post("/api/customers/C1/grocery-order/approve", json={"plan_id": "abcdef"}).status_code == 422
        assert c.get("/api/customers/NOPE/grocery-order").status_code == 404


# ---------- Store-brand swaps and Butler products (real S-kaupat pages; prices parsed in code) ----------
from kukkaro.butler import products  # noqa: E402

PAGE = "https://www.s-kaupat.fi/tuote/rainbow-paahtoleipa-500g/6414890000000"


def test_product_from_page_reads_price_and_picture(data_env):
    p = products.from_page("Rainbow paahtoleipä 500 g | S-kaupat ruoan verkkokauppa", PAGE,
                           "# Rainbow paahtoleipä\n\nn. Noin 1,19 €\n\n2,38 €/kg Vertailuhinta", "https://cdn.s-cloud.fi/x.webp",
                           replaces="Toast bread 500 g")
    assert (p["name"], p["price_eur"], p["own_brand"], p["image"]) == ("Rainbow paahtoleipä 500 g", 1.19, True, "https://cdn.s-cloud.fi/x.webp")
    assert products.get(p["id"])["replaces"] == "Toast bread 500 g"
    assert products.from_page("Some article", "https://www.s-ryhma.fi/uutiset/x", "Noin 1,00 €", None) is None
    assert products.parse_price("no price here") is None and products.get("../etc/passwd") is None
    assert products._size("Store brand oat drink 1 l") == products._size("Rainbow kaurajuoma 1L") == "1l"


def test_swap_replaces_the_branded_line_and_extras_are_added(fake_receipts):
    swap = products.from_page("Rainbow paahtoleipä 500 g", PAGE, "n. Noin 1,19 €", None, replaces="Toast bread 500 g")
    extra = products.from_page("Rainbow kaurajuoma 1L", "https://www.s-kaupat.fi/tuote/rainbow-kaurajuoma-1l/1", "n. Noin 1,05 €", None)
    p = planner.plan_grocery_order("C1", swaps=[swap["id"]], extras=[extra["id"]])
    lines = {i["name"]: i for i in p["items"]}
    assert "Toast bread 500 g" not in lines
    bread = lines["Rainbow paahtoleipä 500 g"]
    assert (bread["qty"], bread["line_total_eur"], bread["swapped_from"], bread["swapped_from_eur"]) == (1.0, 1.19, "Toast bread 500 g", 2.09)
    assert lines["Rainbow kaurajuoma 1L"]["added"] == "butler" and lines["Rainbow kaurajuoma 1L"]["line_total_eur"] == 1.05
    # 4.99 - 2.09 + 1.19 + 1.05 = 5.14; + robot 3.90 = 9.04
    assert (p["items_total_eur"], p["order_total_eur"]) == (5.14, 9.04)
    assert p["swaps"] == [swap["id"]] and p["extras"] == [extra["id"]]
    ok = planner.approve_order("C1", p["plan_id"], False, "robot", [extra["id"]], [swap["id"]])
    assert ok["order_total_eur"] == 9.04
    with pytest.raises(metrics.DataError):   # approving without the reviewed extras is a different order
        planner.approve_order("C1", p["plan_id"], False, "robot")
    with pytest.raises(metrics.DataError):   # unknown or unpriced products are never added
        planner.plan_grocery_order("C1", extras=["0123456789ab"])


def test_order_routes_take_products_by_id_only(fake_receipts):
    from kukkaro.api.main import app
    extra = products.from_page("Rainbow kaurajuoma 1L", "https://www.s-kaupat.fi/tuote/rainbow-kaurajuoma-1l/1", "n. Noin 1,05 €", None)
    with TestClient(app) as c:
        p = c.get(f"/api/customers/C1/grocery-order?extra={extra['id']}").json()
        assert p["order_total_eur"] == 9.94 and p["extras"] == [extra["id"]]
        r = c.post("/api/customers/C1/grocery-order/approve", json={"plan_id": p["plan_id"], "extras": [extra["id"]]})
        assert r.status_code == 200 and r.json()["order_total_eur"] == 9.94
        assert c.get("/api/customers/C1/grocery-order?extra=nope").status_code == 422


def test_swaps_join_receipt_savings_with_real_products(data_env, monkeypatch):
    from kukkaro.orders import swaps
    import kukkaro.receipts.insights as insights
    monkeypatch.setattr(insights, "store_brand_savings", lambda cid: {
        "start": "2026-07-01", "end": "2026-09-30", "months": 3, "monthly_saving_eur": 4.0, "yearly_saving_eur": 48.0,
        "top_swaps": [{"item": "Toast bread 500 g", "store_brand_twin": "Store brand toast bread 500 g", "saving_in_period_eur": 10.0, "qty": 12}]})
    monkeypatch.setattr(products, "own_brand_for", lambda twin, item: {"id": "abc", "name": "Rainbow paahtoleipä", "price_eur": 1.19})
    s = swaps.swaps("C1")
    assert s["swaps"][0]["monthly_saving_eur"] == 3.33 and s["swaps"][0]["product"]["name"] == "Rainbow paahtoleipä"
    assert s["synthetic"] and "S-kaupat" in s["note"]

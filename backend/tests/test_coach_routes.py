"""The /api data routes on the hand-made fixture (numbers worked out in test_data_metrics.py)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_data_fixture import data_env  # noqa: F401  (pytest fixture)


@pytest.fixture(scope="module")
def client(data_env):
    from kukkaro.api.main import app
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health").json()
    assert r["status"] == "ok" and r["data_loaded"] is True and r["today"] == "2026-09-30"


def test_summary_uses_web_names(client):
    r = client.get("/api/customers/C1/summary", params={"month": "2026-09"})
    assert r.status_code == 200
    s = r.json()
    assert (s["month"], s["spending_eur"], s["income_eur"], s["balance_eur"], s["tx_count"]) == ("2026-09", 1120.5, 2500.0, 6928.0, 10)
    # Regular in Sep: housing, utilities, groceries 40 and 60, transport without MCC = 5 rows, 960 €
    assert s["baskets"][0] == {"basket": "MANDATORY_REGULAR", "label": "Regular essentials", "total_eur": 960.0,
                               "share_pct": 85.7, "tx_count": 5}
    assert [b["basket"] for b in s["baskets"]] == ["MANDATORY_REGULAR", "MANDATORY_IRREGULAR", "EVERYDAY"]
    assert s["top_categories"][0] == {"category": "Housing", "basket": "MANDATORY_REGULAR", "total_eur": 800.0, "tx_count": 1}
    assert s["receipts"] is None


def test_summary_defaults_to_month_of_today(client):
    assert client.get("/api/customers/C1/summary").json()["month"] == "2026-09"


@pytest.mark.parametrize("path, params, status", [
    ("/api/customers/NOPE/summary", {}, 404),
    ("/api/customers/C1/summary", {"month": "2026-13"}, 422),
    ("/api/customers/NOPE/transactions", {}, 404),
    ("/api/customers/C1/transactions", {"basket": "FOO"}, 422),
    ("/api/customers/C1/transactions", {"limit": 0}, 422),
    ("/api/customers/NOPE/safe-to-spend", {}, 404),
])
def test_errors(client, path, params, status):
    r = client.get(path, params=params)
    assert r.status_code == status
    assert "detail" in r.json()


def test_transactions_page_newest_first_with_month(client):
    r = client.get("/api/customers/C1/transactions", params={"month": "2026-09", "limit": 3}).json()
    assert (r["total"], r["limit"], r["offset"]) == (10, 3, 0)
    first = r["items"][0]
    assert (first["tx_date"], first["category"], first["subcategory"], first["tx_amount_eur"], first["basket"]) == \
        ("2026-09-26", "Transportation", "Transportation", -10.0, "MANDATORY_REGULAR")
    assert first["merchant_id"] is None and first["tx_id"] == "C1-28"
    assert [i["tx_date"] for i in r["items"]] == ["2026-09-26", "2026-09-25", "2026-09-21"]


def test_transactions_basket_filter(client):
    r = client.get("/api/customers/C1/transactions", params={"basket": "EVERYDAY"}).json()
    assert r["total"] == 8   # 4 taxis + 4 restaurant visits
    assert {i["subcategory"] for i in r["items"]} == {"Taxis", "Eating places"}


def test_safe_to_spend_is_data_unchanged(client):
    r = client.get("/api/customers/C1/safe-to-spend").json()
    assert (r["amount_eur"], r["this_week_eur"], r["per_day_eur"], r["until_date"]) == (6078.0, 2836.4, 405.2, "2026-10-15")
    assert r["explanation_inputs"]["regular_essentials_still_expected_eur"] == 850.0


def test_what_if(client):
    r = client.post("/api/customers/C1/what-if", json={"category_or_item": "restaurants", "change_pct": -50})
    assert r.status_code == 200
    j = r.json()
    assert (j["monthly_eur"], j["yearly_eur"], j["baseline_monthly_eur"]) == (-7.75, -93.0, 15.5)


@pytest.mark.parametrize("body, status", [
    ({"category_or_item": "coffee", "change_pct": -50}, 422),   # unknown category: DataError lists known names
    ({"category_or_item": "taxis", "change_pct": -150}, 422),   # below -100
    ({"change_pct": -50}, 422),
])
def test_what_if_errors(client, body, status):
    assert client.post("/api/customers/C1/what-if", json=body).status_code == status


def test_summary_with_receipts(client, monkeypatch):
    import sys
    import types as pytypes
    fake = pytypes.ModuleType("kukkaro.receipts.insights")
    fake.basket_split = lambda cid, start, end: {
        "grocery_total_eur": 100.0, "without_receipt_eur": 0.0,
        "split": [{"basket": "MANDATORY_REGULAR", "total_eur": 70.0}, {"basket": "EVERYDAY", "total_eur": 30.0}],
        "top_leak_items": [{"name": "Energy drink 0.5 l", "total_eur": 12.0, "qty": 6}]}
    monkeypatch.setitem(sys.modules, "kukkaro.receipts.insights", fake)
    s = client.get("/api/customers/C1/summary", params={"month": "2026-09", "receipts": "true"}).json()
    assert [b["total_eur"] for b in s["baskets"]] == [930.0, 120.0, 70.5] and s["spending_eur"] == 1120.5
    assert s["synthetic"] is True and s["receipts"]["top_leak_items"][0]["name"] == "Energy drink 0.5 l"


def test_summary_receipts_unavailable_is_503(client, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "kukkaro.receipts.insights", None)   # import fails
    r = client.get("/api/customers/C1/summary", params={"month": "2026-09", "receipts": "true"})
    assert r.status_code == 503


def test_rate_limit_on_llm_posts(client, monkeypatch):
    from kukkaro.api import main
    monkeypatch.setattr(main, "RATE_LIMITS", {"/api/customers/C1/what-if": (2, 600)})
    main._hits.clear()
    body = {"category_or_item": "restaurants", "change_pct": -50}
    codes = [client.post("/api/customers/C1/what-if", json=body).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert client.get("/api/customers/C1/safe-to-spend").status_code == 200   # GETs are never limited
    monkeypatch.setenv("RATE_LIMIT", "0")
    assert client.post("/api/customers/C1/what-if", json=body).status_code == 200
    main._hits.clear()


def test_built_web_app_is_served_at_root(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient as TC
    from kukkaro.api.main import mount_web
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}
    assert mount_web(app, tmp_path) is False                     # nothing built: nothing mounted
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>Kukkaro</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    assert mount_web(app, tmp_path) is True
    c = TC(app)
    assert "Kukkaro" in c.get("/").text and c.get("/assets/app.js").status_code == 200
    assert c.get("/api/ping").json() == {"ok": True}             # API routes still win

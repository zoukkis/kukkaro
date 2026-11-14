"""Upcoming payments: a forecast composed from safe_to_spend and recurring_payments (stubbed here)."""
from kukkaro.data import metrics, upcoming

STS = {
    "today": "2026-09-30", "until_date": "2026-10-15", "amount_eur": 272.27, "this_week_eur": 127.05,
    "explanation_inputs": {
        "regular_essentials_still_expected_eur": 825.0,
        "regular_essentials": [
            {"name": "Housing", "typical_monthly_eur": 480.0, "paid_since_salary_eur": 0.0, "still_expected_eur": 480.0},
            {"name": "Utilities", "typical_monthly_eur": 145.0, "paid_since_salary_eur": 0.0, "still_expected_eur": 145.0},
            {"name": "Insurance", "typical_monthly_eur": 30.0, "paid_since_salary_eur": 30.0, "still_expected_eur": 0.0},
            {"name": "Groceries", "typical_monthly_eur": 300.0, "paid_since_salary_eur": 100.0, "still_expected_eur": 200.0},
        ],
    },
}
REC = {"recurring": [
    {"name": "Housing", "category": "Housing", "change_pct": 1.0, "last_payment_date": "2026-09-02"},
    {"name": "Utilities", "category": "Utilities", "change_pct": 120.3, "last_payment_date": "2026-09-05"},
]}


def test_upcoming_payments(monkeypatch):
    monkeypatch.setattr(metrics, "safe_to_spend", lambda c, t=None: STS)
    monkeypatch.setattr(metrics, "recurring_payments", lambda c, t=None: REC)
    r = upcoming.upcoming_payments("CUST02979")
    assert [i["name"] for i in r["items"]] == ["Housing", "Utilities"]  # paid ones dropped, sorted by date
    housing, util = r["items"]
    assert housing["expected_around"] == "2026-10-02" and housing["rising"] is False
    assert util["expected_around"] == "2026-10-05" and util["rising"] is True and util["expected_eur"] == 145.0
    assert r["other_essentials_eur"] == 200.0 and r["other_essentials"] == ["Groceries"]
    assert r["total_expected_eur"] == 825.0 and r["left_after_eur"] == 272.27 and r["estimated"] is True


def test_date_outside_window_is_hidden(monkeypatch):
    rec = {"recurring": [{"name": "Housing", "category": "Housing", "change_pct": None, "last_payment_date": "2026-07-01"}]}
    monkeypatch.setattr(metrics, "safe_to_spend", lambda c, t=None: STS)
    monkeypatch.setattr(metrics, "recurring_payments", lambda c, t=None: rec)
    r = upcoming.upcoming_payments("X")
    assert [i["name"] for i in r["items"]] == ["Housing"]  # no recurring stream for Utilities -> "other"
    assert r["items"][0]["expected_around"] is None and r["items"][0]["rising"] is False
    assert r["other_essentials"] == ["Utilities", "Groceries"] and r["other_essentials_eur"] == 345.0

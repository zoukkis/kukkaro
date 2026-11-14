"""Every metric against numbers worked out by hand from tests/test_data_fixture.py."""
from __future__ import annotations

from datetime import date

import pytest
from test_data_fixture import data_env  # noqa: F401  (pytest fixture)

from kukkaro.data import metrics as m

SEP = ("2026-09-01", "2026-09-30")


def basket(result, key):
    return next(b for b in result["baskets"] if b["basket"] == key)


def test_get_today_defaults_to_last_date(data_env, monkeypatch):
    assert m.get_today() == date(2026, 9, 30)
    monkeypatch.setenv("DEMO_TODAY", "2026-09-14")
    assert m.get_today() == date(2026, 9, 14)


def test_spending_summary_september(data_env):
    r = m.spending_summary("C1", *SEP)
    # Regular: housing 800 + utilities 50 + groceries 40 + 60 + transport without MCC 10 = 960
    # Irregular: doctor 120. Everyday: taxi 25 + restaurant 15.50 = 40.50. Total 1120.50
    assert r["spending_total_eur"] == 1120.50
    assert basket(r, "MANDATORY_REGULAR")["spent_eur"] == 960.00
    assert basket(r, "MANDATORY_IRREGULAR")["spent_eur"] == 120.00
    assert basket(r, "EVERYDAY")["spent_eur"] == 40.50
    # 960 / 1120.5 = 85.68 %, 120 / 1120.5 = 10.71 %, 40.5 / 1120.5 = 3.61 %
    assert [b["share_pct"] for b in r["baskets"]] == [85.7, 10.7, 3.6]
    assert basket(r, "MANDATORY_REGULAR")["label"] == "Regular essentials"
    assert r["income_eur"] == 2500.00
    assert r["transfers_out_eur"] == 100.00 and r["transfers_in_eur"] == 0.0
    assert r["transactions"] == 10
    # Opening 1000; Jun-Aug each +1549.50 -> 5648.50; Sep +1279.50 -> 6928.00 (last row 26 Sep)
    assert r["balance_eur"] == 6928.00 and r["balance_date"] == "2026-09-26"
    top = [(c["name"], c["basket"], c["spent_eur"]) for c in r["top_categories"]]
    assert top == [("Housing", "MANDATORY_REGULAR", 800.0), ("Health", "MANDATORY_IRREGULAR", 120.0),
                   ("Groceries", "MANDATORY_REGULAR", 100.0), ("Utilities", "MANDATORY_REGULAR", 50.0),
                   ("Taxis", "EVERYDAY", 25.0), ("Restaurants", "EVERYDAY", 15.5),
                   ("Transportation", "MANDATORY_REGULAR", 10.0)]


def test_spending_summary_empty_period(data_env):
    r = m.spending_summary("C1", "2026-05-01", "2026-05-31")
    assert r["spending_total_eur"] == 0.0 and r["transactions"] == 0
    assert [b["share_pct"] for b in r["baskets"]] == [0.0, 0.0, 0.0]
    assert r["balance_eur"] is None


def test_category_spend_taxis_by_word(data_env):
    r = m.category_spend("C1", "taxi", "2026-06-01", "2026-09-30")
    assert (r["name"], r["level"]) == ("Taxis", "subcategory")
    assert r["spent_eur"] == 100.00 and r["transactions"] == 4 and r["average_per_transaction_eur"] == 25.00
    assert r["baskets"] == [{"basket": "EVERYDAY", "label": "Everyday spending", "spent_eur": 100.0}]
    assert [x["spent_eur"] for x in r["by_month"]] == [25.0, 25.0, 25.0, 25.0]


def test_category_spend_split_category(data_env):
    r = m.category_spend("C1", "Transportation", "2026-06-01", "2026-09-30")
    # taxis 4 x 25 = 100 (everyday) + one transport purchase without MCC 10 (regular)
    assert r["spent_eur"] == 110.00 and r["level"] == "category"
    assert {b["basket"]: b["spent_eur"] for b in r["baskets"]} == {"EVERYDAY": 100.0, "MANDATORY_REGULAR": 10.0}


def test_category_spend_unknown_lists_known_names(data_env):
    with pytest.raises(m.DataError) as e:
        m.category_spend("C1", "coffee", *SEP)
    assert "Taxis" in str(e.value) and "Groceries" in str(e.value)


def test_merchant_spend(data_env):
    r = m.merchant_spend("C1", "MRC-GRO-0001", "2026-06-01", "2026-09-30")
    assert r["spent_eur"] == 240.00 and r["transactions"] == 4
    assert (r["first_date"], r["last_date"]) == ("2026-06-16", "2026-09-16")
    assert r["subcategory"] == "Grocery stores" and r["basket"] == "MANDATORY_REGULAR"


def test_what_if_halve_restaurants(data_env):
    # Last 3 complete months on 30 Sep: Jul-Sep. Restaurants 15.50 a month.
    r = m.what_if("C1", "restaurants", -50, today="2026-09-30")
    assert r["baseline_monthly_eur"] == 15.50
    assert r["monthly_change_eur"] == -7.75 and r["yearly_change_eur"] == -93.00
    assert r["new_monthly_eur"] == 7.75
    assert r["based_on"] == {"start": "2026-07-01", "end": "2026-09-30", "months": 3}


def test_what_if_rounds_monthly_first(data_env):
    # Groceries Jul-Sep: 60 + 60 + 100 = 220 -> 73.33 a month; -10 % -> -7.33; yearly = -7.33 x 12 = -87.96
    r = m.what_if("C1", "groceries", -10, today="2026-09-30")
    assert (r["baseline_monthly_eur"], r["monthly_change_eur"], r["yearly_change_eur"]) == (73.33, -7.33, -87.96)


def test_what_if_mid_month_uses_previous_complete_months(data_env):
    r = m.what_if("C1", "taxis", 20, today="2026-09-14")
    assert r["based_on"] == {"start": "2026-06-01", "end": "2026-08-31", "months": 3}
    assert (r["baseline_monthly_eur"], r["monthly_change_eur"], r["yearly_change_eur"]) == (25.0, 5.0, 60.0)


def test_what_if_rejects_below_minus_100(data_env):
    with pytest.raises(m.DataError):
        m.what_if("C1", "taxis", -101)


def test_safe_to_spend_after_payday(data_env):
    r = m.safe_to_spend("C1", today="2026-09-30")
    x = r["explanation_inputs"]
    assert x["balance_eur"] == 6928.00
    assert (x["last_salary_date"], r["until_date"], x["days_until_salary"]) == ("2026-09-15", "2026-10-15", 15)
    still = {e["name"]: (e["typical_monthly_eur"], e["paid_since_salary_eur"], e["still_expected_eur"]) for e in x["regular_essentials"]}
    # Housing and utilities were paid before the 15 Sep salary, so a full month is still expected.
    # Groceries: typical 73.33, but 40 (same day, after salary) + 60 already paid -> nothing more expected.
    assert still == {"Housing": (800.0, 0.0, 800.0), "Utilities": (50.0, 0.0, 50.0),
                     "Groceries": (73.33, 100.0, 0.0), "Transportation": (3.33, 10.0, 0.0)}
    assert x["regular_essentials_still_expected_eur"] == 850.00
    # 6928 - 850 = 6078; / 15 days = 405.20 a day; this week 405.20 x 7 = 2836.40
    assert (r["amount_eur"], r["per_day_eur"], r["this_week_eur"], r["status"]) == (6078.00, 405.20, 2836.40, "ok")


def test_safe_to_spend_day_before_payday(data_env):
    r = m.safe_to_spend("C1", today="2026-09-14")
    x = r["explanation_inputs"]
    # Balance after 10 Sep utilities: 5648.50 - 800 - 50 = 4798.50. Everything already paid since 15 Aug.
    assert x["balance_eur"] == 4798.50 and x["regular_essentials_still_expected_eur"] == 0.0
    assert (r["until_date"], x["days_until_salary"], x["days_in_this_week"]) == ("2026-09-15", 1, 1)
    assert (r["amount_eur"], r["per_day_eur"], r["this_week_eur"]) == (4798.50, 4798.50, 4798.50)


def test_safe_to_spend_month_end_payer(data_env):
    r = m.safe_to_spend("C2", today="2026-09-30")
    assert r["until_date"] == "2026-10-31" and r["explanation_inputs"]["days_until_salary"] == 31


def test_spender_profile_against_age_band(data_env):
    r = m.spender_profile("C1", today="2026-09-30")
    assert r["age_band"] == "25-34" and r["peer_customers"] == 2   # C1 and C2; C3 is 50-64
    b = {x["basket"]: x for x in r["baskets"]}
    # C1 Jul-Sep: regular 910 + 910 + 960 = 2780, irregular 120, everyday 121.50, total 3021.50
    assert [b[k]["your_share_pct"] for k in ("MANDATORY_REGULAR", "MANDATORY_IRREGULAR", "EVERYDAY")] == [92.0, 4.0, 4.0]
    # C2: regular 1800, everyday 300 of 2100. Medians of the two exact shares:
    # regular (92.007 + 85.714) / 2 = 88.86 -> 88.9; irregular (3.972 + 0) / 2 -> 2.0; everyday (4.021 + 14.286) / 2 -> 9.2
    assert [b[k]["peer_median_share_pct"] for k in ("MANDATORY_REGULAR", "MANDATORY_IRREGULAR", "EVERYDAY")] == [88.9, 2.0, 9.2]
    assert [b[k]["difference_pp"] for k in ("MANDATORY_REGULAR", "MANDATORY_IRREGULAR", "EVERYDAY")] == [3.1, 2.0, -5.2]
    assert r["biggest_difference"]["basket"] == "EVERYDAY"
    # Monthly: 2780 / 3 = 926.67; peers median(2780, 1800) / 3 = 763.33; everyday median(121.5, 300) / 3 = 70.25
    assert (b["MANDATORY_REGULAR"]["your_monthly_eur"], b["MANDATORY_REGULAR"]["peer_median_monthly_eur"]) == (926.67, 763.33)
    assert b["EVERYDAY"]["peer_median_monthly_eur"] == 70.25


def test_recurring_payments(data_env):
    r = m.recurring_payments("C1", today="2026-09-30")
    assert r["period"] == {"start": "2026-06-01", "end": "2026-09-30", "months": 4}   # clamped to data start
    s = {x["name"]: x for x in r["recurring"]}
    # Same merchant every month at the same amount counts; one-off merchants (MRC-GRO-0002, the doctor) do not.
    assert set(s) == {"Housing", "Utilities", "Invest Deposit", "Groceries merchant MRC-GRO-0001",
                      "Transportation merchant MRC-TRN-0001", "Restaurants merchant MRC-RES-0001"}
    h = s["Housing"]
    assert (h["typical_monthly_eur"], h["latest_month_eur"], h["change_pct"], h["payments_per_month"]) == (800.0, 800.0, 0.0, 1.0)
    assert (h["last_payment_date"], h["last_payment_eur"]) == ("2026-09-05", 800.0)
    inv = s["Invest Deposit"]
    assert inv["typical_monthly_eur"] == 0.0 and inv["change_pct"] is None and inv["latest_month_eur"] == 100.0
    assert [x["name"] for x in r["recurring"]][:2] == ["Housing", "Groceries merchant MRC-GRO-0001"]
    assert r["salary"] == {"payments": 4, "average_monthly_eur": 2500.0, "last_date": "2026-09-15", "last_eur": 2500.0}


def test_customer_profile(data_env):
    assert m.customer_profile("C3") == {"customer_id": "C3", "age": 60, "age_band": "50-64", "postal_code": "00990"}


@pytest.mark.parametrize("call", [
    lambda: m.spending_summary("NOPE", *SEP),
    lambda: m.spending_summary("C1", "2026-09-30", "2026-09-01"),
    lambda: m.spending_summary("C1", "30.9.2026", "2026-09-30"),
    lambda: m.month_bounds("2026-13"),
])
def test_bad_input_raises_data_error(data_env, call):
    with pytest.raises(m.DataError):
        call()


def test_month_helpers():
    assert m.month_bounds("2026-02") == (date(2026, 2, 1), date(2026, 2, 28))
    assert m.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert m.add_months(date(2026, 11, 15), 2) == date(2027, 1, 15)


# ---------- With receipts: merge_grocery_split ----------

def fake_split(total=100.0, without=0.0, regular=70.0, everyday=30.0):
    return {"grocery_total_eur": total, "without_receipt_eur": without,
            "split": [{"basket": "MANDATORY_REGULAR", "total_eur": regular}, {"basket": "EVERYDAY", "total_eur": everyday}],
            "top_leak_items": [{"name": "Energy drink 0.5 l", "total_eur": 12.0, "qty": 6}]}


def test_merge_grocery_split_moves_leaks_and_keeps_total(data_env):
    s = m.spending_summary("C1", *SEP)          # groceries 100 (40 + 60), all regular essentials without receipts
    r = m.merge_grocery_split(s, fake_split())  # receipts: 70 essentials, 30 everyday items
    b = {x["basket"]: x for x in r["baskets"]}
    # regular 960 - 100 + 70 = 930; irregular 120; everyday 40.50 + 30 = 70.50; total still 1120.50
    assert (b["MANDATORY_REGULAR"]["spent_eur"], b["MANDATORY_IRREGULAR"]["spent_eur"], b["EVERYDAY"]["spent_eur"]) == (930.0, 120.0, 70.5)
    assert r["spending_total_eur"] == 1120.50
    # 930 / 1120.5 = 83.00 %, 120 / 1120.5 = 10.71 %, 70.5 / 1120.5 = 6.29 %
    assert [x["share_pct"] for x in r["baskets"]] == [83.0, 10.7, 6.3]
    assert b["MANDATORY_REGULAR"]["transactions"] == 5          # card counts unchanged
    assert r["synthetic"] is True and r["receipts"]["synthetic"] is True
    assert r["receipts"]["split"][2] == {"basket": "EVERYDAY", "label": "Everyday spending", "total_eur": 30.0}
    assert s["baskets"][0]["spent_eur"] == 960.0                  # the input is not modified


def test_merge_grocery_split_with_trips_without_receipt(data_env):
    s = m.spending_summary("C1", *SEP)
    r = m.merge_grocery_split(s, fake_split(without=40.0, regular=45.0, everyday=15.0))
    # only 60 has receipts: regular 960 - 60 + 45 = 945; everyday 40.50 + 15 = 55.50
    assert [x["spent_eur"] for x in r["baskets"]] == [945.0, 120.0, 55.5]


@pytest.mark.parametrize("split", [
    fake_split(total=99.0, regular=69.0),            # receipts do not match card groceries
    fake_split(regular=70.0, everyday=29.99),        # split does not add up to the cent
    {**fake_split(), "split": [{"basket": "INCOME", "total_eur": 100.0}]},
])
def test_merge_grocery_split_refuses_inconsistent_receipts(data_env, split):
    with pytest.raises(m.DataError):
        m.merge_grocery_split(m.spending_summary("C1", *SEP), split)

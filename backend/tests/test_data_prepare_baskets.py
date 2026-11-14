"""prepare.py, db.py and baskets.py on the hand-made fixture."""
from __future__ import annotations

import pytest
from test_data_fixture import data_env, write_raw  # noqa: F401  (pytest fixture)

from kukkaro.data.baskets import Basket, assign_basket, subcategory
from kukkaro.data.db import get_conn
from kukkaro.data.prepare import prepare


def test_prepare_stats(data_env):
    s = data_env["stats"]
    # C1: 6 rows x 4 months + 4 extra in Sep = 28; C2 and C3: 3 x 4 = 12 each
    assert s["n_rows"] == 52
    assert s["n_customers"] == 3
    assert s["unparsed"] == 0 and s["date_mismatch"] == 0 and s["balance_breaks"] == 0
    assert str(s["first_date"]) == "2026-06-01" and str(s["last_date"]) == "2026-09-30"


def test_tx_ids_follow_file_order(data_env):
    con = get_conn()
    ids = [r[0] for r in con.execute("SELECT tx_id FROM transactions WHERE customer_id = 'C1' ORDER BY tx_timestamp").fetchall()]
    assert ids == [f"C1-{i}" for i in range(1, 29)]
    first = con.execute("SELECT category, tx_amount_eur FROM transactions WHERE tx_id = 'C1-1'").fetchone()
    assert first[0] == "Housing" and str(first[1]) == "-800.00"


def test_tx_ids_are_stable_across_runs(data_env, tmp_path):
    import duckdb
    out = tmp_path / "again"
    prepare(data_env["root"] / "raw", out, quiet=True)
    q = "SELECT tx_id, tx_timestamp, tx_amount_eur FROM read_parquet('{}') ORDER BY tx_id"
    a = duckdb.sql(q.format((data_env["root"] / "processed" / "transactions.parquet").as_posix())).fetchall()
    b = duckdb.sql(q.format((out / "transactions.parquet").as_posix())).fetchall()
    assert a == b


def test_types_nulls_and_bom(data_env):
    con = get_conn()
    # Column names have no BOM, money is exact DECIMAL, blank and "." become NULL.
    cols = dict(con.execute("SELECT column_name, column_type FROM (DESCRIBE transactions)").fetchall())
    assert cols["customer_id"] == "VARCHAR"
    assert cols["tx_amount_eur"] == "DECIMAL(18,2)" and cols["tx_timestamp"] == "TIMESTAMP"
    dots = con.execute("SELECT merchant_id, mcc_code FROM transactions WHERE customer_id = 'C1' AND tx_amount_eur = -10").fetchone()
    assert dots == (None, None)
    bills = con.execute("SELECT count(*) FROM transactions WHERE category = 'Housing' AND merchant_id IS NULL").fetchone()[0]
    assert bills == 12
    # Postal codes keep their leading zeros.
    assert con.execute("SELECT customer_postal_code, age_band FROM customers WHERE customer_id = 'C2'").fetchone() == ("00100", "25-34")


def test_lfs_pointer_is_refused(tmp_path):
    write_raw(tmp_path)
    (tmp_path / "tx_junction_transactions.csv").write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 346000000\n")
    with pytest.raises(SystemExit) as e:
        prepare(tmp_path, tmp_path / "out", quiet=True)
    assert "Git LFS pointer" in str(e.value)


def test_missing_file_is_refused(tmp_path):
    with pytest.raises(SystemExit) as e:
        prepare(tmp_path, tmp_path / "out", quiet=True)
    assert "Missing" in str(e.value)


@pytest.mark.parametrize("args, expected", [
    (("Housing", None, "housing_payment", -800), Basket.MANDATORY_REGULAR),
    (("Utilities", None, "utilities_payment", -50), Basket.MANDATORY_REGULAR),
    (("Groceries", "5411", "purchase", -60), Basket.MANDATORY_REGULAR),
    (("Transportation", "4111", "purchase", -3), Basket.MANDATORY_REGULAR),   # public transport
    (("Transportation", "4121", "purchase", -25), Basket.EVERYDAY),           # taxi
    (("Transportation", "7523", "purchase", -4), Basket.EVERYDAY),            # parking
    (("Transportation", None, "purchase", -10), Basket.MANDATORY_REGULAR),    # no MCC: category default
    (("Health", "8011", "purchase", -120), Basket.MANDATORY_IRREGULAR),
    (("Home & Tech", "5732", "purchase", -300), Basket.MANDATORY_IRREGULAR),
    (("Restaurants", "5812", "purchase", -15.5), Basket.EVERYDAY),
    (("Travel", "4511", "purchase", -200), Basket.EVERYDAY),
    (("Salary", None, "salary", 2500), Basket.INCOME),
    (("Other Income", None, "other_income", 900), Basket.INCOME),
    (("Invest Deposit", None, "investment_deposit", -100), Basket.TRANSFER),
    (("Invest Withdraw", None, "investment_withdrawal", 100), Basket.TRANSFER),
    (("Salary Sweep", None, "salary_sweep", -3000), Basket.TRANSFER),
    (("Mystery", None, "salary_sweep", -5), Basket.TRANSFER),                 # unknown category: type fallback
    (("Mystery", None, "mystery", -5), Basket.EVERYDAY),                      # unknown out: stays visible
    (("Mystery", None, "mystery", 5), Basket.INCOME),                         # unknown in
])
def test_assign_basket(args, expected):
    assert assign_basket(*args) is expected


def test_sql_rules_match_python(data_env):
    """The tx_enriched view must classify exactly like assign_basket()/subcategory()."""
    con = get_conn()
    con.execute("""CREATE TEMP TABLE combos AS SELECT * FROM (VALUES
        ('Transportation', '4121', 'purchase', -1.0), ('Transportation', '7523', 'purchase', -1.0),
        ('Transportation', '4111', 'purchase', -1.0), ('Transportation', NULL, 'purchase', -1.0),
        ('Mystery', NULL, 'salary_sweep', -1.0), ('Mystery', NULL, 'mystery', -1.0), ('Mystery', NULL, 'mystery', 1.0),
        ('Restaurants', '5814', 'purchase', -1.0), ('Health', '8021', 'purchase', -1.0))
        AS v(category, mcc_code, transaction_type, tx_amount_eur)""")
    from kukkaro.data.baskets import basket_sql, subcategory_sql
    synthetic = con.execute(f"SELECT *, {basket_sql()}, {subcategory_sql()} FROM combos").fetchall()
    real = con.execute("""SELECT DISTINCT category, mcc_code, transaction_type, sign(tx_amount_eur), basket, subcategory
                          FROM tx_enriched""").fetchall()
    for cat, mcc, tt, amt, basket, sub in synthetic + real:
        assert basket == assign_basket(cat, mcc, tt, float(amt)).value, (cat, mcc, tt)
        assert sub == subcategory(cat, mcc), (cat, mcc)

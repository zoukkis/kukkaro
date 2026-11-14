"""Tiny hand-made dataset for the DATA tests (imported by the other test_data_*.py files).

Written in S-Bank's exact raw format: UTF-8 with BOM, SAS-style timestamps, blank merchant and
MCC for bills. Balances are a running total from an opening balance, as in the real file.
Expected numbers in the tests are worked out by hand from the rows listed here.

C1 (age 30, band 25-34) every month Jun-Sep 2026:
  05 Housing -800 | 10 Utilities -50 | 15 08:00 Salary +2500 | 16 Groceries -60 (MRC-GRO-0001)
  20 Taxi -25 (MCC 4121) | 21 Restaurant -15.50 (MCC 5812)
  September also: 15 10:00 Groceries -40 (MRC-GRO-0002) | 18 Doctor -120 (MCC 8011)
                  25 Invest Deposit -100 | 26 Transportation purchase -10 with no merchant/MCC
C2 (age 31, band 25-34): 01 Housing -600 | 10 Restaurants -100 (MCC 5814) | month-end Salary +2000
C3 (age 60, band 50-64): 02 Housing -1000 | 15 Salary +3000 | 20 Lifestyle -500 (MCC 5651)
"""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
MONTHS = [6, 7, 8, 9]
MONTH_END = {6: 30, 7: 31, 8: 31, 9: 30}


def sas(ts: datetime) -> str:
    return f"{ts:%d}{MON[ts.month - 1]}{ts:%y}:{ts:%H:%M:%S}"


def rows_for(customer: str) -> list[tuple]:
    """(timestamp, category, amount, transaction_type, merchant_id, mcc) in booking order."""
    r = []
    for m in MONTHS:
        d = lambda day, h=12, mi=0: datetime(2026, m, day, h, mi)
        if customer == "C1":
            r += [(d(5), "Housing", "-800.00", "housing_payment", "", ""),
                  (d(10), "Utilities", "-50.00", "utilities_payment", "", ""),
                  (d(15, 8), "Salary", "2500.00", "salary", "", "")]
            if m == 9:
                r.append((d(15, 10), "Groceries", "-40.00", "purchase", "MRC-GRO-0002", "5411"))
            r.append((d(16), "Groceries", "-60.00", "purchase", "MRC-GRO-0001", "5411"))
            if m == 9:
                r.append((d(18), "Health", "-120.00", "purchase", "MRC-HEA-0001", "8011"))
            r += [(d(20), "Transportation", "-25.00", "purchase", "MRC-TRN-0001", "4121"),
                  (d(21), "Restaurants", "-15.50", "purchase", "MRC-RES-0001", "5812")]
            if m == 9:
                r += [(d(25), "Invest Deposit", "-100.00", "investment_deposit", "", ""),
                      (d(26), "Transportation", "-10.00", "purchase", ".", ".")]
        elif customer == "C2":
            r += [(d(1), "Housing", "-600.00", "housing_payment", "", ""),
                  (d(10), "Restaurants", "-100.00", "purchase", "MRC-RES-0002", "5814"),
                  (d(MONTH_END[m], 18), "Salary", "2000.00", "salary", "", "")]
        else:
            r += [(d(2), "Housing", "-1000.00", "housing_payment", "", ""),
                  (d(15), "Salary", "3000.00", "salary", "", ""),
                  (d(20), "Lifestyle", "-500.00", "purchase", "MRC-LIF-0001", "5651")]
    return r


def write_raw(raw: Path) -> None:
    raw.mkdir(parents=True, exist_ok=True)
    lines = ["customer_id,bank_account_id,tx_date,tx_timestamp,category,tx_amount_eur,balance_after_eur,transaction_type,merchant_id,mcc_code"]
    for cid, acc in [("C1", "ACC1"), ("C2", "ACC2"), ("C3", "ACC3")]:
        bal = Decimal("1000.00")
        for ts, cat, amt, tt, merch, mcc in rows_for(cid):
            bal += Decimal(amt)
            lines.append(f"{cid},{acc},{ts:%Y-%m-%d},{sas(ts)},{cat},{amt},{bal},{tt},{merch},{mcc}")
    (raw / "tx_junction_transactions.csv").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    (raw / "tx_customers_junction.csv").write_text(
        "customer_id,customer_postal_code,customer_age\nC1,02150,30\nC2,00100,31\nC3,00990,60\n", encoding="utf-8-sig")


@pytest.fixture(scope="session")
def data_env(tmp_path_factory):
    """Prepare the fixture into a temp DATA_DIR and point get_conn() at it."""
    from kukkaro.data import metrics
    from kukkaro.data.prepare import prepare

    root = tmp_path_factory.mktemp("data")
    write_raw(root / "raw")
    stats = prepare(root / "raw", root / "processed", quiet=True)
    old = {k: os.environ.get(k) for k in ("DATA_DIR", "DEMO_TODAY")}
    os.environ["DATA_DIR"] = str(root)
    os.environ["DEMO_TODAY"] = ""
    metrics.reset_caches()
    yield {"root": root, "stats": stats}
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    metrics.reset_caches()

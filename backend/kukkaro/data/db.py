"""DuckDB access for every workstream: `get_conn()` returns a connection with three views.

- `transactions`: S-Bank's rows plus a stable `tx_id` (from data/processed/transactions.parquet)
- `customers`:    customer_id, customer_postal_code (text), customer_age, age_band
- `tx_enriched`:  transactions plus `basket` and `subcategory` (rules in baskets.py)

Money columns are DECIMAL(18,2): exact to the cent. `tx_amount_eur` is signed
(negative = money out). Run `python -m kukkaro.data.prepare` first.

The base connection is created once per process; each `get_conn()` call returns a cursor on it,
which is the thread-safe way to share one DuckDB database (FastAPI runs endpoints in threads).
"""
from __future__ import annotations

import threading
from pathlib import Path

import duckdb

from kukkaro.data.baskets import basket_sql, subcategory_sql
from kukkaro.data.settings import processed_dir

AGE_BAND_SQL = """CASE
    WHEN customer_age < 25 THEN '18-24'
    WHEN customer_age < 35 THEN '25-34'
    WHEN customer_age < 50 THEN '35-49'
    WHEN customer_age < 65 THEN '50-64'
    ELSE '65+' END"""

_lock = threading.Lock()
_base: duckdb.DuckDBPyConnection | None = None
_base_dir: Path | None = None


def create_views(con: duckdb.DuckDBPyConnection, processed: Path) -> None:
    tx, cust = processed / "transactions.parquet", processed / "customers.parquet"
    for f in (tx, cust):
        if not f.exists():
            raise FileNotFoundError(f"{f} not found. Run: cd backend && python -m kukkaro.data.prepare")
    # Load into memory once: per-customer queries then take a few milliseconds.
    con.execute(f"CREATE OR REPLACE TABLE _tx AS SELECT * FROM read_parquet('{tx.as_posix()}')")
    con.execute(f"CREATE OR REPLACE TABLE _customers AS SELECT * FROM read_parquet('{cust.as_posix()}')")
    con.execute("CREATE OR REPLACE VIEW transactions AS SELECT * FROM _tx")
    con.execute(f"CREATE OR REPLACE VIEW customers AS SELECT *, {AGE_BAND_SQL} AS age_band FROM _customers")
    con.execute(f"""CREATE OR REPLACE VIEW tx_enriched AS
        SELECT t.*, {basket_sql()} AS basket, {subcategory_sql()} AS subcategory FROM transactions t""")


def get_conn(processed: Path | None = None) -> duckdb.DuckDBPyConnection:
    """A cursor on the shared in-memory database. Pass `processed` to use another folder (tests)."""
    global _base, _base_dir
    target = (processed or processed_dir()).resolve()
    with _lock:
        if _base is None or _base_dir != target:
            con = duckdb.connect()
            con.execute("SET enable_progress_bar = false")
            create_views(con, target)
            _base, _base_dir = con, target
        return _base.cursor()

"""Convert S-Bank's raw CSVs into Parquet with stable transaction IDs.

Usage (from backend/):  python -m kukkaro.data.prepare

- Reads data/raw/tx_junction_transactions.csv and tx_customers_junction.csv (UTF-8 with BOM).
- Parses the SAS-style timestamps ("03OCT24:09:04:04"), keeps money as exact DECIMAL(18,2).
- Blank or "." merchant_id / mcc_code become NULL (transfers and bills have none).
- tx_id = "{customer_id}-{n}", n = 1, 2, ... in file order within each customer. The file is
  sorted by customer and time, and the running balance only adds up in file order (checked
  below), so file order is the true booking order and the IDs are stable.
- The mortgage CSVs are skipped on purpose (stretch only, root AGENTS.md §5.1).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import duckdb

from kukkaro.data.settings import processed_dir, raw_dir

TX_CSV = "tx_junction_transactions.csv"
CUST_CSV = "tx_customers_junction.csv"
LFS_HELP = (
    "It is a Git LFS pointer, not the data. Download the real file: from the repo root run\n"
    "  bash scripts/get_data.sh\n"
    "or see data/README.md (open the file on GitHub and click 'Download raw file')."
)


def _check_inputs(raw: Path) -> None:
    for name in (TX_CSV, CUST_CSV):
        f = raw / name
        if not f.exists():
            sys.exit(f"Missing {f}. Put the S-Bank CSVs in {raw} (see data/README.md, or run bash scripts/get_data.sh).")
    with open(raw / TX_CSV, "rb") as fh:
        if b"git-lfs" in fh.read(200):
            sys.exit(f"{raw / TX_CSV}: {LFS_HELP}")


def _null_if_blank(col: str) -> str:
    return f"NULLIF(NULLIF(trim({col}), ''), '.')"


def prepare(raw: Path | None = None, out: Path | None = None, quiet: bool = False) -> dict:
    raw, out = raw or raw_dir(), out or processed_dir()
    _check_inputs(raw)
    out.mkdir(parents=True, exist_ok=True)
    log = (lambda *a: None) if quiet else print
    t0 = time.time()

    con = duckdb.connect()
    con.execute("SET preserve_insertion_order = true")  # file order matters for tx_id
    tx_csv, cust_csv = (raw / TX_CSV).as_posix(), (raw / CUST_CSV).as_posix()

    con.execute(f"""
        CREATE TABLE src AS
        SELECT row_number() OVER () AS file_row, *
        FROM read_csv('{tx_csv}', header = true, all_varchar = true, encoding = 'utf-8')""")
    cols = [r[0] for r in con.execute("DESCRIBE src").fetchall()]
    expected = ["file_row", "customer_id", "bank_account_id", "tx_date", "tx_timestamp", "category", "tx_amount_eur",
                "balance_after_eur", "transaction_type", "merchant_id", "mcc_code"]
    if cols != expected:
        sys.exit(f"Unexpected columns in {TX_CSV}: {cols}")

    con.execute(f"""
        CREATE TABLE tx AS
        SELECT
            customer_id || '-' || row_number() OVER (PARTITION BY customer_id ORDER BY file_row) AS tx_id,
            customer_id,
            bank_account_id,
            CAST(tx_date AS DATE) AS tx_date,
            strptime(tx_timestamp, '%d%b%y:%H:%M:%S') AS tx_timestamp,
            category,
            CAST(tx_amount_eur AS DECIMAL(18, 2)) AS tx_amount_eur,
            CAST(balance_after_eur AS DECIMAL(18, 2)) AS balance_after_eur,
            transaction_type,
            {_null_if_blank('merchant_id')} AS merchant_id,
            {_null_if_blank('mcc_code')} AS mcc_code,
            file_row
        FROM src""")

    # Integrity checks: every value parsed, and the running balance chains in file order.
    checks = con.execute("""
        SELECT
            count(*) AS n_rows,
            count(DISTINCT customer_id) AS n_customers,
            count(*) FILTER (WHERE tx_timestamp IS NULL OR tx_date IS NULL OR tx_amount_eur IS NULL) AS unparsed,
            count(*) FILTER (WHERE CAST(tx_timestamp AS DATE) <> tx_date) AS date_mismatch,
            min(tx_date) AS first_date,
            max(tx_date) AS last_date
        FROM tx""").fetchone()
    breaks = con.execute("""
        SELECT count(*) FROM (
            SELECT tx_amount_eur, balance_after_eur,
                   lag(balance_after_eur) OVER (PARTITION BY customer_id ORDER BY file_row) AS prev
            FROM tx) WHERE prev IS NOT NULL AND prev + tx_amount_eur <> balance_after_eur""").fetchone()[0]
    stats = dict(zip(["n_rows", "n_customers", "unparsed", "date_mismatch", "first_date", "last_date"], checks))
    stats["balance_breaks"] = breaks
    if stats["unparsed"]:
        sys.exit(f"{stats['unparsed']} rows failed to parse; refusing to write Parquet.")

    tx_out, cust_out = (out / "transactions.parquet").as_posix(), (out / "customers.parquet").as_posix()
    # Sorted by customer so per-customer queries only touch a few row groups.
    con.execute(f"""
        COPY (SELECT * EXCLUDE (file_row) FROM tx ORDER BY customer_id, file_row)
        TO '{tx_out}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 50000)""")
    con.execute(f"""
        COPY (
            SELECT customer_id,
                   trim(customer_postal_code) AS customer_postal_code,  -- text: leading zeros matter
                   CAST(customer_age AS INTEGER) AS customer_age
            FROM read_csv('{cust_csv}', header = true, all_varchar = true, encoding = 'utf-8')
            ORDER BY customer_id)
        TO '{cust_out}' (FORMAT parquet, COMPRESSION zstd)""")
    stats["n_customer_rows"] = con.execute(f"SELECT count(*) FROM read_parquet('{cust_out}')").fetchone()[0]
    stats["seconds"] = round(time.time() - t0, 1)

    log(f"Wrote {tx_out} and {cust_out}")
    for k, v in stats.items():
        log(f"  {k}: {v}")
    if breaks:
        log(f"  WARNING: {breaks} balance breaks; file order may not be booking order.")
    return stats


if __name__ == "__main__":
    prepare()

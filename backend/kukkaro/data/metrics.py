"""Deterministic money metrics over DuckDB. COACH exposes these as LLM tools.

Conventions (every function):
- Every function returns a plain dict of JSON-safe values: euros are floats rounded to the cent and
  dates are ISO strings. Sums are computed exactly (DECIMAL) and rounded only for output.
- Spending is reported as positive euros (`spent_eur`). The raw `tx_amount_eur` is signed.
- Periods are inclusive: `start` and `end` are both counted.
- Derived figures are computed from the rounded figures shown next to them, so a reader can redo
  the arithmetic (e.g. yearly = monthly x 12 exactly).
- Invalid input (unknown customer, unknown category, bad dates) raises `DataError` with a message
  that is safe to show to the user or the LLM.
- "Today" is `get_today()`: `DEMO_TODAY` if set, else the last date in the dataset. Never the real date.
"""
from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from statistics import median
from typing import Any

from kukkaro.data.baskets import BASKET_LABELS, CATEGORY_BASKET, SPENDING_BASKETS, Basket
from kukkaro.data.db import get_conn
from kukkaro.data.settings import demo_today_env

CENT = Decimal("0.01")
SPENDING = tuple(b.value for b in SPENDING_BASKETS)
_SPENDING_SQL = "(" + ", ".join(f"'{b}'" for b in SPENDING) + ")"

# Words people use for categories that are not literal names in the data.
ALIASES: dict[str, str] = {
    "taxi": "Taxis", "cab": "Taxis", "uber": "Taxis", "bolt": "Taxis",
    "bus": "Public transport", "metro": "Public transport", "train": "Public transport", "tram": "Public transport",
    "public transportation": "Public transport", "hsl": "Public transport",
    "gas": "Fuel", "petrol": "Fuel", "diesel": "Fuel",
    "grocery": "Groceries", "food shopping": "Groceries", "supermarket": "Grocery stores",
    "eating out": "Restaurants", "takeaway": "Fast food", "take-away": "Fast food", "fast-food": "Fast food",
    "pub": "Bars", "drinks": "Bars", "movies": "Cinema",
    "rent": "Housing", "mortgage": "Housing", "bills": "Utilities", "electricity": "Utilities",
    "clothes": "Clothing", "doctor visits": "Doctor", "medicine": "Pharmacy", "dental": "Dentist",
    "flight": "Flights", "hotel": "Hotels", "shopping": "Lifestyle",
}


class DataError(ValueError):
    """Bad input to a metric. The message is user-safe. The API answers 422."""


class UnknownCustomer(DataError):
    """The customer ID does not exist. The API answers 404."""


# ---------- small helpers ----------

def _eur(x: Decimal | float | int | None) -> float:
    return float(Decimal(x or 0).quantize(CENT, rounding=ROUND_HALF_UP))


def _round(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def _pct(part: Decimal, whole: Decimal) -> float:
    return 0.0 if not whole else float((part * 100 / whole).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _date(d: date | str, name: str) -> date:
    if isinstance(d, date):
        return d
    try:
        return date.fromisoformat(str(d))
    except ValueError:
        raise DataError(f"{name} must be a date like 2026-09-30, got {d!r}") from None


def _period(start: date | str, end: date | str) -> tuple[date, date]:
    s, e = _date(start, "start"), _date(end, "end")
    if s > e:
        raise DataError(f"start ({s}) is after end ({e})")
    return s, e


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, n: int) -> date:
    """Same day n months later, clamped to the month's last day (Jan 31 + 1 = Feb 28)."""
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def month_bounds(month: str) -> tuple[date, date]:
    """'2026-09' -> (2026-09-01, 2026-09-30)."""
    try:
        first = date.fromisoformat(f"{month}-01")
    except ValueError:
        raise DataError(f"month must look like 2026-09, got {month!r}") from None
    return first, month_end(first)


@lru_cache(maxsize=1)
def _dataset_bounds() -> tuple[date, date]:
    return get_conn().execute("SELECT min(tx_date), max(tx_date) FROM transactions").fetchone()


def get_today() -> date:
    return demo_today_env() or _dataset_bounds()[1]


def warm_up(customer_id: str | None = None) -> None:
    """Fill every cache once (dataset dates, category names, age-band medians) so no user request is slow."""
    get_today()
    _names()
    if customer_id:
        spender_profile(customer_id)


def reset_caches() -> None:
    """Forget cached dataset facts (call after switching data folders, e.g. in tests)."""
    _dataset_bounds.cache_clear()
    _names.cache_clear()
    _peer_stats.cache_clear()


def complete_months(today: date, n: int) -> tuple[date, date, int]:
    """The last n calendar months that are complete on `today` (a month counts once its last day
    is reached), clamped to the start of the data. Returns (start, end, number_of_months)."""
    last = month_start(today) if today == month_end(today) else add_months(month_start(today), -1)
    first = add_months(last, -(n - 1))
    data_first = month_start(_dataset_bounds()[0])
    if first < data_first:
        first = data_first
    months = (last.year - first.year) * 12 + last.month - first.month + 1
    if months < 1:
        raise DataError(f"No complete month of data before {today}")
    return first, month_end(last), months


def _check_customer(con, customer_id: str) -> None:
    if not con.execute("SELECT 1 FROM customers WHERE customer_id = ?", [customer_id]).fetchone():
        raise UnknownCustomer(f"Unknown customer {customer_id!r}")


@lru_cache(maxsize=1)
def _names() -> tuple[dict[str, str], dict[str, str]]:
    """Lower-case lookup of category and subcategory names present in the data."""
    con = get_conn()
    cats = {r[0].lower(): r[0] for r in con.execute("SELECT DISTINCT category FROM transactions").fetchall()}
    subs = {r[0].lower(): r[0] for r in con.execute("SELECT DISTINCT subcategory FROM tx_enriched").fetchall()}
    return cats, subs


def resolve_category(name: str) -> tuple[str, str]:
    """Map a user's word to ('category' | 'subcategory', exact name). Categories win over
    subcategories, plural/singular is ignored, and a few everyday words are aliased."""
    cats, subs = _names()
    key = " ".join(str(name).lower().split())
    key = ALIASES.get(key, ALIASES.get(key.rstrip("s"), key)).lower()
    for k in (key, key.rstrip("s"), key + "s"):
        if k in cats:
            return "category", cats[k]
    for k in (key, key.rstrip("s"), key + "s"):
        if k in subs:
            return "subcategory", subs[k]
    known = sorted(set(cats.values()) | set(subs.values()))
    raise DataError(f"Unknown category {name!r}. Known: {', '.join(known)}")


def _spend_rows(con, customer_id: str, level: str, name: str, start: date, end: date):
    col = "category" if level == "category" else "subcategory"
    return con.execute(f"""
        SELECT basket, strftime(tx_date, '%Y-%m') AS month, sum(-tx_amount_eur) AS spent, count(*) AS n
        FROM tx_enriched
        WHERE customer_id = ? AND {col} = ? AND tx_date BETWEEN ? AND ? AND basket IN {_SPENDING_SQL}
        GROUP BY ALL""", [customer_id, name, start, end]).fetchall()


# ---------- metrics ----------

def spending_summary(customer_id: str, start: date | str, end: date | str) -> dict[str, Any]:
    """Spending per basket and per category, plus income, transfers and balance, for a period."""
    s, e = _period(start, end)
    con = get_conn()
    _check_customer(con, customer_id)
    rows = con.execute("""
        SELECT basket, category, subcategory, sum(-tx_amount_eur) AS spent, count(*) AS n
        FROM tx_enriched WHERE customer_id = ? AND tx_date BETWEEN ? AND ? GROUP BY ALL""",
        [customer_id, s, e]).fetchall()

    per_basket = {b: [Decimal(0), 0] for b in SPENDING}
    groups: dict[tuple[str, str], list] = {}
    income = transfers_out = transfers_in = Decimal(0)
    n_total = 0
    for basket, category, sub, spent, n in rows:
        n_total += n
        if basket in per_basket:
            per_basket[basket][0] += spent
            per_basket[basket][1] += n
            # Show a subcategory on its own line when its basket differs from its category's default
            # (e.g. Taxis under Everyday spending while the rest of Transportation is a regular essential).
            default = CATEGORY_BASKET.get(category)
            label = category if default is not None and default.value == basket else sub
            g = groups.setdefault((basket, label), [Decimal(0), 0])
            g[0] += spent
            g[1] += n
        elif basket == Basket.INCOME.value:
            income += -spent
        elif spent > 0:
            transfers_out += spent
        else:
            transfers_in += -spent
    total = sum((v[0] for v in per_basket.values()), Decimal(0))

    bal = con.execute("""
        SELECT tx_date, balance_after_eur FROM transactions
        WHERE customer_id = ? AND tx_date <= ? ORDER BY tx_timestamp DESC, tx_id DESC LIMIT 1""",
        [customer_id, e]).fetchone()
    return {
        "customer_id": customer_id,
        "period": {"start": s.isoformat(), "end": e.isoformat()},
        "spending_total_eur": _eur(total),
        "baskets": [
            {"basket": b, "label": BASKET_LABELS[Basket(b)], "spent_eur": _eur(v[0]),
             "share_pct": _pct(v[0], total), "transactions": v[1]}
            for b, v in per_basket.items()
        ],
        "top_categories": [
            {"name": label, "basket": b, "spent_eur": _eur(v[0]), "transactions": v[1]}
            for (b, label), v in sorted(groups.items(), key=lambda kv: kv[1][0], reverse=True)
        ],
        "income_eur": _eur(income),
        "transfers_out_eur": _eur(transfers_out),
        "transfers_in_eur": _eur(transfers_in),
        "transactions": n_total,
        "balance_eur": _eur(bal[1]) if bal else None,
        "balance_date": bal[0].isoformat() if bal else None,
    }


def category_spend(customer_id: str, category: str, start: date | str, end: date | str) -> dict[str, Any]:
    """Spending in one category or subcategory (e.g. 'Restaurants', 'taxis'), with a monthly breakdown."""
    s, e = _period(start, end)
    con = get_conn()
    _check_customer(con, customer_id)
    level, name = resolve_category(category)
    rows = _spend_rows(con, customer_id, level, name, s, e)
    total = sum((r[2] for r in rows), Decimal(0))
    n = sum(r[3] for r in rows)
    by_basket: dict[str, Decimal] = {}
    by_month: dict[str, Decimal] = {}
    for basket, month, spent, _ in rows:
        by_basket[basket] = by_basket.get(basket, Decimal(0)) + spent
        by_month[month] = by_month.get(month, Decimal(0)) + spent
    return {
        "customer_id": customer_id,
        "name": name,
        "level": level,
        "period": {"start": s.isoformat(), "end": e.isoformat()},
        "spent_eur": _eur(total),
        "transactions": n,
        "average_per_transaction_eur": _eur(_round(total) / n) if n else 0.0,
        "baskets": [{"basket": b, "label": BASKET_LABELS[Basket(b)], "spent_eur": _eur(v)}
                    for b, v in sorted(by_basket.items(), key=lambda kv: kv[1], reverse=True)],
        "by_month": [{"month": m, "spent_eur": _eur(v)} for m, v in sorted(by_month.items())],
    }


def merchant_spend(customer_id: str, merchant_id: str, start: date | str, end: date | str) -> dict[str, Any]:
    """Spending at one merchant (the dataset has merchant IDs, not names)."""
    s, e = _period(start, end)
    con = get_conn()
    _check_customer(con, customer_id)
    r = con.execute("""
        SELECT sum(-tx_amount_eur), count(*), any_value(category), any_value(subcategory), any_value(basket),
               min(tx_date), max(tx_date)
        FROM tx_enriched WHERE customer_id = ? AND merchant_id = ? AND tx_date BETWEEN ? AND ?""",
        [customer_id, merchant_id, s, e]).fetchone()
    spent, n, cat, sub, basket, first, last = r
    return {
        "customer_id": customer_id,
        "merchant_id": merchant_id,
        "period": {"start": s.isoformat(), "end": e.isoformat()},
        "spent_eur": _eur(spent),
        "transactions": n,
        "category": cat,
        "subcategory": sub,
        "basket": basket,
        "first_date": first.isoformat() if first else None,
        "last_date": last.isoformat() if last else None,
    }


def _last_income(con, customer_id: str, today: date):
    return con.execute("""
        SELECT tx_date, tx_amount_eur, tx_timestamp FROM transactions
        WHERE customer_id = ? AND category = 'Salary' AND tx_date <= ? ORDER BY tx_timestamp DESC LIMIT 1""",
        [customer_id, today]).fetchone()


def _next_income(last_income: date, today: date) -> date:
    """Salary arrives monthly on about the same day; a month-end payer stays on month ends."""
    month_end_payer = last_income == month_end(last_income)
    nxt = last_income
    while nxt <= today:
        nxt = add_months(nxt, 1)
        if month_end_payer:
            nxt = month_end(nxt)
    return nxt


def safe_to_spend(customer_id: str, today: date | str | None = None) -> dict[str, Any]:
    """Balance minus the regular essentials still expected before the next salary, spread over the
    days until then. "Still expected" per regular-essentials group = its typical month (average of
    the last 3 complete months) minus what was already paid since the last salary (never below 0)."""
    t = _date(today, "today") if today else get_today()
    con = get_conn()
    _check_customer(con, customer_id)
    bal = con.execute("""
        SELECT tx_date, balance_after_eur FROM transactions
        WHERE customer_id = ? AND tx_date <= ? ORDER BY tx_timestamp DESC, tx_id DESC LIMIT 1""",
        [customer_id, t]).fetchone()
    inc = _last_income(con, customer_id, t)
    if not bal or not inc:
        raise DataError(f"Not enough history for {customer_id} on {t} (need a balance and a salary)")
    last_income_date, last_income_amt, last_income_ts = inc
    next_income = _next_income(last_income_date, t)
    days_left = (next_income - t).days
    m_start, m_end, n_months = complete_months(t, 3)

    # "Paid since salary" = after the salary was booked (same-day payments after it count).
    rows = con.execute("""
        SELECT CASE WHEN category = 'Transportation' THEN subcategory ELSE category END AS grp,
               sum(-tx_amount_eur) FILTER (WHERE tx_date BETWEEN ? AND ?) AS typical_total,
               coalesce(sum(-tx_amount_eur) FILTER (WHERE tx_timestamp > ? AND tx_date <= ?), 0) AS paid_since
        FROM tx_enriched
        WHERE customer_id = ? AND basket = 'MANDATORY_REGULAR' AND tx_date BETWEEN ? AND ?
        GROUP BY 1""",
        [m_start, m_end, last_income_ts, t, customer_id, min(m_start, last_income_date), t]).fetchall()
    expected = []
    for grp, typical_total, paid_since in rows:
        typical = _round(Decimal(typical_total or 0) / n_months)
        paid = _round(Decimal(paid_since))
        still = max(Decimal(0), typical - paid)
        expected.append({"name": grp, "typical_monthly_eur": _eur(typical), "paid_since_salary_eur": _eur(paid),
                         "still_expected_eur": _eur(still)})
    expected.sort(key=lambda x: x["still_expected_eur"], reverse=True)
    expected_total = sum((Decimal(str(x["still_expected_eur"])) for x in expected), Decimal(0))
    balance = _round(Decimal(bal[1]))
    amount = balance - expected_total
    per_day = _round(amount / days_left)
    week_days = min(7, days_left)
    return {
        "customer_id": customer_id,
        "today": t.isoformat(),
        "amount_eur": _eur(amount),
        "until_date": next_income.isoformat(),
        "per_day_eur": _eur(per_day),
        "this_week_eur": _eur(per_day * week_days),
        "status": "ok" if amount > 0 else "short",
        "explanation_inputs": {
            "balance_eur": _eur(balance),
            "balance_date": bal[0].isoformat(),
            "last_salary_date": last_income_date.isoformat(),
            "last_salary_eur": _eur(last_income_amt),
            "next_salary_date_estimated": next_income.isoformat(),
            "days_until_salary": days_left,
            "days_in_this_week": week_days,
            "regular_essentials_still_expected_eur": _eur(expected_total),
            "regular_essentials": expected,
            "typical_month_based_on": {"start": m_start.isoformat(), "end": m_end.isoformat(), "months": n_months},
            "formula": "amount = balance - still expected regular essentials; per_day = amount / days until salary; this_week = per_day x days in this week",
        },
    }


def what_if(customer_id: str, category: str, change_pct: float, today: date | str | None = None) -> dict[str, Any]:
    """Monthly and yearly euro impact of changing spending in a category by `change_pct` percent,
    based on the average month over the last 3 complete months."""
    t = _date(today, "today") if today else get_today()
    pct = Decimal(str(change_pct))
    if pct < -100:
        raise DataError("change_pct cannot be below -100 (that would be negative spending)")
    con = get_conn()
    _check_customer(con, customer_id)
    level, name = resolve_category(category)
    m_start, m_end, n_months = complete_months(t, 3)
    rows = _spend_rows(con, customer_id, level, name, m_start, m_end)
    total = sum((r[2] for r in rows), Decimal(0))
    baseline = _round(total / n_months)
    monthly = _round(baseline * pct / 100)
    baskets = sorted({r[0] for r in rows})
    return {
        "customer_id": customer_id,
        "name": name,
        "level": level,
        "change_pct": float(pct),
        "baseline_monthly_eur": _eur(baseline),
        "monthly_change_eur": _eur(monthly),
        "yearly_change_eur": _eur(monthly * 12),
        "new_monthly_eur": _eur(baseline + monthly),
        "baskets": [{"basket": b, "label": BASKET_LABELS[Basket(b)]} for b in baskets],
        "based_on": {"start": m_start.isoformat(), "end": m_end.isoformat(), "months": n_months},
        "formula": "monthly_change = baseline_monthly x change_pct / 100; yearly_change = monthly_change x 12",
    }


@lru_cache(maxsize=8)
def _peer_stats(start: date, end: date) -> dict[str, tuple[int, dict[str, Decimal], dict[str, Decimal]]]:
    """Per age band: (customers, median basket share %, median euros per basket) for a period.
    Computed for all bands in one pass and cached, so only the first call per period is slow."""
    rows = get_conn().execute(f"""
        SELECT c.age_band, t.customer_id, t.basket, sum(-t.tx_amount_eur)
        FROM tx_enriched t JOIN customers c USING (customer_id)
        WHERE t.tx_date BETWEEN ? AND ? AND t.basket IN {_SPENDING_SQL}
        GROUP BY ALL""", [start, end]).fetchall()
    per: dict[str, dict[str, dict[str, Decimal]]] = {}
    for band, cid, basket, spent in rows:
        per.setdefault(band, {}).setdefault(cid, {b: Decimal(0) for b in SPENDING})[basket] = Decimal(spent)
    out = {}
    for band, customers in per.items():
        shares = {b: [] for b in SPENDING}
        amounts = {b: [] for b in SPENDING}
        for v in customers.values():
            tot = sum(v.values(), Decimal(0))
            for b in SPENDING:
                shares[b].append(v[b] * 100 / tot if tot else Decimal(0))
                amounts[b].append(v[b])
        out[band] = (len(customers),
                     {b: Decimal(median(x)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) for b, x in shares.items()},
                     {b: Decimal(median(x)) for b, x in amounts.items()})
    return out


def spender_profile(customer_id: str, today: date | str | None = None) -> dict[str, Any]:
    """Your basket shares over the last 3 complete months compared with the median customer of
    your age band (same months)."""
    t = _date(today, "today") if today else get_today()
    con = get_conn()
    _check_customer(con, customer_id)
    age, band = con.execute("SELECT customer_age, age_band FROM customers WHERE customer_id = ?", [customer_id]).fetchone()
    m_start, m_end, n_months = complete_months(t, 3)
    summary = spending_summary(customer_id, m_start, m_end)
    zero = {b: Decimal(0) for b in SPENDING}
    peers, peer_share, peer_amount = _peer_stats(m_start, m_end).get(band, (0, zero, zero))
    baskets = []
    for b in summary["baskets"]:
        key = b["basket"]
        mine = Decimal(str(b["share_pct"]))
        baskets.append({
            "basket": key, "label": b["label"],
            "your_share_pct": b["share_pct"], "peer_median_share_pct": float(peer_share[key]),
            "difference_pp": float(mine - peer_share[key]),
            "your_monthly_eur": _eur(Decimal(str(b["spent_eur"])) / n_months),
            "peer_median_monthly_eur": _eur(peer_amount[key] / n_months),
        })
    biggest = max(baskets, key=lambda x: abs(x["difference_pp"]))
    return {
        "customer_id": customer_id,
        "age": age,
        "age_band": band,
        "peer_customers": peers,
        "period": {"start": m_start.isoformat(), "end": m_end.isoformat(), "months": n_months},
        "spending_total_eur": summary["spending_total_eur"],
        "baskets": baskets,
        "biggest_difference": {"basket": biggest["basket"], "label": biggest["label"], "difference_pp": biggest["difference_pp"]},
        "note": "Shares are percent of your spending in these months; peers are customers in the same age band.",
    }


def recurring_payments(customer_id: str, today: date | str | None = None) -> dict[str, Any]:
    """Recurring outgoing payments and the salary pattern, over the last 6 complete months.

    In this dataset bills and housing payments carry no merchant, so they are grouped by category
    (all utility bills form one stream). Purchases count as recurring when the same merchant is
    paid in at least 4 of the 6 months, at most twice a month, with amounts within 15% of each
    other. (No purchase meets that bar in the S-Bank data; see docs/DATA_PROFILE.md.)
    For each stream: typical month = average of the 3 months before the latest complete month,
    compared with the latest complete month (`change_pct`), so a rise shows up."""
    t = _date(today, "today") if today else get_today()
    con = get_conn()
    _check_customer(con, customer_id)
    w_start, w_end, n_months = complete_months(t, 6)
    last_month = month_start(w_end)
    prev_start = add_months(last_month, -3)

    rows = con.execute("""
        WITH x AS (
            SELECT CASE WHEN merchant_id IS NULL THEN category ELSE merchant_id END AS stream,
                   merchant_id IS NOT NULL AS is_merchant, category, basket,
                   date_trunc('month', tx_date) AS m, tx_date, -tx_amount_eur AS amt, tx_timestamp, tx_id
            FROM tx_enriched
            WHERE customer_id = ? AND tx_date BETWEEN ? AND ? AND tx_amount_eur < 0
              AND (merchant_id IS NOT NULL OR transaction_type IN ('housing_payment', 'utilities_payment', 'investment_deposit', 'salary_sweep')))
        SELECT stream, any_value(is_merchant), any_value(category), any_value(basket),
               count(DISTINCT m) AS months_present, count(*) AS n,
               max(amt) AS max_amt, min(amt) AS min_amt,
               sum(amt) FILTER (WHERE m >= ? AND m < ?) AS prev3_total,
               coalesce(sum(amt) FILTER (WHERE m = ?), 0) AS last_month_total,
               arg_max(tx_date, tx_timestamp) AS last_date, arg_max(amt, tx_timestamp) AS last_amt,
               max(per_month) AS max_per_month
        FROM (SELECT *, count(*) OVER (PARTITION BY stream, m) AS per_month FROM x)
        GROUP BY stream""",
        [customer_id, w_start, w_end, prev_start, last_month, last_month]).fetchall()

    streams = []
    for stream, is_merchant, cat, basket, months_present, n, mx, mn, prev3, last_total, last_date, last_amt, max_pm in rows:
        if is_merchant and not (months_present >= min(4, n_months) and max_pm <= 2 and mn > 0 and (mx - mn) / mn <= Decimal("0.15")):
            continue
        typical = _round(Decimal(prev3 or 0) / 3)
        last_total = _round(Decimal(last_total))
        streams.append({
            "name": stream if not is_merchant else f"{cat} merchant {stream}",
            "category": cat,
            "basket": basket,
            "label": BASKET_LABELS[Basket(basket)],
            "months_present": months_present,
            "payments_per_month": round(n / months_present, 1),
            "typical_monthly_eur": _eur(typical),
            "latest_month": last_month.strftime("%Y-%m"),
            "latest_month_eur": _eur(last_total),
            "change_pct": _pct(last_total - typical, typical) if typical else None,
            "last_payment_date": last_date.isoformat(),
            "last_payment_eur": _eur(last_amt),
        })
    streams.sort(key=lambda x: x["typical_monthly_eur"], reverse=True)

    inc = con.execute("""
        SELECT count(*), sum(tx_amount_eur), arg_max(tx_date, tx_date), arg_max(tx_amount_eur, tx_date)
        FROM transactions WHERE customer_id = ? AND category = 'Salary' AND tx_date BETWEEN ? AND ?""",
        [customer_id, w_start, w_end]).fetchone()
    other = con.execute("""
        SELECT count(*), coalesce(sum(tx_amount_eur), 0) FROM transactions
        WHERE customer_id = ? AND category = 'Other Income' AND tx_date BETWEEN ? AND ?""",
        [customer_id, w_start, w_end]).fetchone()
    return {
        "customer_id": customer_id,
        "period": {"start": w_start.isoformat(), "end": w_end.isoformat(), "months": n_months},
        "recurring": streams,
        "salary": {
            "payments": inc[0],
            "average_monthly_eur": _eur(_round(Decimal(inc[1] or 0)) / n_months),
            "last_date": inc[2].isoformat() if inc[2] else None,
            "last_eur": _eur(inc[3]),
        },
        "other_income": {"payments": other[0], "total_eur": _eur(other[1])},
        "note": "Utility bills have no merchant in this data, so electricity, water and internet cannot be told apart.",
    }


TX_COLUMNS = ("tx_id", "customer_id", "bank_account_id", "tx_date", "tx_timestamp", "category", "subcategory",
              "tx_amount_eur", "balance_after_eur", "transaction_type", "merchant_id", "mcc_code", "basket")


def transactions_page(customer_id: str, limit: int = 50, offset: int = 0, basket: str | None = None,
                      month: str | None = None) -> dict[str, Any]:
    """One page of the customer's `tx_enriched` rows, newest first. Optional basket and month filters."""
    if not 1 <= limit <= 500:
        raise DataError("limit must be between 1 and 500")
    if offset < 0:
        raise DataError("offset cannot be negative")
    if basket is not None and basket not in {b.value for b in Basket}:
        raise DataError(f"basket must be one of {', '.join(b.value for b in Basket)}")
    con = get_conn()
    _check_customer(con, customer_id)
    where, params = ["customer_id = ?"], [customer_id]
    if basket:
        where.append("basket = ?")
        params.append(basket)
    if month:
        s, e = month_bounds(month)
        where.append("tx_date BETWEEN ? AND ?")
        params += [s, e]
    cond = " AND ".join(where)
    total = con.execute(f"SELECT count(*) FROM tx_enriched WHERE {cond}", params).fetchone()[0]
    rows = con.execute(f"""SELECT {', '.join(TX_COLUMNS)} FROM tx_enriched WHERE {cond}
                           ORDER BY tx_timestamp DESC, tx_id DESC LIMIT ? OFFSET ?""", params + [limit, offset]).fetchall()
    items = []
    for r in rows:
        d = dict(zip(TX_COLUMNS, r))
        d["tx_date"] = d["tx_date"].isoformat()
        d["tx_timestamp"] = d["tx_timestamp"].isoformat()
        d["tx_amount_eur"] = _eur(d["tx_amount_eur"])
        d["balance_after_eur"] = _eur(d["balance_after_eur"])
        items.append(d)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def customer_profile(customer_id: str) -> dict[str, Any]:
    """Age, age band and postal code (context for the Butler; no names exist in this data)."""
    con = get_conn()
    _check_customer(con, customer_id)
    age, band, postal = con.execute(
        "SELECT customer_age, age_band, customer_postal_code FROM customers WHERE customer_id = ?", [customer_id]).fetchone()
    return {"customer_id": customer_id, "age": age, "age_band": band, "postal_code": postal}

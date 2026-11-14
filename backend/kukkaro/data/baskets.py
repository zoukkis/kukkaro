"""S-Bank's three spending baskets, plus INCOME and TRANSFER for non-spending rows.

This module is the only place where transactions are mapped to baskets (root AGENTS.md §5.2).
Every rule below is based on docs/DATA_PROFILE.md: the dataset has 15 categories, each with
exactly one transaction_type, and purchases carry a merchant category code (MCC).

The same rules are used two ways, so they can never drift apart:
- `assign_basket()` classifies one transaction in Python (tests, receipts, ad-hoc use).
- `basket_sql()` / `subcategory_sql()` build the SQL used by the `tx_enriched` view in db.py.
"""
from __future__ import annotations

from enum import Enum


class Basket(str, Enum):
    MANDATORY_REGULAR = "MANDATORY_REGULAR"
    MANDATORY_IRREGULAR = "MANDATORY_IRREGULAR"
    EVERYDAY = "EVERYDAY"
    INCOME = "INCOME"
    TRANSFER = "TRANSFER"


# S-Bank's own labels (from their brief). Use these in every user-facing string.
BASKET_LABELS: dict[Basket, str] = {
    Basket.MANDATORY_REGULAR: "Regular essentials",
    Basket.MANDATORY_IRREGULAR: "Unexpected necessities",
    Basket.EVERYDAY: "Everyday spending",
    Basket.INCOME: "Income",
    Basket.TRANSFER: "Transfers and savings",
}
BASKET_ICONS: dict[Basket, str] = {
    Basket.MANDATORY_REGULAR: "🏠",
    Basket.MANDATORY_IRREGULAR: "🔧",
    Basket.EVERYDAY: "☕",
    Basket.INCOME: "💶",
    Basket.TRANSFER: "🔁",
}
SPENDING_BASKETS = (Basket.MANDATORY_REGULAR, Basket.MANDATORY_IRREGULAR, Basket.EVERYDAY)

R, I, E = Basket.MANDATORY_REGULAR, Basket.MANDATORY_IRREGULAR, Basket.EVERYDAY

# Default basket per dataset category.
CATEGORY_BASKET: dict[str, Basket] = {
    "Housing": R,          # rent or mortgage, one payment a month
    "Utilities": R,        # electricity, water, internet: about three bills a month
    "Groceries": R,        # food is an essential. Card data cannot split a grocery trip; receipts can (docs/WHY_RECEIPTS.md)
    "Transportation": R,   # commuting and fuel by default; taxis and parking are overridden below
    "Health": I,           # doctor, dentist, pharmacy: necessary but not planned
    "Home & Tech": I,      # repairs, furniture, appliances and electronics: necessary but irregular
    "Restaurants": E,      # eating out, fast food, bars: the classic leak
    "Entertainment": E,    # events, cinema, attractions
    "Lifestyle": E,        # clothes, sports gear, hobbies, books: mostly impulse
    "Travel": E,           # discretionary; S-Bank's model has three spending baskets, so non-essential = everyday
    "Salary": Basket.INCOME,
    "Other Income": Basket.INCOME,
    "Invest Deposit": Basket.TRANSFER,   # saving into investments, not spending
    "Invest Withdraw": Basket.TRANSFER,  # the customer's own money coming back, not earned income
    "Salary Sweep": Basket.TRANSFER,     # salary moved to another account
}

# MCC overrides inside a category, applied before the category default.
MCC_BASKET: dict[tuple[str, str], Basket] = {
    ("Transportation", "4121"): E,  # taxis: the spec's example of an everyday leak
    ("Transportation", "7523"): E,  # parking: convenience spending, often avoidable
}

# Fallback when a category is unknown (not seen in the profiled data).
TRANSACTION_TYPE_BASKET: dict[str, Basket] = {
    "housing_payment": R,
    "utilities_payment": R,
    "salary": Basket.INCOME,
    "other_income": Basket.INCOME,
    "investment_deposit": Basket.TRANSFER,
    "investment_withdrawal": Basket.TRANSFER,
    "salary_sweep": Basket.TRANSFER,
}

# Human-readable subcategory per MCC, so people can ask about "taxis" or "fast food".
MCC_SUBCATEGORY: dict[str, str] = {
    "5411": "Grocery stores", "5499": "Convenience and specialty food", "5422": "Butchers", "5451": "Dairy shops",
    "5812": "Eating places", "5814": "Fast food", "5813": "Bars",
    "5542": "Fuel", "5541": "Fuel", "7523": "Parking", "4111": "Public transport", "4121": "Taxis",
    "7922": "Tickets and shows", "7999": "Recreation", "7832": "Cinema", "7991": "Attractions", "7996": "Amusement parks",
    "5912": "Pharmacy", "8011": "Doctor", "8099": "Health services", "8021": "Dentist",
    "5200": "Home supplies", "5732": "Electronics", "5251": "Hardware", "5712": "Furniture", "5734": "Software",
    "5941": "Sports gear", "5651": "Clothing", "5999": "Other shops", "5691": "Clothing", "5942": "Books", "5945": "Toys and hobbies",
    "4722": "Travel agencies", "4511": "Flights", "7011": "Hotels", "7512": "Car rental",
}


def assign_basket(category: str | None, mcc_code: str | None, transaction_type: str | None, amount: float) -> Basket:
    """Basket for one transaction. `amount` is signed (negative = money out)."""
    if category is not None and mcc_code is not None and (category, mcc_code) in MCC_BASKET:
        return MCC_BASKET[(category, mcc_code)]
    if category in CATEGORY_BASKET:
        return CATEGORY_BASKET[category]
    if transaction_type in TRANSACTION_TYPE_BASKET:
        return TRANSACTION_TYPE_BASKET[transaction_type]
    # Unknown row: money in counts as income; money out stays visible as everyday spending.
    return Basket.INCOME if amount >= 0 else Basket.EVERYDAY


def subcategory(category: str | None, mcc_code: str | None) -> str | None:
    """Subcategory from the MCC. Rows without an MCC (bills, income, and the ~5% of purchases
    that have no merchant data) use their category name."""
    if mcc_code is not None and mcc_code in MCC_SUBCATEGORY:
        return MCC_SUBCATEGORY[mcc_code]
    return category


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def basket_sql(category: str = "category", mcc: str = "mcc_code", ttype: str = "transaction_type", amount: str = "tx_amount_eur") -> str:
    """SQL CASE expression equivalent to `assign_basket` (same rules, same order)."""
    whens = [f"WHEN {category} = {_q(c)} AND {mcc} = {_q(m)} THEN {_q(b.value)}" for (c, m), b in MCC_BASKET.items()]
    whens += [f"WHEN {category} = {_q(c)} THEN {_q(b.value)}" for c, b in CATEGORY_BASKET.items()]
    whens += [f"WHEN {ttype} = {_q(t)} THEN {_q(b.value)}" for t, b in TRANSACTION_TYPE_BASKET.items()]
    whens.append(f"WHEN {amount} >= 0 THEN {_q(Basket.INCOME.value)}")
    return "CASE " + " ".join(whens) + f" ELSE {_q(Basket.EVERYDAY.value)} END"


def subcategory_sql(category: str = "category", mcc: str = "mcc_code") -> str:
    """SQL CASE expression equivalent to `subcategory`."""
    whens = " ".join(f"WHEN {mcc} = {_q(m)} THEN {_q(s)}" for m, s in MCC_SUBCATEGORY.items())
    return f"CASE {whens} ELSE {category} END"

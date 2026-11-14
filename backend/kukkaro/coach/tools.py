"""DATA metrics exposed to the LLM as tools. Tools return dicts and never format numbers.

The customer ID is never a tool argument: the router binds it, so the model can only ever see
the signed-in customer's own data.
"""
from __future__ import annotations

from typing import Any, Callable

from kukkaro.coach.llm import ToolSpec
from kukkaro.data import metrics

DATE = {"type": "string", "description": "ISO date YYYY-MM-DD"}
CATEGORY = {"type": "string", "description": (
    "A category or subcategory name, or an everyday word for one. Categories: Groceries, Restaurants, "
    "Transportation, Utilities, Entertainment, Health, Home & Tech, Housing, Lifestyle, Travel. "
    "Subcategories include Taxis, Fast food, Bars, Eating places, Fuel, Parking, Public transport, Cinema, "
    "Pharmacy, Doctor, Dentist, Electronics, Clothing, Flights, Hotels. Words like 'taxi', 'takeaway' or 'rent' work.")}

SPECS: list[ToolSpec] = [
    ToolSpec("spending_summary",
             "Spending per basket (Regular essentials, Unexpected necessities, Everyday spending) and per category "
             "between two dates (both inclusive), plus income, transfers and the balance at the end. "
             "Use for 'where did my money go' and any total for a period.",
             {"type": "object", "properties": {"start": DATE, "end": DATE}, "required": ["start", "end"]}),
    ToolSpec("category_spend",
             "Total spent in one category or subcategory between two dates (inclusive), with a monthly breakdown "
             "and which basket it belongs to. Use for questions like 'how much on taxis last month'.",
             {"type": "object", "properties": {"category": CATEGORY, "start": DATE, "end": DATE},
              "required": ["category", "start", "end"]}),
    ToolSpec("safe_to_spend",
             "How much the customer can safely spend: the balance minus regular essentials still expected before the "
             "next salary. Returns amount_eur (total until the salary date), per_day_eur and this_week_eur "
             "(use this_week_eur for 'this week'), with all inputs.",
             {"type": "object", "properties": {}}),
    ToolSpec("what_if",
             "Monthly and yearly euro impact of changing spending in a category by a percentage (e.g. -50 for halving), "
             "based on the average month over the last 3 complete months.",
             {"type": "object", "properties": {"category": CATEGORY,
                                               "change_pct": {"type": "number", "description": "Percent change, -100 to +100"}},
              "required": ["category", "change_pct"]}),
    ToolSpec("spender_profile",
             "The customer's basket shares over the last 3 complete months compared with the median customer of the "
             "same age band. Use for 'what kind of spender am I'.",
             {"type": "object", "properties": {}}),
    ToolSpec("recurring_payments",
             "Recurring payments (housing, utility bills, savings transfers) with their typical month, the latest month "
             "and the change in percent, plus the salary pattern. Use for bills, rent, 'what went up'.",
             {"type": "object", "properties": {}}),
]

_FUNCS: dict[str, Callable[..., dict]] = {
    "spending_summary": lambda cid, a: metrics.spending_summary(cid, a["start"], a["end"]),
    "category_spend": lambda cid, a: metrics.category_spend(cid, a["category"], a["start"], a["end"]),
    "safe_to_spend": lambda cid, a: metrics.safe_to_spend(cid),
    "what_if": lambda cid, a: metrics.what_if(cid, a["category"], a["change_pct"]),
    "spender_profile": lambda cid, a: metrics.spender_profile(cid),
    "recurring_payments": lambda cid, a: metrics.recurring_payments(cid),
}


def executor(customer_id: str) -> Callable[[str, dict], dict[str, Any]]:
    """`execute(name, args)` bound to one customer. Bad input comes back as {"error": ...} for the model."""
    def execute(name: str, args: dict) -> dict[str, Any]:
        if name not in _FUNCS:
            return {"error": f"Unknown tool {name!r}"}
        try:
            return _FUNCS[name](customer_id, args or {})
        except metrics.DataError as e:
            return {"error": str(e)}
        except KeyError as e:
            return {"error": f"Missing argument {e}"}
    return execute

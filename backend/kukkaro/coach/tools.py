"""DATA metrics and RECEIPTS insights exposed to the LLM as tools. Tools return dicts and never
format numbers.

The customer ID is never a tool argument: the router binds it, so the model can only ever see
the signed-in customer's own data. Receipt tools work on synthetic example receipts and say so
(`synthetic: true`).
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable

from kukkaro.coach.llm import ToolSpec
from kukkaro.data import metrics

try:
    from kukkaro.receipts import insights as receipts
except ImportError:  # RECEIPTS not available: the coach still works on card data
    receipts = None

CENT = Decimal("0.01")


def _item_variants(item: str) -> list[str]:
    """Receipt items match by substring, so try the word as given and in the singular ("energy drinks")."""
    q = " ".join(str(item).lower().split())
    out = [q, q.rstrip("s"), " ".join(w.rstrip("s") if len(w) > 3 else w for w in q.split())]
    return list(dict.fromkeys(v for v in out if v))


def item_spend(customer_id: str, item: str, start, end) -> dict[str, Any]:
    """RECEIPTS' item_spend, also trying the singular. Raises DataError if no receipt item matches."""
    if receipts is None:
        raise metrics.DataError("Receipt data is not available")
    for v in _item_variants(item):
        r = receipts.item_spend(customer_id, v, start, end)
        if r["matched_items"]:
            return r
    raise metrics.DataError(f"No receipt items match {item!r}")


def item_what_if(customer_id: str, item: str, change_pct: float) -> dict[str, Any]:
    """Monthly and yearly impact of changing spending on one receipt item, based on the average month
    over the last 3 complete months: the same formula and rounding as metrics.what_if."""
    pct = Decimal(str(change_pct))
    if pct < -100:
        raise metrics.DataError("change_pct cannot be below -100 (that would be negative spending)")
    s, e, n = metrics.complete_months(metrics.get_today(), 3)
    r = item_spend(customer_id, item, s, e)
    baseline = (Decimal(str(r["total_eur"])) / n).quantize(CENT, rounding=ROUND_HALF_UP)
    monthly = (baseline * pct / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        "customer_id": customer_id, "name": item, "level": "item", "matched_items": r["matched_items"],
        "change_pct": float(pct), "baseline_monthly_eur": float(baseline), "monthly_change_eur": float(monthly),
        "yearly_change_eur": float(monthly * 12), "new_monthly_eur": float(baseline + monthly),
        "baskets": [{"basket": "EVERYDAY", "label": "Everyday spending"}] if r["matched_items"] else [],
        "based_on": {"start": s.isoformat(), "end": e.isoformat(), "months": n}, "synthetic": True,
        "formula": "monthly_change = baseline_monthly x change_pct / 100; yearly_change = monthly_change x 12",
    }

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

ITEM = {"type": "string", "description": "A grocery item in the singular, e.g. 'energy drink', 'candy', 'chips', "
                                          "'iced coffee', 'cinnamon bun', 'milk'"}
RECEIPT_SPECS: list[ToolSpec] = [
    ToolSpec("leak_items",
             "From the customer's synthetic example receipts: the top Everyday-spending items inside grocery trips "
             "(energy drinks, snacks, candy…) between two dates, by euros, with quantities and trips.",
             {"type": "object", "properties": {"start": DATE, "end": DATE}, "required": ["start", "end"]}),
    ToolSpec("item_spend",
             "From synthetic example receipts: spending on one grocery item between two dates (inclusive).",
             {"type": "object", "properties": {"item": ITEM, "start": DATE, "end": DATE}, "required": ["item", "start", "end"]}),
    ToolSpec("item_what_if",
             "From synthetic example receipts: monthly and yearly euro impact of changing spending on one grocery item "
             "by a percentage (e.g. -50 for halving energy drinks), based on the last 3 complete months.",
             {"type": "object", "properties": {"item": ITEM, "change_pct": {"type": "number", "description": "Percent change, -100 to +100"}},
              "required": ["item", "change_pct"]}),
    ToolSpec("store_brand_savings",
             "From synthetic example receipts: what switching branded grocery items to their store-brand twins would "
             "save per month and per year (last 3 complete months), with the top swaps.",
             {"type": "object", "properties": {}}),
]
ORDER_SPEC = ToolSpec(
    "plan_grocery_order",
    "Concept demo: prepare a week of the customer's usual groceries from their synthetic receipts, for delivery by robot, "
    "with the order total and whether it fits what is safe to spend this week. Treats (everyday items) are left out unless "
    "include_treats is true. It only prepares the order: the customer reviews and approves it in the app; nothing is "
    "bought or paid. Use when the user asks you to buy, order or shop groceries for them.",
    {"type": "object", "properties": {"include_treats": {"type": "boolean", "description": "Add the usual treats (energy drinks, snacks) back in"}}},
)

if receipts is not None:
    SPECS += RECEIPT_SPECS
    from kukkaro.orders import planner as _orders
    SPECS.append(ORDER_SPEC)
    _FUNCS["plan_grocery_order"] = lambda cid, a: _orders.plan_grocery_order(cid, bool(a.get("include_treats", False)))
    _FUNCS.update({
        "leak_items": lambda cid, a: receipts.leak_items(cid, a["start"], a["end"]),
        "item_spend": lambda cid, a: item_spend(cid, a["item"], a["start"], a["end"]),
        "item_what_if": lambda cid, a: item_what_if(cid, a["item"], a["change_pct"]),
        "store_brand_savings": lambda cid, a: receipts.store_brand_savings(cid),
    })


RESEARCH_SPEC = ToolSpec(
    "research_web",
    "Look up CURRENT outside information on the public web (prices, offers, Kela benefits, rent rules, consumer "
    "rights, where to buy a product). A separate public research service answers it from web pages with sources; "
    "it never sees the customer's data. Write ONE general question with no personal details: no IDs, no exact "
    "euro amounts (use rounded context like 'around 140 €'), no exact age (use a band like 'age 20–25'), no postal "
    "code (use the region). Returns facts, each with source numbers, and the numbered sources.",
    {"type": "object", "properties": {"question": {"type": "string", "description": "The anonymised question, max 300 characters"}},
     "required": ["question"]},
)
SPECS.append(RESEARCH_SPEC)

BLOCKED_HINT = ("Not sent: the question contains {problems}. Rewrite it as a general question without personal details "
                "(round amounts to tens, use an age band and the region) and call research_web again, or answer without "
                "the web search.")


class Executor:
    """`execute(name, args)` bound to one customer. Bad input comes back as {"error": ...} for the model.

    It also is the privacy gateway's hook: every tool result is remembered, so `research_web` can block a
    question that repeats one of the customer's exact figures. A blocked question gets one rewrite (by the
    model), the second block refuses. `research_log` records what was sent (sanitised text only) for
    "How I got this"."""

    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        self.results: list[Any] = []
        self.research_log: list[dict[str, Any]] = []
        self.blocked = 0
        try:
            p = metrics.customer_profile(customer_id)
            self.results.append({"age": p.get("age"), "postal_code_number": int(p["postal_code"]) if str(p.get("postal_code") or "").isdigit() else None})
        except Exception:
            pass

    def __call__(self, name: str, args: dict) -> dict[str, Any]:
        if name == "research_web":
            return self._research((args or {}).get("question", ""))
        if name not in _FUNCS:
            return {"error": f"Unknown tool {name!r}"}
        try:
            out = _FUNCS[name](self.customer_id, args or {})
        except metrics.DataError as e:
            return {"error": str(e)}
        except KeyError as e:
            return {"error": f"Missing argument {e}"}
        self.results.append(out)
        return out

    def _research(self, question: str) -> dict[str, Any]:
        from kukkaro.butler import research
        from kukkaro.coach import privacy

        v = privacy.check(question, self.results)
        if not v.ok:
            self.blocked += 1
            self.research_log.append({"question_sent": None, "blocked": v.problems, "sources": []})
            if self.blocked >= 2:
                return {"refused": True, "message": privacy.REFUSAL_TEXT}
            return {"error": BLOCKED_HINT.format(problems=", ".join(v.problems))}
        r = research.public_view(research.research(v.question))
        self.research_log.append({"question_sent": v.question, "blocked": [], "kind": r["kind"],
                                  "sources": r["sources"], "facts": len(r["facts"]), "error": r["error"]})
        return r


def executor(customer_id: str) -> Executor:
    return Executor(customer_id)

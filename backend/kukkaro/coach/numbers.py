"""Number checks for coach answers: which numbers in the text came from tools ("How I got this").

Used by the chat router (figures + unverified numbers) and by eval.py (the pass/fail check).
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

# 1,234.56 · 1 234,56 · 1234.56 · 61.4 · 2026
_NUM = re.compile(r"(?<![\w.])-?\d{1,3}(?:[ ,  ]\d{3})+(?:[.,]\d+)?(?!\d)|(?<![\w.])-?\d+(?:[.,]\d+)?(?!\d)")
EUR_KEYS = ("_eur",)
PCT_KEYS = ("_pct", "_pp")
COUNT_KEYS = ("transactions", "tx_count", "days_until_salary", "days_in_this_week", "months", "peer_customers",
              "payments", "months_present", "age")


def _to_decimal(raw: str) -> Decimal | None:
    s = raw.replace(" ", " ").replace(" ", " ")
    if re.fullmatch(r"-?\d{1,3}(?:[ ,]\d{3})+(?:[.,]\d+)?", s):
        # Thousands separators: the last [.,] group with 1-2 digits is decimals.
        m = re.fullmatch(r"(-?[\d ,]+?)([.,]\d{1,2})?", s)
        whole, frac = (m.group(1), m.group(2) or "") if m else (s, "")
        s = whole.replace(" ", "").replace(",", "") + frac.replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def numbers_in_text(text: str) -> list[Decimal]:
    out = []
    for raw in _NUM.findall(text or ""):
        d = _to_decimal(raw)
        if d is not None:
            out.append(abs(d))
    return out


def allowed_numbers(tool_calls: list[dict], extra_text: str = "") -> set[Decimal]:
    """Every number that appears in tool arguments or results (incl. digits inside dates), plus every
    number in `extra_text` (e.g. web sources), read the same way as answers ("8,18", "2 000")."""
    blob = json.dumps([{"a": c.get("args"), "r": c.get("result")} for c in tool_calls], ensure_ascii=False, default=str)
    allowed = {abs(d) for d in (_to_decimal(x) for x in re.findall(r"-?\d+(?:\.\d+)?", blob + " " + extra_text)) if d is not None}
    allowed |= set(numbers_in_text(extra_text))
    return {d.normalize() for d in allowed}


def unverified_numbers(answer: str, tool_calls: list[dict], extra_text: str = "") -> list[str]:
    """Numbers in the answer that no tool produced (should be empty)."""
    allowed = allowed_numbers(tool_calls, extra_text)
    bad = []
    for d in numbers_in_text(answer):
        if d.normalize() not in allowed:
            bad.append(format(d.normalize(), "f"))
    return sorted(set(bad), key=lambda x: Decimal(x))


def _unit(key: str) -> str | None:
    if key.endswith(EUR_KEYS):
        return "EUR"
    if key.endswith(PCT_KEYS):
        return "%"
    if key in COUNT_KEYS:
        return "count"
    return None


def _period(d: dict) -> str | None:
    for k in ("period", "based_on", "typical_month_based_on"):
        p = d.get(k)
        if isinstance(p, dict) and p.get("start"):
            return f"{p['start']} to {p['end']}"
    if d.get("today") and d.get("until_date"):
        return f"{d['today']} to {d['until_date']}"
    return None


def _walk(obj: Any, path: list[str], context: dict, out: list[dict]) -> None:
    if isinstance(obj, dict):
        ctx = dict(context)
        if _period(obj):
            ctx["period"] = _period(obj)
        for k in ("label", "name", "category"):
            if isinstance(obj.get(k), str):
                ctx["what"] = obj[k]
                break
        for k, v in obj.items():
            _walk(v, path + [k], ctx, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, path, context, out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        unit = _unit(path[-1]) if path else None
        if unit:
            label = path[-1].replace("_eur", "").replace("_pct", " %").replace("_", " ").strip()
            if context.get("what"):
                label = f"{context['what']} · {label}"
            out.append({"label": label, "value": obj, "unit": unit, "source": context.get("period") or "your data"})


_COUNT_NOUN = r"\s+(?:trips?|transactions?|rides?|visits?|purchases?|payments?|days?|bills?|customers?)\b"


def figures(answer: str, tool_calls: list[dict]) -> list[dict]:
    """The tool numbers that the answer actually uses, with label, unit and period. Counts only
    match when the answer says what they count ("9 trips"), so "last 3 months" is not a figure."""
    used = {d.normalize() for d in numbers_in_text(answer)}
    found: list[dict] = []
    for c in tool_calls:
        res = c.get("result")
        if isinstance(res, dict) and "error" not in res:
            _walk(res, [], {"tool": c.get("name")}, found)
    seen, out = set(), []
    for f in found:
        key = Decimal(str(abs(f["value"]))).normalize()
        if key not in used or key in seen or key == 0:
            continue
        if f["unit"] == "count" and not re.search(rf"(?<![\d.,]){f['value']}{_COUNT_NOUN}", answer, re.IGNORECASE):
            continue
        seen.add(key)
        out.append(f)
    return out

"""Privacy gateway between Kukkaro's two zones (root AGENTS.md §4).

Trusted zone: Gemma 4 sees the customer's own data (through the deterministic tools).
Public zone:  Exa + Gemini research the open web and never see customer data.

Everything that crosses from the trusted zone to the public zone is ONE short question, written by
Gemma, that must pass `check()` here in code before it leaves. Blocked: customer, account, merchant
and transaction IDs, postal codes, exact euro amounts (with cents, or a number that equals one of the
customer's own figures), exact ages, names, emails, phone numbers and street addresses. Allowed:
rounded or banded context ("rent around 600 €", "age 20–25", "Espoo region").

`banded_context()` turns the customer's profile into such safe context deterministically.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

MAX_QUESTION_CHARS = 300

REFUSAL_TEXT = ("I can't search the web for that without sharing details about your own data, so I left the web "
                "search out. Ask the question in general terms (for example \"typical electricity prices in Finland\") "
                "and I'll look it up.")

_RULES: list[tuple[str, re.Pattern]] = [
    ("customer ID", re.compile(r"\bCUST[\s_-]?\d+\b", re.IGNORECASE)),
    ("account ID", re.compile(r"\bACC[\s_-]?\d+\b|\bFI\d{2}(?:\s?\d{4}){3,4}\b", re.IGNORECASE)),
    ("merchant ID", re.compile(r"\bMRC-[A-Z]{2,5}-\d+\b", re.IGNORECASE)),
    ("transaction ID", re.compile(r"\b[A-Z]{2,6}\d{3,}-\d+\b")),
    ("email address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("phone number", re.compile(r"(?:\+358|\b0)\s?\d{1,3}[\s-]?\d{3}[\s-]?\d{2,4}\b")),
    ("postal code", re.compile(r"(?<![\d.,])\d{5}(?![\d.,])")),
    ("exact amount", re.compile(r"(?<![\d.,])\d+[.,]\d{2}(?![\d])\s*(?:€|eur|euro|e\b)?", re.IGNORECASE)),
    ("exact age", re.compile(r"\b(?:age[d]?|ikä)\s*:?\s*\d{1,3}\b(?!\s*[–—-]\s*\d)|\b\d{1,3}[\s-]?(?:years?[\s-]old|v(?:uotias|\.))\b",
                             re.IGNORECASE)),
    ("name", re.compile(r"\b(?:my name is|minun nimeni on|i am called|nimeni on)\s+[A-ZÅÄÖ][a-zåäö]+", re.IGNORECASE)),
    ("street address", re.compile(r"\b[A-ZÅÄÖ][a-zåäö]+(?:katu|tie|polku|kuja|väylä|bulevardi|ranta|street|road)\s+\d+", re.IGNORECASE)),
]
_NUM = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?(?![\w])")


@dataclass
class Verdict:
    ok: bool
    question: str
    problems: list[str] = field(default_factory=list)


def _private_numbers(values: Iterable[Any]) -> set[Decimal]:
    """The customer's own figures that are too exact to share: anything with decimals, and whole
    numbers that are not round (a multiple of 10). Round numbers like 600 are fine to share."""
    out: set[Decimal] = set()

    def visit(v: Any) -> None:
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            d = Decimal(str(abs(v))).normalize()
            if d != d.to_integral_value() or (d >= 10 and d % 10 != 0):
                out.add(d)
        elif isinstance(v, dict):
            for x in v.values():
                visit(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                visit(x)
    for v in values:
        visit(v)
    return out


def check(question: str, private_values: Iterable[Any] = ()) -> Verdict:
    """Is this question safe to send to the public zone? `private_values` are the customer's tool
    results in this turn: a number in the question equal to one of their exact figures is blocked
    even without cents ("my bill is 145 €" when the bill was 144.73 is fine; "144.73" is not)."""
    q = " ".join(str(question or "").split())
    problems: list[str] = []
    if not q:
        problems.append("empty question")
    if len(q) > MAX_QUESTION_CHARS:
        problems.append(f"longer than {MAX_QUESTION_CHARS} characters")
    for label, rx in _RULES:
        if rx.search(q):
            problems.append(label)
    private = _private_numbers(private_values)
    if private:
        for raw in _NUM.findall(q):
            try:
                d = Decimal(raw.replace(",", ".")).normalize()
            except InvalidOperation:
                continue
            if d in private and "customer's exact figure" not in problems:
                problems.append("customer's exact figure")
    return Verdict(ok=not problems, question=q, problems=problems)


# First two digits of a Finnish postal code -> region. Only the capital area is spelled out; the rest is
# "Finland", which is all a price or benefit search needs.
_REGIONS = {"00": "Helsinki region", "01": "Vantaa region", "02": "Espoo region"}


def region(postal_code: str | None) -> str:
    return _REGIONS.get(str(postal_code or "")[:2], "Finland")


def age_band(age: int | None) -> str | None:
    if age is None:
        return None
    lo = (int(age) // 5) * 5
    return f"age {lo}–{lo + 5}"


def round_eur(v: float | None, step: int = 10) -> str | None:
    if v is None:
        return None
    return f"around {int(round(float(v) / step) * step)} €"


def banded_context(profile: dict[str, Any]) -> str:
    """Safe, banded context from the customer's profile (age, postal code), e.g. "Espoo region, age 20–25"."""
    parts = [region(profile.get("postal_code")), age_band(profile.get("age"))]
    return ", ".join(p for p in parts if p)

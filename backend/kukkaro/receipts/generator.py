"""Synthetic grocery receipts for card transactions (no real receipt data anywhere).

- Deterministic: the RNG is seeded with the transaction's `tx_id`, so a transaction always gets the
  same receipt, and personas are seeded with `customer_id`, so habits repeat across weeks.
- Exact: line totals (in whole cents) always add up to the card amount. The last line is a weighed
  produce item that absorbs the remainder, as on a real receipt where produce is sold by weight.
- Only for Groceries purchases up to MAX_RECEIPT_EUR (DECISIONS.md 12:31); bigger trips get none.
- Channel: always "in_store" for now; online orders come later (AGENTS.md 4b, M3).
"""
from __future__ import annotations

import csv
import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from kukkaro.receipts.models import Receipt, ReceiptItem

MAX_RECEIPT_EUR = Decimal("300")
CATALOG_PATH = Path(__file__).with_name("catalog.csv")
PRODUCE_BY_WEIGHT = ("Vegetables & fruit (by weight)", "produce", 3.49)  # name, category, €/kg


@dataclass(frozen=True)
class Product:
    name: str
    category: str
    price_cents: int
    basket: str
    store_brand: bool
    typical_qty: int
    twin: str  # name of the store-brand twin, "" if none


@dataclass
class Persona:
    customer_id: str
    leak_share: float                 # typical share of a trip spent on EVERYDAY items
    favourite_leaks: list[str]        # bought again and again
    leak_weights: list[float]
    staples: list[str]                # the customer's usual basket
    store_brand_pref: float           # probability of picking the store-brand twin
    irregular_rate: float = 0.04      # chance per trip of a pharmacy-shelf / household necessity
    notes: dict = field(default_factory=dict)


def _rng(key: str) -> random.Random:
    return random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:16], 16))


@lru_cache(maxsize=1)
def catalog() -> dict[str, Product]:
    with CATALOG_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        out[r["name"]] = Product(
            name=r["name"], category=r["category"],
            price_cents=int((Decimal(r["unit_price_eur"]) * 100).to_integral_value()),
            basket=r["basket"], store_brand=r["store_brand"].strip().lower() == "true",
            typical_qty=max(1, int(r.get("typical_qty") or 1)), twin=(r.get("twin") or "").strip())
    return out


def _by_basket(basket: str, *, store_brand: bool | None = None) -> list[Product]:
    return [p for p in catalog().values() if p.basket == basket
            and (store_brand is None or p.store_brand == store_brand)]


# Demo tuning: the demo customer (DECISIONS.md, CUST02979, age 22) gets clear, recurring leak
# habits so the With/Without receipts story is easy to see. Still 100 % synthetic.
DEMO_PERSONAS = {
    "CUST02979": dict(leak_share=0.27, favourite_leaks=["Energy drink 0.5 l", "Cinnamon bun",
                      "Pick-and-mix candy 200 g", "Potato chips 275 g", "Iced coffee 250 ml"],
                      leak_weights=[5, 3, 3, 2, 2], store_brand_pref=0.15),
}


def make_persona(customer_id: str, age: int | None) -> Persona:
    """Stable habits for one customer, seeded by `customer_id` (younger = a bit more snacking)."""
    rng = _rng("persona:" + customer_id)
    age = age or 40
    base = 0.24 if age < 30 else 0.18 if age < 50 else 0.13
    leaks = [p.name for p in _by_basket("EVERYDAY")]
    if age < 20:
        leaks = [n for n in leaks if not n.startswith(("Beer", "Cider"))]  # no alcohol under 20
    fav = rng.sample(leaks, k=min(5, len(leaks)))
    regular = [p.name for p in _by_basket("MANDATORY_REGULAR", store_brand=False)]
    staples = rng.sample(regular, k=min(18, len(regular)))
    p = Persona(customer_id=customer_id,
                leak_share=round(min(0.45, max(0.05, rng.gauss(base, 0.06))), 3),
                favourite_leaks=fav, leak_weights=[rng.choice([1, 2, 3, 4]) for _ in fav],
                staples=staples, store_brand_pref=round(rng.uniform(0.05, 0.85), 2))
    for k, v in DEMO_PERSONAS.get(customer_id, {}).items():
        setattr(p, k, v)
    return p


def _store_name(merchant_id: str | None, mcc: str | None) -> str:
    if mcc == "5499":
        return "Alepa (synthetic)"
    if mcc == "5422":
        return "Butcher counter (synthetic)"
    if mcc == "5451":
        return "Dairy shop (synthetic)"
    chains = ["S-market (synthetic)", "Prisma (synthetic)", "Sale (synthetic)"]
    return chains[int(hashlib.sha256((merchant_id or "none").encode()).hexdigest(), 16) % len(chains)]


def _line(p: Product, qty: int) -> ReceiptItem:
    return ReceiptItem(name=p.name, category=p.category, qty=qty, unit_price_eur=p.price_cents / 100,
                       line_total_eur=p.price_cents * qty / 100, basket=p.basket, store_brand=p.store_brand)


def generate(tx: dict, persona: Persona) -> Receipt | None:
    """Receipt for one card transaction dict with keys tx_id, tx_amount_eur, tx_timestamp,
    category, merchant_id, mcc_code. Returns None if this transaction gets no receipt."""
    amount = -Decimal(str(tx["tx_amount_eur"]))
    if tx.get("category") != "Groceries" or amount <= 0 or amount > MAX_RECEIPT_EUR:
        return None
    total = int((amount * 100).to_integral_value())
    rng = _rng("receipt:" + tx["tx_id"])
    cat = catalog()
    lines: list[tuple[Product, int]] = []
    remaining = total

    def add(p: Product, qty: int) -> bool:
        nonlocal remaining
        while qty > 0 and p.price_cents * qty > remaining:
            qty -= 1
        if qty <= 0:
            return False
        lines.append((p, qty))
        remaining -= p.price_cents * qty
        return True

    # 1) Everyday leaks: the persona's favourites, roughly leak_share of the trip.
    leak_budget = int(total * max(0.0, rng.gauss(persona.leak_share, 0.07)))
    spent_leaks, tries = 0, 0
    while spent_leaks < leak_budget and tries < 40:
        tries += 1
        p = cat[rng.choices(persona.favourite_leaks, weights=persona.leak_weights)[0]]
        room = leak_budget - spent_leaks
        qty = min(rng.randint(1, p.typical_qty), max(1, room // p.price_cents))
        if p.price_cents * qty > room + p.price_cents // 2:
            continue  # would overshoot the leak budget too much; try a cheaper favourite
        before = remaining
        if add(p, qty):
            spent_leaks += before - remaining

    # 2) Now and then an unexpected necessity from the shelf.
    if rng.random() < persona.irregular_rate:
        add(rng.choice(_by_basket("MANDATORY_IRREGULAR")), 1)

    # 3) Staples until the trip is (nearly) filled; keep some room for weighed produce.
    reserve = min(total // 10, 600)
    tries = 0
    while remaining > reserve and tries < 200:
        tries += 1
        p = cat[rng.choice(persona.staples)]
        if p.twin and p.twin in cat and rng.random() < persona.store_brand_pref:
            p = cat[p.twin]
        add(p, rng.randint(1, p.typical_qty))
        if remaining <= 0:
            break

    merged: dict[str, list] = {}  # one line per product, as on a real receipt
    for p, q in lines:
        merged.setdefault(p.name, [p, 0])[1] += q
    items = [_line(p, q) for p, q in merged.values()]
    # 4) Weighed produce absorbs the exact remainder (a real receipt line: price per kg x weight).
    if remaining > 0:
        name, category, per_kg = PRODUCE_BY_WEIGHT
        kg = round(remaining / 100 / per_kg, 3) or 0.001
        items.append(ReceiptItem(name=name, category=category, qty=kg, unit_price_eur=per_kg,
                                 line_total_eur=remaining / 100, basket="MANDATORY_REGULAR"))
    assert sum(int(round(i.line_total_eur * 100)) for i in items) == total  # never a mismatch

    ts = tx.get("tx_timestamp")
    ts = ts.isoformat() if isinstance(ts, datetime) else str(ts or tx.get("tx_date", ""))
    return Receipt(tx_id=tx["tx_id"], store=_store_name(tx.get("merchant_id"), tx.get("mcc_code")),
                   timestamp=ts, total_eur=total / 100, items=items)

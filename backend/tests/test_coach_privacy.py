"""Privacy gateway (coach/privacy.py): leaking questions are blocked, good questions pass."""
from __future__ import annotations

import pytest

from test_data_fixture import data_env  # noqa: F401  (pytest fixture)

from kukkaro.coach import privacy


@pytest.mark.parametrize("question, problem", [
    ("Is 144.73 € a high electricity bill for CUST02979?", "customer ID"),
    ("Electricity prices for account ACC002979", "account ID"),
    ("What does merchant MRC-GRO-0056 sell?", "merchant ID"),
    ("Receipt CUST02979-740 prices", "transaction ID"),
    ("Is a 144.73 € monthly utility bill high in Finland?", "exact amount"),
    ("Is a 144,73 e monthly bill normal?", "exact amount"),
    ("Kela housing allowance in 02360 Espoo", "postal code"),
    ("Housing allowance rules for someone aged 22", "exact age"),
    ("Is 22-year-old eligible for student benefits?", "exact age"),
    ("Contact me at matti.meikalainen@example.fi about prices", "email address"),
    ("Call +358 40 123 4567 about electricity offers", "phone number"),
    ("My name is Matti, cheap electricity?", "name"),
    ("Rent rules for Mannerheimintie 12", "street address"),
])
def test_leaking_questions_are_blocked(question, problem):
    v = privacy.check(question)
    assert not v.ok and problem in v.problems


def test_customers_exact_figure_is_blocked_even_without_cents():
    tool_results = [{"utility_bills_latest_month_eur": 145.0, "rent_typical_monthly_eur": 611.56, "salary_eur": 2200}]
    assert "customer's exact figure" in privacy.check("Is a 145 € utility bill high?", tool_results).problems
    assert "customer's exact figure" in privacy.check("Is rent of 611.56 normal?", tool_results).problems
    # round numbers stay allowed, even when they happen to equal a figure
    assert privacy.check("Is rent around 600 € normal for a one-bedroom flat?", tool_results).ok
    assert privacy.check("Kela housing allowance income limit for salary around 2200 €", tool_results).ok


@pytest.mark.parametrize("question", [
    "Average electricity prices in Finland in November 2026 for a small flat",
    "Is a monthly utility bill around 140 € high for a one-person flat in the Espoo region?",
    "Kela general housing allowance income limits for one adult, age 20–25, rent around 600 €",
    "Can a landlord raise rent mid-contract in Finland?",
    "Where can I buy cheap oat milk 1 l in Finland?",
    "Fixed-price vs spot electricity contracts in 2026",
])
def test_good_questions_pass(question):
    v = privacy.check(question)
    assert v.ok, v.problems


def test_empty_and_too_long_questions_are_blocked():
    assert not privacy.check("   ").ok
    assert "longer than 300 characters" in privacy.check("electricity " * 40).problems


def test_banded_context_is_safe():
    ctx = privacy.banded_context({"age": 22, "postal_code": "02360"})
    assert ctx == "Espoo region, age 20–25"
    assert privacy.check(f"Electricity prices, {ctx}").ok
    assert privacy.region("33100") == "Finland" and privacy.round_eur(144.73) == "around 140 €"


def test_research_web_tool_blocks_rewrites_and_refuses(data_env, monkeypatch):
    from kukkaro.butler import research
    from kukkaro.coach import tools

    sent = []
    monkeypatch.setattr(research, "research", lambda q, use_cache=True: sent.append(q) or {
        "question": q, "kind": "market", "facts": [{"text": "Fixed price 9,89 snt/kWh.", "sources": [1]}],
        "sources": [{"n": 1, "title": "Vertailu", "url": "https://www.sahkovertaaja.fi/", "published_date": None, "text": "x"}],
        "error": None})
    ex = tools.Executor("C1")
    ex.results.append({"utility_bills_latest_month_eur": 144.73})
    first = ex("research_web", {"question": "Is a 144.73 € electricity bill high for CUST02979?"})
    assert "Not sent" in first["error"] and sent == []
    ok = ex("research_web", {"question": "Is a monthly utility bill around 140 € high in Finland?"})
    assert sent == ["Is a monthly utility bill around 140 € high in Finland?"]
    assert ok["question_sent"] == sent[0] and ok["sources"][0]["url"].startswith("https://") and "text" not in ok["sources"][0]
    again = ex("research_web", {"question": "bill 144.73"})
    assert again["refused"] is True and len(sent) == 1
    assert [x["question_sent"] for x in ex.research_log] == [None, sent[0], None]

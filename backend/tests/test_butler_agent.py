"""Butler guards without network: fake Exa results and fake LLM output."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_data_fixture import data_env  # noqa: F401  (pytest fixture)

from kukkaro.butler import agent, exa_client
from kukkaro.coach import llm

SOURCES = [{"query": "q", "domains": exa_client.OFFICIAL_DOMAINS, "cached": False, "results": [
    {"title": "Yleinen asumistuki", "url": "https://www.kela.fi/yleinen-asumistuki", "published_date": "2026-03-01",
     "highlights": ["Tuloraja 1 844 € kuukaudessa yhdelle aikuiselle. Kysymykset: asumistuki@kela.fi"]},
    {"title": "Laskuri", "url": "https://laskurit.kela.fi/yleisen-asumistuen-laskuri", "published_date": None,
     "highlights": ["Laske arvio asumistuesta."]},
    {"title": "No text", "url": "https://example.com/empty", "published_date": None, "highlights": []},
]}]


def fake_llm(answer_json):
    """complete_json stand-in. Records (system, prompt, provider) so tests can check what each zone saw."""
    calls = []

    def complete_json(system, prompt, schema, provider=None, fallback_provider=None):
        calls.append({"system": system, "prompt": prompt, "provider": provider})
        r = llm.RunResult(text="{}", model="fake", host="google", provider=provider or "gemini")
        props = schema["properties"]
        if "kind" in props:            # research worker: plan
            return {"kind": "official", "searches": ["Kela yleinen asumistuki tulorajat"]}, r
        if "facts" in props:           # research worker: facts from the pages
            return {"facts": [{"text": "Tuloraja 1 844 € kuukaudessa yhdelle aikuiselle.", "sources": [1]},
                              {"text": "Kela has an allowance calculator.", "sources": [2]},
                              {"text": "Made up", "sources": [7]}]}, r
        if "question" in props:        # gateway rewrite
            return {"question": "Kela housing allowance rules"}, r
        return answer_json, r          # trusted zone: the answer
    return complete_json, calls


@pytest.fixture(autouse=True)
def empty_answer_cache(data_env):
    import shutil
    shutil.rmtree(data_env["root"] / "cache" / "butler", ignore_errors=True)
    shutil.rmtree(data_env["root"] / "cache" / "research", ignore_errors=True)


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setattr(exa_client, "search_many", lambda queries: SOURCES)

    def use(answer_json):
        fn, calls = fake_llm(answer_json)
        monkeypatch.setattr(llm, "complete_json", fn)
        return calls
    return use


def test_context_comes_from_data_tools(data_env):
    ctx = agent.user_context("C1")
    assert (ctx["age"], ctx["postal_code"], ctx["rent_typical_monthly_eur"], ctx["salary_average_monthly_eur"]) == (30, "02150", 800.0, 2500.0)
    assert ctx["utility_bills_typical_monthly_eur"] == 50.0 and ctx["utility_bills_change_pct"] == 0.0


def test_guards(data_env, fakes):
    calls = fakes({
        "answer": "You are eligible [1]. Your average salary in your bank data (2500.0 €) is above the 1 844 € limit [1] [9].",
        "next_steps": ["Use the calculator [2]", "You qualify, so apply"],
        "draft": {"kind": "email", "to": "boss@invented.fi", "subject": "Asumistuki", "body": "Hei, palkkani on 2500.0 €.", "source_n": 2},
    })
    r = agent.run("C1", "Am I eligible for housing allowance?")
    assert "You are eligible" not in r["answer"] and r["answer"].startswith("You may be eligible")
    assert "[9]" not in r["answer"]                                   # citation to a source that does not exist
    assert [s["n"] for s in r["sources"]] == [1, 2]                   # the source without text is dropped
    assert r["sources"][0]["cited"] is True and r["sources"][1]["cited"] is False
    assert r["next_steps"][1] == "You may be eligible, so apply"
    assert r["draft"]["to"] is None                                   # address not in any source
    assert r["draft"]["open_url"] == "https://laskurit.kela.fi/yleisen-asumistuen-laskuri"
    assert r["draft"]["mailto"].startswith("mailto:?subject=Asumistuki")
    assert r["unverified_numbers"] == []                              # 2500.0 from data, 1 844 from the source
    answer_call = calls[-1]
    assert "Today is" in answer_call["prompt"] and "[1] Yleinen asumistuki" in answer_call["prompt"]
    assert answer_call["provider"] == "gemma"                         # the trusted zone writes the answer
    assert r["zones"] == ["trusted", "public"] and r["fallback"] is False


def test_public_zone_never_sees_customer_data(data_env, fakes):
    calls = fakes({"answer": "Info [1].", "next_steps": [], "draft": {"kind": "none", "subject": "", "body": ""}})
    r = agent.run("C1", "Am I eligible for housing allowance?")
    sent = r["research"]["question_sent"]
    assert sent == "Am I eligible for housing allowance? (Espoo region, age 30–35)"
    public = [c for c in calls if c["provider"] == "gemini"]          # research plan + facts
    assert len(public) == 2
    for c in public:
        for private in ("C1", "02150", "2500", "800.0", "age\": 30"):
            assert private not in c["prompt"], private
    assert "2500.0" in calls[-1]["prompt"]                            # only the trusted zone sees the figures


def test_leaking_task_is_rewritten_once_or_refused(data_env, fakes, monkeypatch):
    calls = fakes({"answer": "Info [1].", "next_steps": [], "draft": {"kind": "none", "subject": "", "body": ""}})
    r = agent.run("C1", "Housing allowance for C1, salary 2500.55 €, postal code 02150?")
    assert r["research"]["question_sent"].startswith("Kela housing allowance rules")
    assert calls[0]["provider"] == "gemma"                            # the rewrite happens in the trusted zone
    from kukkaro.butler import agent as a
    fn, _ = fake_llm({})
    monkeypatch.setattr(llm, "complete_json", lambda *x, **k: ({"question": "still 02150"}, llm.RunResult(text="")))
    r2 = a.run("C1", "Rent rules at 02150, my rent is 800.00 €", use_cache=False)
    assert r2["error"] == "blocked" and r2["research"]["question_sent"] is None and r2["sources"] == []


def test_address_from_a_source_is_kept_and_invented_numbers_flagged(data_env, fakes):
    fakes({"answer": "Ask Kela [1]. The allowance is 377 € a month [1].", "next_steps": [],
           "draft": {"kind": "email", "to": "asumistuki@kela.fi", "subject": "Kysymys", "body": "Hei", "source_n": 1}})
    r = agent.run("C1", "Housing allowance?")
    assert r["draft"]["to"] == "asumistuki@kela.fi"
    assert r["unverified_numbers"] == ["377"]


def test_no_draft_and_no_sources(data_env, fakes, monkeypatch):
    fakes({"answer": "Info [1].", "next_steps": [], "draft": {"kind": "none", "subject": "", "body": ""}})
    first = agent.run("C1", "What is Kela?")
    assert first["draft"] is None and first["cached"] is False
    monkeypatch.setattr(exa_client, "search_many", lambda q: [{"query": "x", "domains": None, "results": [], "error": "down"}])
    again = agent.run("C1", "  what is KELA? ")                     # same task, normalised: from the cache
    assert again["cached"] is True and again["answer"] == first["answer"]
    r = agent.run("C1", "What is Kela?", use_cache=False)            # live again: no sources now
    assert r["sources"] == [] and r["error"] == "no sources" and "won't guess" in r["answer"]
    assert agent.run("C1", "What is Kela?")["cached"] is True         # the failure was not cached over the good answer


def test_route(data_env, fakes):
    fakes({"answer": "Info [1].", "next_steps": ["Check [1]"], "draft": {"kind": "none", "subject": "", "body": ""}})
    from kukkaro.api.main import app
    with TestClient(app) as c:
        assert "kukkaro.butler.router" in c.get("/api/health").json()["routers"]
        r = c.post("/api/butler", json={"customer_id": "C1", "task": "What is Kela?"})
        assert r.status_code == 200 and r.json()["sources"][0]["url"].startswith("https://www.kela.fi")
        assert c.post("/api/butler", json={"customer_id": "NOPE", "task": "What is Kela?"}).status_code == 404
        assert c.post("/api/butler", json={"customer_id": "C1", "task": ""}).status_code == 422


def test_suggestions_only_for_bills_that_rose(data_env, monkeypatch):
    from kukkaro.data import metrics
    fake = {"recurring": [
        {"name": "Utilities", "category": "Utilities", "change_pct": 120.3, "latest_month": "2026-09", "latest_month_eur": 144.73, "typical_monthly_eur": 65.7},
        {"name": "Housing", "category": "Housing", "change_pct": -0.7, "latest_month": "2026-09", "latest_month_eur": 607.12, "typical_monthly_eur": 611.56},
        {"name": "Invest Deposit", "category": "Invest Deposit", "change_pct": 80.0, "latest_month": "2026-09", "latest_month_eur": 90.0, "typical_monthly_eur": 50.0},
        {"name": "Groceries merchant X", "category": "Groceries", "change_pct": None, "latest_month": "2026-09", "latest_month_eur": 1.0, "typical_monthly_eur": 0.0}]}
    monkeypatch.setattr(metrics, "recurring_payments", lambda cid: fake)
    r = agent.suggestions("C1")
    assert [c["category"] for c in r["suggestions"]] == ["Utilities"]          # savings transfers and falls are not cards
    c = r["suggestions"][0]
    assert (c["title"], c["change_pct"], c["latest_month_eur"], c["typical_monthly_eur"]) == ("Your utility bills went up", 120.3, 144.73, 65.7)
    assert "electricity" not in c["title"].lower() and c["task"].startswith("My utility bills went up")


def test_suggestions_route(data_env):
    from kukkaro.api.main import app
    with TestClient(app) as c:
        r = c.get("/api/customers/C1/butler/suggestions")
        assert r.status_code == 200 and r.json()["suggestions"] == []           # C1's bills are flat
        assert c.get("/api/customers/NOPE/butler/suggestions").status_code == 404

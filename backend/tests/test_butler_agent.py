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
    calls = []

    def complete_json(system, prompt, schema, provider=None):
        calls.append(prompt)
        r = llm.RunResult(text="{}", model="fake", host="google", provider="gemini")
        if "searches" in schema["properties"]:
            return {"searches": [{"query": "Kela yleinen asumistuki tulorajat", "official_only": True}]}, r
        return answer_json, r
    return complete_json, calls


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
    assert "Today is" in calls[1] and "[1] Yleinen asumistuki" in calls[1]


def test_address_from_a_source_is_kept_and_invented_numbers_flagged(data_env, fakes):
    fakes({"answer": "Ask Kela [1]. The allowance is 377 € a month [1].", "next_steps": [],
           "draft": {"kind": "email", "to": "asumistuki@kela.fi", "subject": "Kysymys", "body": "Hei", "source_n": 1}})
    r = agent.run("C1", "Housing allowance?")
    assert r["draft"]["to"] == "asumistuki@kela.fi"
    assert r["unverified_numbers"] == ["377"]


def test_no_draft_and_no_sources(data_env, fakes, monkeypatch):
    fakes({"answer": "Info [1].", "next_steps": [], "draft": {"kind": "none", "subject": "", "body": ""}})
    assert agent.run("C1", "What is Kela?")["draft"] is None
    monkeypatch.setattr(exa_client, "search_many", lambda q: [{"query": "x", "domains": None, "results": [], "error": "down"}])
    r = agent.run("C1", "What is Kela?")
    assert r["sources"] == [] and r["error"] == "no sources" and "won't guess" in r["answer"]


def test_route(data_env, fakes):
    fakes({"answer": "Info [1].", "next_steps": ["Check [1]"], "draft": {"kind": "none", "subject": "", "body": ""}})
    from kukkaro.api.main import app
    with TestClient(app) as c:
        assert "kukkaro.butler.router" in c.get("/api/health").json()["routers"]
        r = c.post("/api/butler", json={"customer_id": "C1", "task": "What is Kela?"})
        assert r.status_code == 200 and r.json()["sources"][0]["url"].startswith("https://www.kela.fi")
        assert c.post("/api/butler", json={"customer_id": "NOPE", "task": "What is Kela?"}).status_code == 404
        assert c.post("/api/butler", json={"customer_id": "C1", "task": ""}).status_code == 422

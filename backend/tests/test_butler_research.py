"""Public-zone research worker (butler/research.py) and the S-Group rule, without network."""
from __future__ import annotations

import pytest
from test_data_fixture import data_env  # noqa: F401  (pytest fixture)

from kukkaro.butler import exa_client, research
from kukkaro.coach import llm
from kukkaro.coach.prompts import S_GROUP_RULE, system_prompt


def _results(*rows):
    return [{"query": "q", "domains": [], "results": [
        {"title": t, "url": u, "published_date": None, "highlights": [h]} for t, u, h in rows]}]


@pytest.fixture
def fake_world(data_env, monkeypatch):
    import shutil
    shutil.rmtree(data_env["root"] / "cache" / "research", ignore_errors=True)
    seen = {"queries": [], "prompts": []}

    def search_many(queries):
        seen["queries"] += queries
        return _results(
            ("Kaurajuoma 1 l | S-kaupat", "https://www.s-kaupat.fi/tuote/kaurajuoma-1l/123", "Rainbow kaurajuoma 1 l 1,19 €"),
            ("Kaurajuoma | K-Ruoka", "https://www.k-ruoka.fi/kauppa/tuote/kaurajuoma", "Pirkka kaurajuoma 1,09 €"),
            ("Lidl oat drink", "https://www.lidl.fi/p/oat", "Oat drink 0,99 €"),
        )

    def complete_json(system, prompt, schema, provider=None, fallback_provider=None):
        seen["prompts"].append({"system": system, "prompt": prompt, "provider": provider})
        r = llm.RunResult(text="{}", model="fake", provider=provider or "gemini")
        if "kind" in schema["properties"]:
            return {"kind": "market", "searches": ["halpa kaurajuoma"]}, r      # the model gets the kind wrong
        return {"facts": [
            {"text": "Rainbow oat drink 1 l costs 1,19 € at S-kaupat.", "sources": [1]},
            {"text": "Lidl sells oat drink for 0,99 €.", "sources": [1]},       # names a competitor: dropped
            {"text": "K-Ruoka has Pirkka oat drink.", "sources": [2]},           # competitor source: invalid
        ]}, r

    monkeypatch.setattr(exa_client, "search_many", search_many)
    monkeypatch.setattr(llm, "complete_json", complete_json)
    return seen


def test_grocery_question_only_surfaces_s_group(fake_world):
    r = research.research("Where can I buy cheap oat milk?")
    assert r["kind"] == "grocery"                                            # code overrides the model's "market"
    assert all(q["domains"] == exa_client.S_GROUP_DOMAINS for q in fake_world["queries"])
    assert [s["url"] for s in r["sources"]] == ["https://www.s-kaupat.fi/tuote/kaurajuoma-1l/123"]
    assert [f["text"] for f in r["facts"]] == ["Rainbow oat drink 1 l costs 1,19 € at S-kaupat."]
    blob = str(research.public_view(r)).lower()
    for name in ("k-ruoka", "lidl", "pirkka", "k-market", "citymarket"):
        assert name not in blob
    assert all(p["provider"] == "gemini" for p in fake_world["prompts"])     # public zone model
    assert S_GROUP_RULE in fake_world["prompts"][-1]["system"]


def test_official_topics_stay_neutral(data_env, monkeypatch):
    import shutil
    shutil.rmtree(data_env["root"] / "cache" / "research", ignore_errors=True)
    queries = []
    monkeypatch.setattr(exa_client, "search_many", lambda q: queries.extend(q) or _results(
        ("Asumistuki", "https://www.kela.fi/asumistuki", "Tuloraja 1 844 €")))
    monkeypatch.setattr(llm, "complete_json", lambda s, p, schema, provider=None, fallback_provider=None: (
        {"kind": "official", "searches": ["Kela asumistuki"]} if "kind" in schema["properties"]
        else {"facts": [{"text": "Income limit 1 844 € for one adult.", "sources": [1]}]}, llm.RunResult(text="")))
    r = research.research("Kela housing allowance income limit for one adult")
    assert r["kind"] == "official" and queries[0]["domains"] == exa_client.OFFICIAL_DOMAINS
    assert r["facts"][0]["sources"] == [1]


def test_market_searches_exclude_competitor_grocery_sites(data_env, monkeypatch):
    import shutil
    shutil.rmtree(data_env["root"] / "cache" / "research", ignore_errors=True)
    queries = []
    monkeypatch.setattr(exa_client, "search_many", lambda q: queries.extend(q) or _results(
        ("Sähkövertailu", "https://www.sahkovertaaja.fi/", "Kiinteä 9,89 snt/kWh")))
    monkeypatch.setattr(llm, "complete_json", lambda s, p, schema, provider=None, fallback_provider=None: (
        {"kind": "market", "searches": ["sähkösopimus hinta"]} if "kind" in schema["properties"]
        else {"facts": [{"text": "Cheapest fixed price 9,89 snt/kWh.", "sources": [1]}]}, llm.RunResult(text="")))
    research.research("Typical electricity contract prices in Finland")
    assert queries[0]["domains"] is None and queries[0]["exclude"] == exa_client.COMPETITOR_GROCERY_DOMAINS


def test_s_group_rule_in_every_prompt():
    from datetime import date
    from kukkaro.butler import agent
    assert S_GROUP_RULE in system_prompt(date(2026, 9, 30)) and S_GROUP_RULE in agent.ANSWER_SYSTEM
    assert S_GROUP_RULE in research.FACTS_SYSTEM
    for name in ("S-market", "Prisma", "Alepa", "Sale", "S-kaupat"):
        assert name in S_GROUP_RULE


def test_competitor_mentions_and_grocery_detection():
    assert research.competitor_mentions("Try K-Citymarket or Lidl") == ["K-Citymarket", "Lidl"]
    assert research.competitor_mentions("S-market and Prisma") == []
    assert research.is_grocery("Where can I buy cheap oat milk?")
    assert not research.is_grocery("Can my landlord raise the rent?")


def test_chat_answer_naming_a_competitor_is_retried(data_env, monkeypatch):
    from kukkaro.coach import router
    texts = ["Lidl usually has cheap oat milk.", "Look at S-kaupat for oat milk."]
    calls = []

    def fake_run(system, history, message, tools, execute, provider=None):
        calls.append(provider)
        return llm.RunResult(text=texts[len(calls) - 1], model="fake", host="google", provider=provider)
    monkeypatch.setattr(llm, "run", fake_run)
    out = router.answer("C1", "Where can I buy cheap oat milk?", [])
    assert out["answer"] == "Look at S-kaupat for oat milk." and out["number_check"] == "retried"
    assert calls == ["gemma", "gemma"] and out["fallback"] is False

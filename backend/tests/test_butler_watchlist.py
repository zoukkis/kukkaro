"""Watchlist (butler/watchlist.py): deterministic diff, LLM only on change, raw task never reaches Exa. No network."""
from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient
from test_data_fixture import data_env  # noqa: F401  (pytest fixture)

from kukkaro.butler import agent, exa_client, watchlist
from kukkaro.coach import llm

TASK = "Am I overpaying for electricity? My rent is 611.56 and I live in 02150"
QUESTION = "Typical electricity prices in Finland (Espoo region, age 20–25)"
KELA = "https://www.kela.fi/asumistuki"
ENERGY = "https://www.energiavirasto.fi/sahkon-hinta"


def page(url, text, published="2026-10-01", highlight=None):
    return {"title": url.split("/")[-1], "url": url, "published_date": published, "image": None,
            "highlights": [highlight or text], "text": text}


@pytest.fixture
def world(data_env, monkeypatch):
    shutil.rmtree(data_env["root"] / "cache" / "watchlist", ignore_errors=True)
    state = {"pages": [page(KELA, "Kela text v1"), page(ENERGY, "Energy text v1")], "recent": [],
             "exa_calls": [], "llm_calls": []}

    monkeypatch.setattr(agent, "run", lambda cid, task, use_cache=True: {
        "answer": "x [1]", "research": {"question_sent": QUESTION, "kind": "market", "blocked": []}})

    def search(query, domains=None, num_results=5, search_type="auto", highlights_chars=1200, max_age_h=24,
               exclude=None, start_published_date=None, text_chars=0):
        state["exa_calls"].append({"query": query, "domains": domains, "max_age_h": max_age_h,
                                   "start_published_date": start_published_date, "text_chars": text_chars})
        return {"query": query, "domains": domains or [], "cached": False,
                "results": list(state["recent"] if start_published_date else state["pages"])}

    def complete_json(system, prompt, schema, provider=None, fallback_provider=None):
        state["llm_calls"].append({"prompt": prompt, "provider": provider})
        return {"summary": "Energy prices page was updated [1]. Something else [9]. Third [1]. Fourth [1]."}, \
            llm.RunResult(text="{}", model="fake", provider=provider or "gemini")

    monkeypatch.setattr(exa_client, "search", search)
    monkeypatch.setattr(llm, "complete_json", complete_json)
    return state


def test_unchanged_sources_no_llm_call(world):
    w = watchlist.watch("C1", TASK)
    assert w["question_sent"] == QUESTION and len(w["sources"]) == 2 and all(s["content_hash"] for s in w["sources"])
    r = watchlist.check(w["id"])
    assert r["changed"] is False and r["summary"] is None and r["sources"] == []
    assert r["new_sources"] == r["gone_sources"] == r["updated_sources"] == []
    assert world["llm_calls"] == []                                   # no change -> no model call
    checks = world["exa_calls"][1:]                                   # [0] was the snapshot at watch()
    assert all(c["max_age_h"] == 0 for c in world["exa_calls"])       # the Exa cache is bypassed
    assert [c["start_published_date"] is not None for c in checks] == [False, True]  # plus "published since"


def test_new_url_is_new_source_and_summary_cites_it(world):
    w = watchlist.watch("C1", TASK)
    world["recent"] = [page("https://www.energiavirasto.fi/uutinen", "New advice on electricity contracts", "2026-11-15")]
    r = watchlist.check(w["id"])
    assert r["changed"] is True and [s["url"] for s in r["new_sources"]] == ["https://www.energiavirasto.fi/uutinen"]
    assert r["sources"][0]["n"] == 1 and r["sources"][0]["status"] == "new" and r["sources"][0]["site"] == "energiavirasto.fi"
    recent_call = world["exa_calls"][-1]                              # "what's new" only on the watch's own sites
    assert recent_call["start_published_date"] and recent_call["domains"] == ["energiavirasto.fi", "kela.fi"]
    assert len(world["llm_calls"]) == 1 and world["llm_calls"][0]["provider"] == "gemini"
    assert "[9]" not in r["summary"] and "[1]" in r["summary"]       # citation guard: [9] is not a real source
    assert r["summary"].count(".") <= 3                               # at most 3 sentences
    again = watchlist.check(w["id"])                                  # the snapshot moved forward
    assert again["changed"] is False and again["gone_sources"] == []  # a "recent"-only page drops out quietly


def test_recent_page_off_topic_is_ignored(world):
    w = watchlist.watch("C1", TASK)
    world["recent"] = [page("https://www.espoo.fi/kuulutus", "Päätös meluilmoituksesta, paalutus, Tapiola", "2026-11-15")]
    r = watchlist.check(w["id"])                      # live test found exactly this: an off-topic official notice
    assert r["changed"] is False and r["new_sources"] == [] and world["llm_calls"] == []
    assert watchlist.topic_words(QUESTION) == {"electricity", "prices"}   # banded context is not a topic word


def test_same_url_new_hash_is_updated(world):
    w = watchlist.watch("C1", TASK)
    world["pages"] = [page(KELA, "Kela text v1"), page(ENERGY, "Energy text v2: prices fell")]
    r = watchlist.check(w["id"])
    assert r["changed"] is True and [s["url"] for s in r["updated_sources"]] == [ENERGY]
    assert r["new_sources"] == [] and r["gone_sources"] == []


def test_new_highlights_same_page_text_is_not_updated(world):
    w = watchlist.watch("C1", TASK)                     # live test: Exa regenerated highlights minutes apart
    world["pages"] = [page(KELA, "Kela text v1", highlight="other excerpt"), page(ENERGY, "Energy text v1", highlight="x")]
    r = watchlist.check(w["id"])
    assert r["changed"] is False and world["llm_calls"] == []
    assert all(c["text_chars"] > 0 for c in world["exa_calls"])   # page text is fetched for the fingerprint


def test_newer_published_date_is_updated_and_missing_url_is_gone(world):
    w = watchlist.watch("C1", TASK)
    world["pages"] = [page(ENERGY, "Energy text v1", "2026-11-14")]
    r = watchlist.check(w["id"])
    assert [s["url"] for s in r["updated_sources"]] == [ENERGY] and [s["url"] for s in r["gone_sources"]] == [KELA]


def test_rank_churn_at_the_bottom_is_ignored(world):
    top = [page(f"https://www.kela.fi/p{i}", f"text {i}") for i in range(1, 9)]
    world["pages"] = top
    w = watchlist.watch("C1", TASK)
    world["pages"] = top[:7] + [page("https://www.kela.fi/p9", "text 9")]      # rank 8 swapped: churn
    assert watchlist.check(w["id"])["changed"] is False
    world["pages"] = [page("https://www.kela.fi/p10", "text 10")] + top[1:7]    # rank 1 left, a new page at rank 1
    r = watchlist.check(w["id"])
    assert [s["url"] for s in r["new_sources"]] == ["https://www.kela.fi/p10"]
    assert [s["url"] for s in r["gone_sources"]] == ["https://www.kela.fi/p1"]  # p9 (rank 8) leaves quietly


def test_raw_task_never_reaches_exa_or_public_model(world):
    w = watchlist.watch("C1", TASK)
    world["pages"].append(page("https://www.vero.fi/x", "Tax text"))
    watchlist.check(w["id"])
    sent = [c["query"] for c in world["exa_calls"]] + [c["prompt"] for c in world["llm_calls"]]
    assert sent and all(TASK not in s and "611.56" not in s and "02150" not in s for s in sent)
    assert all(c["query"] == QUESTION for c in world["exa_calls"])


def test_exa_down_keeps_snapshot(world, monkeypatch):
    w = watchlist.watch("C1", TASK)
    monkeypatch.setattr(exa_client, "search", lambda *a, **k: {"results": [], "error": "down"})
    r = watchlist.check(w["id"])
    assert r["changed"] is False and r["error"] == "down" and r["gone_sources"] == []
    assert len(watchlist.list_watches("C1")[0]["sources"]) == 2


def test_blocked_question_cannot_be_watched(world, monkeypatch):
    monkeypatch.setattr(agent, "run", lambda cid, task, use_cache=True: {"research": {"question_sent": None, "blocked": ["id"]}})
    with pytest.raises(watchlist.CannotWatch):
        watchlist.watch("C1", "my id is C1")


def test_routes(world):
    from kukkaro.api.main import app
    with TestClient(app) as c:
        r = c.post("/api/customers/C1/watchlist", json={"task": TASK})
        assert r.status_code == 200
        wid = r.json()["id"]
        items = c.get("/api/customers/C1/watchlist").json()["items"]
        assert [i["id"] for i in items] == [wid] and items[0]["last_result"] is None
        res = c.post(f"/api/watchlist/{wid}/check").json()
        assert res["changed"] is False and set(res) >= {"new_sources", "gone_sources", "updated_sources", "summary", "sources"}
        assert c.get("/api/customers/C1/watchlist").json()["items"][0]["last_result"]["changed"] is False
        assert c.post("/api/customers/NOPE/watchlist", json={"task": TASK}).status_code == 404
        assert c.get("/api/customers/NOPE/watchlist").status_code == 404
        assert c.post("/api/watchlist/not-an-id/check").status_code == 404
        assert c.delete(f"/api/watchlist/{wid}").status_code == 200
        assert c.delete(f"/api/watchlist/{wid}").status_code == 404
        assert c.post(f"/api/watchlist/{wid}/check").status_code == 404


def test_check_all(world):
    a = watchlist.watch("C1", TASK)
    world["pages"] = world["pages"][:1]
    rows = watchlist.check_all()
    assert rows == [{"watch_id": a["id"], "changed": True, "new": 0, "gone": 1, "updated": 0, "error": None}]


def test_watchlist_posts_are_rate_limited(data_env, monkeypatch):
    """The real RATE_LIMITS rules (api/main.py): both watchlist POSTs call paid APIs, so they are limited per
    visitor, one bucket per rule (cycling watch ids doesn't reset it). Paid calls are stubbed here."""
    from kukkaro.api import main
    calls = {"watch": 0, "check": 0}

    def fake_watch(cid, task):
        calls["watch"] += 1
        return {"id": "a" * 12, "task": task}

    def fake_check(wid):
        calls["check"] += 1
        return {"changed": False}

    monkeypatch.setattr(watchlist, "watch", fake_watch)
    monkeypatch.setattr(watchlist, "check", fake_check)
    monkeypatch.setenv("RATE_LIMIT", "1")
    watch_limit = main.RATE_LIMITS[r"^/api/customers/[^/]+/watchlist$"][0]
    check_limit = main.RATE_LIMITS[r"^/api/watchlist/[^/]+/check$"][0]
    main._hits.clear()
    h = {"x-forwarded-for": "203.0.113.7"}
    with TestClient(main.app) as c:
        saves = [c.post("/api/customers/C1/watchlist", json={"task": TASK}, headers=h).status_code
                 for _ in range(watch_limit + 1)]
        checks = [c.post(f"/api/watchlist/{i:012x}/check", headers=h).status_code for i in range(check_limit + 1)]
        assert c.get("/api/customers/C1/watchlist", headers=h).status_code == 200          # GETs are never limited
        other = c.post("/api/watchlist/aaaaaaaaaaaa/check", headers={"x-forwarded-for": "203.0.113.8"}).status_code
    main._hits.clear()
    assert saves == [200] * watch_limit + [429]
    assert checks == [200] * check_limit + [429]                                           # different ids, one bucket
    assert other == 200                                                                    # per visitor
    assert calls == {"watch": watch_limit, "check": check_limit + 1}                       # 429s never reach Exa/LLM

"""Coach chat without network: number checks, tools, the fallback model, and the /api/chat route."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_data_fixture import data_env  # noqa: F401  (pytest fixture)

from kukkaro.coach import llm, numbers
from kukkaro.coach.tools import SPECS, executor

CALLS = [{"name": "safe_to_spend", "args": {},
          "result": {"today": "2026-09-30", "until_date": "2026-10-15", "amount_eur": 272.27, "this_week_eur": 127.05,
                     "per_day_eur": 18.15, "explanation_inputs": {"balance_eur": 1259.49, "days_until_salary": 15,
                                                                  "days_in_this_week": 7}}}]


@pytest.mark.parametrize("text, expected", [
    ("You can spend €127.05 this week.", ["127.05"]),
    ("Balance €1,259.49 and 1 259,49 € and 1259.49", ["1259.49", "1259.49", "1259.49"]),
    ("61,4 % of spending", ["61.4"]),
    ("Until 2026-10-15", ["2026", "10", "15"]),
])
def test_numbers_in_text(text, expected):
    assert [format(d.normalize(), "f") for d in numbers.numbers_in_text(text)] == expected


def test_unverified_numbers_flags_only_invented_ones():
    ok = "You can safely spend €127.05 this week (€18.15 a day) until 2026-10-15, out of €272.27."
    assert numbers.unverified_numbers(ok, CALLS) == []
    bad = "You can safely spend €127.05 this week, about €550 a month."
    assert numbers.unverified_numbers(bad, CALLS) == ["550"]


def test_figures_only_used_numbers_and_counts_need_a_noun():
    f = numbers.figures("Safe this week: €127.05, that's €18.15 a day for the next 7 days. In 3 weeks...", CALLS)
    assert [(x["label"], x["value"], x["unit"]) for x in f] == [
        ("this week", 127.05, "EUR"), ("per day", 18.15, "EUR"), ("days in this week", 7, "count")]
    assert f[0]["source"] == "2026-09-30 to 2026-10-15"


def test_tool_specs_never_take_a_customer_id():
    for s in SPECS:
        assert "customer_id" not in s.parameters.get("properties", {})


def test_executor_binds_customer_and_returns_errors(data_env):
    ex = executor("C1")
    assert ex("category_spend", {"category": "taxi", "start": "2026-06-01", "end": "2026-09-30"})["spent_eur"] == 100.0
    assert "Unknown category" in ex("category_spend", {"category": "coffee", "start": "2026-09-01", "end": "2026-09-30"})["error"]
    assert ex("category_spend", {"category": "taxi"})["error"].startswith("Missing argument")
    assert ex("nope", {})["error"].startswith("Unknown tool")


def test_fallback_model_takes_over(monkeypatch):
    seen = []

    def fake(cfg, system, history, message, tools, execute, deadline, result):
        seen.append(cfg["model"])
        if cfg["model"] == "gemini-4-hydrogen":
            raise TimeoutError("slow")
        result.text = "ok"

    monkeypatch.setenv("GEMINI_MODEL", "gemini-4-hydrogen")
    monkeypatch.setattr(llm, "_run_google", fake)
    r = llm.run("sys", [], "hi", SPECS, lambda n, a: {}, "gemini")
    assert seen == ["gemini-4-hydrogen", "gemini-3.8-flash"]
    assert (r.text, r.model, r.error) == ("ok", "gemini-3.8-flash", None)


def test_all_models_fail_gives_friendly_text(monkeypatch):
    def fake(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(llm, "_run_google", fake)
    r = llm.run("sys", [], "hi", SPECS, lambda n, a: {}, "gemini")
    assert r.text == llm.FALLBACK_TEXT and "down" in r.error


def test_gemma_stage1_uses_google_host(monkeypatch):
    monkeypatch.delenv("GEMMA_BASE_URL", raising=False)
    monkeypatch.setenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")
    assert llm.provider_config("gemma") == {"provider": "gemma", "model": "gemma-4-26b-a4b-it", "host": "google"}
    monkeypatch.setenv("GEMMA_BASE_URL", "https://example.invalid/v1")
    assert llm.provider_config("gemma")["host"] == "verda"


@pytest.fixture(scope="module")
def client(data_env):
    from kukkaro.api.main import app
    with TestClient(app) as c:
        yield c


def test_chat_route(client, monkeypatch):
    captured = {}

    def fake_run(system, history, message, tools, execute, provider=None):
        captured.update(system=system, history=history, provider=provider)
        out = execute("safe_to_spend", {})
        r = llm.RunResult(text=f"You can safely spend €{out['this_week_eur']} this week.", model="fake-model", host="google",
                          provider=provider or "gemini")
        r.tool_calls = [{"name": "safe_to_spend", "args": {}, "result": out}]
        return r

    monkeypatch.setattr(llm, "run", fake_run)
    body = {"customer_id": "C1", "message": "What can I safely spend this week?",
            "history": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Hello!"}], "provider": "gemma"}
    r = client.post("/api/chat", json=body)
    assert r.status_code == 200
    j = r.json()
    assert j["answer"] == "You can safely spend €2836.4 this week."
    assert j["tool_calls"] == [{"name": "safe_to_spend", "args": {}}]
    assert j["figures"][0]["value"] == 2836.4 and j["unverified_numbers"] == []
    assert (j["model"], j["host"], j["provider"]) == ("fake-model", "google", "gemma")
    assert "_tool_results" not in j
    assert "Today is 2026-09-30" in captured["system"] and captured["history"][1]["role"] == "assistant"


@pytest.mark.parametrize("body, status", [
    ({"customer_id": "NOPE", "message": "hi"}, 404),
    ({"customer_id": "C1", "message": ""}, 422),
    ({"customer_id": "C1", "message": "hi", "provider": "openai"}, 422),
])
def test_chat_route_errors(client, monkeypatch, body, status):
    monkeypatch.setattr(llm, "run", lambda *a, **k: pytest.fail("LLM must not be called"))
    assert client.post("/api/chat", json=body).status_code == status

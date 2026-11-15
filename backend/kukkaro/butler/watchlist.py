"""Watchlist: Kukkaro re-checks a saved Butler question with Exa and speaks up only when the sources change.

Zones (root AGENTS.md §4):
- `watch(customer_id, task)` runs the normal Butler flow once (`agent.run`: trusted zone, privacy gateway,
  public research). It stores the question that already passed the gateway (`question_sent`), never sends the
  raw task anywhere, and takes a source snapshot by searching Exa for that question.
- `check(watch_id)` is PUBLIC ZONE ONLY: it reads just `question_sent`, the topic kind and the stored source
  snapshot (`_public_check`), never the task or the customer's data. Two live Exa searches (cache bypassed):
  the question again, and the question restricted to pages published since the last check.
- The diff is computed in code: new, gone and updated sources (same URL, different content hash or a newer
  published date). Only when something changed does Gemini write at most 3 sentences on what changed, citing
  the changed sources as [n]; citations that point to no real changed source are removed in code.

Storage: one JSON file per watch in data/cache/watchlist/ (gitignored). CLI for a nightly batch job:
    python -m kukkaro.butler.watchlist --check-all
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from kukkaro.butler import exa_client, research
from kukkaro.coach import llm
from kukkaro.coach.prompts import S_GROUP_RULE

PROVIDER = "gemini"          # public zone: sees only the anonymised question and web pages
SNAPSHOT_RESULTS = 8          # sources kept per watch
CORE_RANK = 5                 # a ranked page must enter the top 5 to count as new (hysteresis, see diff())
RECENT_RESULTS = 5            # "published since the last check" search
PAGE_TEXT_CHARS = 4000        # page text fetched for the fingerprint (content_hash)
MAX_SUMMARY_SENTENCES = 3
_ID = re.compile(r"[0-9a-f]{12}")
_CITE = re.compile(r"\[(\d+)\]")


class WatchNotFound(LookupError):
    pass


class CannotWatch(ValueError):
    """The Butler sent nothing to the web for this task (blocked by the privacy gateway or no question)."""


# ---------- storage ----------

def _dir():
    from kukkaro.data.settings import data_dir
    d = data_dir() / "cache" / "watchlist"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(watch_id: str):
    if not _ID.fullmatch(watch_id or ""):
        raise WatchNotFound(watch_id)
    return _dir() / f"{watch_id}.json"


def _load(watch_id: str) -> dict[str, Any]:
    p = _path(watch_id)
    if not p.exists():
        raise WatchNotFound(watch_id)
    return json.loads(p.read_text(encoding="utf-8"))


def _save(w: dict[str, Any]) -> None:
    _path(w["id"]).write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------- public zone: search + diff ----------

def content_hash(page_text: str) -> str:
    """Fingerprint of a page: its text as Exa crawled it, whitespace-normalised. Not the highlights: Exa
    regenerates those, and in a live test the same pages got different highlights minutes apart."""
    text = " ".join((page_text or "").split()).lower()
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _domains(kind: str | None, question: str) -> tuple[list[str] | None, list[str] | None, bool]:
    """The same domain rules as the research worker: S-Group only for groceries, official sites for official topics."""
    grocery = kind == "grocery" or research.is_grocery(question)
    domains = exa_client.S_GROUP_DOMAINS if grocery else exa_client.OFFICIAL_DOMAINS if kind == "official" else None
    return domains, (None if domains else exa_client.COMPETITOR_GROCERY_DOMAINS), grocery


def _sources(res: dict, grocery: bool, via: str) -> list[dict[str, Any]]:
    out = []
    for r in res.get("results", []):
        if not r.get("highlights") or (grocery and research._is_competitor_url(r["url"])):
            continue
        out.append({"url": r["url"], "title": r.get("title") or r["url"], "published_date": r.get("published_date"),
                    "content_hash": content_hash(r.get("text") or " ".join(r["highlights"])), "via": via,
                    "rank": len(out) + 1 if via == "search" else None,
                    "text": " … ".join(r["highlights"])[:research.TEXT_CHARS_PER_SOURCE]})
    return out


def _snapshot(question: str, kind: str | None, since: str | None = None) -> tuple[list[dict], list[str]]:
    """Live Exa (no cache): the question, plus pages published since `since`. Returns (sources, errors)."""
    domains, exclude, grocery = _domains(kind, question)
    main = exa_client.search(question, domains, num_results=SNAPSHOT_RESULTS, max_age_h=0, exclude=exclude,
                              text_chars=PAGE_TEXT_CHARS)
    found, errors = _sources(main, grocery, "search"), [main["error"]] if main.get("error") else []
    if since:
        # "What's new" only on the sites this watch already relies on (the ranked results): on the open web
        # something new about electricity appears every day (live test: EV-charging and energy blogs).
        sites = sorted({_site(s["url"]) for s in found}) or domains
        recent = exa_client.search(question, sites, num_results=RECENT_RESULTS, max_age_h=0, exclude=exclude,
                                   start_published_date=since[:10], text_chars=PAGE_TEXT_CHARS)  # by day: Exa dates are often day-precision
        if recent.get("error"):
            errors.append(recent["error"])
        seen = {s["url"] for s in found}
        found += [s for s in _sources(recent, grocery, "recent") if s["url"] not in seen and relevant(s, question)]
    return found, errors


# Words too general to show a page is about the watched topic (the banded context in brackets is dropped too).
_STOP = {"about", "after", "also", "does", "from", "have", "into", "more", "much", "should", "that", "their", "there",
         "these", "this", "what", "when", "where", "which", "with", "would", "your", "finland", "finnish", "suomi",
         "current", "currently", "typical", "general", "possible", "possibly", "still", "rules", "region", "people"}


def topic_words(question: str) -> set[str]:
    """Content words of the anonymised question, without its banded context ("(Espoo region, age 20–25)")."""
    q = re.sub(r"\([^)]*\)", " ", question or "").lower()
    return {w for w in re.findall(r"[a-zåäö]{4,}", q) if w not in _STOP}


def relevant(source: dict, question: str) -> bool:
    """A page that only the "published since" search found counts only if it mentions the topic. Without
    this, the date filter brings in anything new on an official site (live test: Espoo noise notices for
    a Kela question)."""
    words = topic_words(question)
    text = f"{source.get('title', '')} {source.get('text', '')}".lower()
    return not words or any(w in text for w in words)


def _newer(new: str | None, old: str | None) -> bool:
    return bool(new and old and new[:10] > old[:10])


def _core(s: dict) -> bool:
    """In the top CORE_RANK of the ranked search (old snapshots without a rank count as core)."""
    return s.get("via") == "search" and (s.get("rank") is None or s["rank"] <= CORE_RANK)


def diff(old: list[dict], current: list[dict]) -> dict[str, list[dict]]:
    """Deterministic: new URLs, gone URLs, and same URL with a different content hash or a newer published date.
    Hysteresis against Exa's ranking churn (live: pages at ranks 6-8 swap between calls minutes apart): a ranked
    page is new only if it enters the top CORE_RANK, and gone only if it was in the top CORE_RANK and has left all
    SNAPSHOT_RESULTS. A page that only the "published since" search found is new, and drops out silently later."""
    before = {s["url"]: s for s in old}
    now = {s["url"]: s for s in current}
    new = [s for u, s in now.items() if u not in before and (s.get("via") == "recent" or _core(s))]
    gone = [s for u, s in before.items() if u not in now and _core(s)]
    updated = [s for u, s in now.items() if u in before and
               (s["content_hash"] != before[u]["content_hash"] or _newer(s["published_date"], before[u]["published_date"]))]
    return {"new_sources": new, "gone_sources": gone, "updated_sources": updated}


SUMMARY_SYSTEM = f"""You tell a person what changed in the web sources about a question they are watching. \
You get the question, the numbered NEW or UPDATED sources with their text, and the titles of sources that are gone. \
Write at most 3 short sentences on what changed, using ONLY the numbered sources, and put [n] after each claim. \
Copy numbers exactly as the sources give them; do not calculate. Never say the person is eligible for anything; \
say they may want to check. You know nothing about the person.
{S_GROUP_RULE}"""
SUMMARY_SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}


def _site(url: str) -> str:
    return research._domain(url)


def _summary(question: str, numbered: list[dict], gone: list[dict]) -> tuple[str | None, str | None]:
    """Gemini, max 3 sentences, only valid [n] citations kept. Returns (summary or None, error)."""
    today = date.today().isoformat()
    src = "\n\n".join(f"[{s['n']}] ({s['status']}) {s['title']} ({s['url']}, published {s['published_date'] or 'unknown'})\n"
                      f"{s.get('text') or ''}" for s in numbered)
    gone_txt = "\n".join(f"- {g['title']} ({_site(g['url'])})" for g in gone) or "(none)"
    out, run = llm.complete_json(SUMMARY_SYSTEM, f"Today is {today}.\nQuestion: {question}\n\nChanged sources:\n{src}\n\n"
                                 f"Sources no longer found:\n{gone_txt}", SUMMARY_SCHEMA, PROVIDER)
    text = str((out or {}).get("summary") or "")
    valid = {s["n"] for s in numbered}
    text = _CITE.sub(lambda m: m.group(0) if int(m.group(1)) in valid else "", text)   # citation guard
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", llm.plain(text)) if x.strip()][:MAX_SUMMARY_SENTENCES]
    text = " ".join(sentences)
    from kukkaro.butler.agent import _soften_eligibility
    text = _soften_eligibility(text)
    if numbered and not _CITE.search(text):
        return None, run.error or "summary had no valid citations"
    return text or None, run.error


def _public_check(question: str, kind: str | None, old: list[dict], since: str | None) -> dict[str, Any]:
    """Public zone only: the anonymised question, the topic kind and the stored snapshot. Nothing else."""
    current, errors = _snapshot(question, kind, since)
    if errors and not current:  # Exa failed: report it and keep the old snapshot instead of calling it all "gone"
        return {"changed": False, "error": errors[0], "current": None, "new_sources": [], "gone_sources": [],
                "updated_sources": [], "summary": None, "sources": []}
    d = diff(old, current)
    numbered = [{**s, "n": i + 1, "status": status, "site": _site(s["url"])}
                for i, (s, status) in enumerate([(s, "new") for s in d["new_sources"]] +
                                                [(s, "updated") for s in d["updated_sources"]])]
    changed = any(d.values())
    summary, err = _summary(question, numbered, d["gone_sources"]) if changed else (None, None)
    pub = lambda s: {k: s.get(k) for k in ("url", "title", "published_date", "content_hash")} | {"site": _site(s["url"])}
    return {"changed": changed, "new_sources": [pub(s) for s in d["new_sources"]],
            "gone_sources": [pub(s) for s in d["gone_sources"]], "updated_sources": [pub(s) for s in d["updated_sources"]],
            "summary": summary, "sources": [pub(s) | {"n": s["n"], "status": s["status"]} for s in numbered],
            "current": current, "error": err or (errors[0] if errors else None)}


# ---------- API ----------

def _stored(s: dict) -> dict:
    return {k: s.get(k) for k in ("url", "title", "published_date", "content_hash", "via", "rank")}


def public(w: dict[str, Any]) -> dict[str, Any]:
    """What the API returns for a watch (the stored snapshot without page text)."""
    return {k: w.get(k) for k in ("id", "customer_id", "task", "question_sent", "kind", "created_at", "last_checked_at",
                                  "last_result")} | {"sources": [_stored(s) | {"site": _site(s["url"])} for s in w["sources"]]}


def watch(customer_id: str, task: str) -> dict[str, Any]:
    """Save a Butler question. Runs the normal Butler flow once (cached if the user just asked it)."""
    from kukkaro.butler import agent
    from kukkaro.data import metrics
    metrics.customer_profile(customer_id)       # unknown customer -> UnknownCustomer (404) before any web call
    out = agent.run(customer_id, task)
    r = out.get("research") or {}
    question = r.get("question_sent")
    if not question:
        raise CannotWatch("This question can't be watched: nothing was sent to the web for it.")
    kind = r.get("kind")
    current, errors = _snapshot(question, kind)
    if errors and not current:
        raise CannotWatch("Couldn't reach the web search right now. Please try again in a moment.")
    now = _now()
    w = {"id": uuid.uuid4().hex[:12], "customer_id": customer_id, "task": task, "question_sent": question, "kind": kind,
         "sources": [_stored(s) for s in current], "created_at": now, "last_checked_at": now, "last_result": None}
    _save(w)
    return public(w)


def list_watches(customer_id: str) -> list[dict[str, Any]]:
    ws = [json.loads(p.read_text(encoding="utf-8")) for p in _dir().glob("*.json")]
    return [public(w) for w in sorted((w for w in ws if w["customer_id"] == customer_id), key=lambda w: w["created_at"],
                                      reverse=True)]


def check(watch_id: str) -> dict[str, Any]:
    w = _load(watch_id)
    res = _public_check(w["question_sent"], w.get("kind"), w["sources"], w.get("last_checked_at"))
    current = res.pop("current")
    checked = _now()
    if current is not None:              # Exa answered: move the snapshot forward
        w["sources"] = [_stored(s) for s in current]
        w["last_checked_at"] = checked
    result = {**res, "checked_at": checked}
    w["last_result"] = {k: result[k] for k in ("changed", "summary", "sources", "new_sources", "gone_sources",
                                               "updated_sources", "checked_at", "error")}
    _save(w)
    return {"watch_id": watch_id, "question_sent": w["question_sent"], "last_checked_at": w["last_checked_at"], **result}


def delete(watch_id: str) -> None:
    p = _path(watch_id)
    if not p.exists():
        raise WatchNotFound(watch_id)
    p.unlink()


def check_all() -> list[dict[str, Any]]:
    out = []
    for p in sorted(_dir().glob("*.json")):
        wid = p.stem
        try:
            r = check(wid)
            out.append({"watch_id": wid, "changed": r["changed"], "new": len(r["new_sources"]),
                        "gone": len(r["gone_sources"]), "updated": len(r["updated_sources"]), "error": r.get("error")})
        except Exception as e:  # one broken watch must not stop the nightly run
            out.append({"watch_id": wid, "changed": False, "error": f"{type(e).__name__}: {e}"[:200]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Kukkaro watchlist: re-check saved Butler questions with Exa.")
    ap.add_argument("--check-all", action="store_true", help="check every saved watch (nightly batch job)")
    args = ap.parse_args()
    if not args.check_all:
        ap.print_help()
        return
    rows = check_all()
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    print(f"checked {len(rows)} watch(es), {sum(r['changed'] for r in rows)} changed")


if __name__ == "__main__":
    main()

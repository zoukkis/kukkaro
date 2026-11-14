"""Collect app reviews of similar products for user research (NOT part of the app).

Run on your own laptop (needs internet):
    pip install google-play-scraper requests
    python scripts/research/scrape_reviews.py

Output: data/raw/research/reviews.csv  (gitignored; never commit raw reviews)
Only stores app, source, rating, date, language, version and text. No usernames (GDPR).
"""
from __future__ import annotations

import csv
import time
from pathlib import Path

import requests
from google_play_scraper import Sort, reviews

OUT = Path(__file__).resolve().parents[2] / "data" / "raw" / "research" / "reviews.csv"

# (name, google play package, apple app id, country, language)
# IDs marked TODO are unverified: look them up in the store URL and fill in, or leave None to skip.
APPS = [
    ("S-mobiili", "fi.spankki", "740514933", "fi", "fi"),
    ("Revolut", "com.revolut.revolut", "932493382", "gb", "en"),
    ("Cleo", None, "1447274646", "us", "en"),          # TODO: Google Play package
    ("OP-mobiili", None, None, "fi", "fi"),            # TODO: both IDs
    ("Nordea Mobile FI", None, None, "fi", "fi"),      # TODO: both IDs
    ("Emma", None, None, "gb", "en"),                  # TODO: both IDs
]
PER_APP = 400  # Google Play reviews per app


def google_play(name: str, package: str, country: str, lang: str):
    rows, token = [], None
    while len(rows) < PER_APP:
        batch, token = reviews(package, lang=lang, country=country, sort=Sort.NEWEST,
                               count=min(200, PER_APP - len(rows)), continuation_token=token)
        if not batch:
            break
        for r in batch:
            rows.append({"app": name, "source": "google_play", "rating": r["score"],
                         "date": r["at"].date().isoformat(), "language": lang,
                         "version": r.get("reviewCreatedVersion") or "", "text": r["content"] or ""})
        if token is None:
            break
        time.sleep(1)
    return rows


def app_store(name: str, app_id: str, country: str, lang: str):
    rows = []
    for page in range(1, 11):  # Apple serves up to 10 pages x 50 reviews
        url = f"https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
        resp = requests.get(url, timeout=20)
        if resp.status_code != 200:
            break
        entries = resp.json().get("feed", {}).get("entry", [])
        entries = [e for e in entries if "im:rating" in e]  # skip the app-info entry
        if not entries:
            break
        for e in entries:
            rows.append({"app": name, "source": "app_store", "rating": int(e["im:rating"]["label"]),
                         "date": e.get("updated", {}).get("label", "")[:10], "language": lang,
                         "version": e.get("im:version", {}).get("label", ""),
                         "text": (e["title"]["label"] + ". " + e["content"]["label"]).strip()})
        time.sleep(1)
    return rows


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for name, package, app_id, country, lang in APPS:
        if package:
            try:
                got = google_play(name, package, country, lang)
                print(f"{name}: {len(got)} Google Play reviews")
                all_rows += got
            except Exception as exc:  # keep going if one app fails
                print(f"{name}: Google Play failed ({exc})")
        if app_id:
            try:
                got = app_store(name, app_id, country, lang)
                print(f"{name}: {len(got)} App Store reviews")
                all_rows += got
            except Exception as exc:
                print(f"{name}: App Store failed ({exc})")
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["app", "source", "rating", "date", "language", "version", "text"])
        w.writeheader()
        w.writerows(all_rows)
    print(f"Saved {len(all_rows)} reviews to {OUT}")


if __name__ == "__main__":
    main()

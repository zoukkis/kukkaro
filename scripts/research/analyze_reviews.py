"""Classify scraped reviews into themes with Gemini and print a summary (NOT part of the app).

    pip install google-genai python-dotenv
    python scripts/research/analyze_reviews.py

Reads data/raw/research/reviews.csv, writes data/raw/research/themes.csv and prints counts per
app and theme. Copy only the SUMMARY (no raw review text) into docs/USER_RESEARCH.md.
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from google import genai

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
IN = ROOT / "data" / "raw" / "research" / "reviews.csv"
OUT = ROOT / "data" / "raw" / "research" / "themes.csv"

THEMES = [
    "generic_or_useless_advice", "wrong_or_missing_categories", "no_spending_insight",
    "wants_budgeting_tools", "wants_product_or_receipt_level_detail", "likes_spending_overview",
    "likes_ai_chat", "ai_chat_unhelpful_or_wrong", "privacy_or_trust_worry", "fees_or_upsell",
    "too_many_notifications", "hard_to_navigate", "bugs_crashes_login", "other",
]
PROMPT = (
    "Classify each app review into 1-3 themes from this list: " + ", ".join(THEMES) + ". "
    "Reviews may be Finnish or English. Return JSON: a list of objects {\"i\": index, \"themes\": [...], "
    "\"sentiment\": \"neg\"|\"neu\"|\"pos\"}. Reviews:\n"
)


def main() -> None:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = os.environ.get("GEMINI_MODEL", "gemini-4-hydrogen")
    rows = list(csv.DictReader(IN.open(encoding="utf-8")))
    results = []
    for start in range(0, len(rows), 40):
        batch = rows[start:start + 40]
        text = "\n".join(f"{i}: [{r['rating']}*] {r['text'][:600]}" for i, r in enumerate(batch))
        resp = client.models.generate_content(model=model, contents=PROMPT + text,
                                              config={"response_mime_type": "application/json"})
        for item in json.loads(resp.text):
            r = batch[item["i"]]
            results.append({"app": r["app"], "rating": r["rating"], "sentiment": item.get("sentiment", ""),
                            "themes": "|".join(item.get("themes", []))})
        print(f"classified {min(start + 40, len(rows))}/{len(rows)}")
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["app", "rating", "sentiment", "themes"])
        w.writeheader()
        w.writerows(results)
    for app in sorted({r["app"] for r in results}):
        c = Counter(t for r in results if r["app"] == app for t in r["themes"].split("|") if t)
        n = sum(1 for r in results if r["app"] == app)
        print(f"\n{app} ({n} reviews)")
        for theme, k in c.most_common(8):
            print(f"  {theme:40s} {k:4d}  ({k / n:.0%})")


if __name__ == "__main__":
    main()

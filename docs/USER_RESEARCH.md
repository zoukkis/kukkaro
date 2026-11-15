# User research: what people like and hate in similar products

First pass, 14 Nov 2026 13:30, from public review pages and review summaries (sources at the end).
Only summaries here, never raw reviews or usernames. (A review scraper was drafted and removed unused on
15 Nov: app store terms restrict scraping, so this file relies on public review pages only.)

## Findings

### S-mobiili (the app Kukkaro would live in)
- Rated about 4.4/5 on the Finnish App Store (~32,000 ratings). Visible reviews ask for basics:
  Apple Pay, working with a VPN on, an English version.
- unitQ's review tracker scores it 39/100 ("poor", 30-day average to 9 Nov 2026). Top complaint
  themes: crashes, fails to launch, can't log in, **difficult to navigate UI**. Most reports are from Android.
- It already has a receipt archive and a "Bonus and Purchases" view that groups purchases into product
  groups and compares basket prices, **but no budgeting or coaching tool is mentioned**.

### Revolut AIR (closest AI-assistant competitor, launched Apr 2026)
- Strengths: conversational drill-down into spending, transaction search, acts on cards and travel
  after confirmation.
- Weaknesses found by a detailed review: **savings advice is generic and doesn't name specific
  spending drivers**; answers depend on correct categorisation; misses some transactions; verbose
  by default; not faster than normal app flows. No web search mentioned.

### Cleo (AI money chatbot, US/UK)
- Users like that the chatbot makes budgeting feel engaging and less intimidating.
- Complaints cluster on **money taken before value is given**: subscriptions, fees, cash-advance
  eligibility, hard cancellation, slow support.

## What it means for Kukkaro

| What users hate or miss | How Kukkaro answers it | Where |
|---|---|---|
| Generic savings advice (Revolut AIR) | Receipt-level drivers + concrete what-if in euros | RECEIPTS, COACH |
| Answers depend on (wrong) categories | Receipts split a trip by item; "How I got this" shows the source | RECEIPTS, WEB |
| Hard-to-navigate UI (S-mobiili) | One chat box + 3 baskets, no menus to learn; big tap targets | WEB |
| Verbose AI answers (Revolut AIR) | Max ~120 words + one next step (already in the coach prompt) | COACH |
| No coaching in S-mobiili today | Kukkaro *is* that missing layer, on data S-mobiili already has | Pitch |
| Fees and upsell destroy trust (Cleo) | Free inside the bank app, never sells products or loans | Pitch, COACH rules |
| Engaging AI personality is liked (Cleo) | Friendly coach tone, but numbers always from data | COACH |
| No web search in bank assistants (Revolut AIR) | Butler brings current official info with sources (Exa) | BUTLER |

## Sources
- S-mobiili on the Finnish App Store: https://apps.apple.com/fi/app/s-mobiili/id740514933
- unitQ scorecard for S-mobiili: https://www.unitq.com/unitq-scorecards/smobiili
- AIR by Revolut UX review: https://craftinnovations.global/revolut-air-ux-analysis/
- Cleo reviews: https://www.thepennyhoarder.com/budgeting/cleo-app-review/ and https://joingerald.com/blog/cleo-ai-review

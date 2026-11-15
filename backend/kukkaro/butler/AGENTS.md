# Workstream BUTLER — `backend/kukkaro/butler/`

Read the root `AGENTS.md` first. You own **only** this folder plus `backend/tests/test_butler_*.py`.
This feature is the **Exa** submission ("The Internet Butler"), so it must work on judges' own live queries.

## Exa's judging (20% each)
Use of Exa for info a model can't know from training data · usefulness to a specific group ·
clarity of sources · originality · works on live queries, including the judges' own.

## Positioning (use in pitch and README)
Revolut is an Exa customer: its Wealth & Trading AI team benchmarked search providers for agentic
workflows and picked Exa. Revolut's in-app assistant AIR (launched Apr 2026) covers spending,
search and card actions, but reviewers found its savings advice generic. Kukkaro's angle:
specific drivers from receipts, plus a Butler that brings in current official information with sources.

## Deliverables (in order)
1. **`exa_client.py`**: thin wrapper over the Exa Python SDK (`EXA_API_KEY`). Use Search plus
   Contents (highlights or summaries). Prefer official domains for Finnish topics (e.g. `kela.fi`,
   `vero.fi`, `kkv.fi`, `suomi.fi`, `finlex.fi`) via domain filters, and recent dates for prices.
2. **`agent.py`**: `run(customer_id, task) -> {answer, sources[{title,url}], next_steps[]}`
   - Step 1: get the user's context from DATA tools (age band, postal code, recurring payments such as
     rent, electricity, phone and subscriptions). Use only numbers from tools.
   - Step 2: plan 1–4 Exa searches for the task.
   - Step 3: answer only from the retrieved pages. Every claim cites a source URL. If sources
     disagree or are missing, say so.
   - Step 4: draft concrete next steps (application checklist, message to landlord, switch plan).
     The user approves; the agent never sends or submits anything.
3. **Three demo tasks that must work reliably:**
   - "Am I possibly eligible for Kela housing allowance?" (uses rent + income pattern + age)
   - "My rent went up. Is that allowed, and what can I do?" (general rights question: the data has
     no real rent rises, see docs/DATA_PROFILE.md, so answer from sources, not from the user's data)
   - "Am I overpaying for electricity?" (the data has no subscriptions and utilities have no merchant;
     use `recurring_payments()` utilities `change_pct`, e.g. demo customer CUST02979: Sep 144.73 €
     vs typical 65.70 €, +120%)
   It must also survive free-form questions from judges. Test 10 unseen phrasings.
4. **`router.py`**: `POST /api/butler` per root AGENTS.md §5.4. COACH mounts it in `api/main.py`.

## Privacy design (decided 14 Nov; root AGENTS.md §4)
- `research.py` is the **public-zone research worker**: `research(question)` gets ONE anonymised
  question (never customer data), plans Exa searches, and Gemini writes facts only from the pages
  (`{facts[{text, sources[n]}], sources[{n,title,url}]}`). Cached per question in `data/cache/research/`.
  The coach calls it through `research_web`; `/api/butler` calls it through the same gateway.
- `agent.run()`: the task is checked by `coach/privacy.py` and sent with banded context only
  ("Espoo region, age 20–25"); Gemma (Gemini as backup) writes the answer with the user's figures.
- S-Group rule: grocery/product questions search `exa_client.S_GROUP_DOMAINS` only; competitor
  grocery sites are excluded from other searches and dropped from results; facts naming competitor
  chains are dropped. Official topics keep `OFFICIAL_DOMAINS`.

## Watchlist (`watchlist.py`, 15 Nov)
- `watch(customer_id, task)` runs `agent.run` once (cached if just asked) and stores only the gateway's
  `question_sent`, the topic kind and a source snapshot `{url, title, published_date, content_hash}` in
  `data/cache/watchlist/` (gitignored). A task the gateway blocked can't be watched (422).
- `check(watch_id)` is public zone only (`_public_check` gets the question, kind and snapshot, nothing else):
  two live Exa searches with the cache bypassed (`max_age_h=0`): the question, and the question with
  `start_published_date` = the last check's day, limited to the sites already in the ranked results. A page
  only that second search found must also mention a topic word of the question (`relevant()`). Live, without
  these two rules the date filter brought in Espoo noise notices (Kela question) and EV-charging blogs
  (electricity question).
- Fingerprint = hash of the page **text** (`text_chars`), not the highlights: Exa regenerated highlights for
  unchanged pages minutes apart, which made every check report false "updated" sources.
- Diff in code: new, gone (pages found only by the date search drop out quietly), updated (same URL, new hash
  or newer published date). Only if changed: Gemini, at most 3 sentences, `[n]` citations to the changed
  sources; invalid citations are removed and eligibility claims softened in code. Exa down -> error, snapshot kept.
- Routes: `POST/GET /api/customers/{id}/watchlist`, `POST /api/watchlist/{id}/check`, `DELETE /api/watchlist/{id}`.
  Nightly: `python -m kukkaro.butler.watchlist --check-all`.

## Rules
- Never claim someone **is** eligible. Say "you may be eligible; here's how to check", with the official link.
- Use the LLM interface from `kukkaro.coach.llm` (don't add another SDK). Ask COACH if you need changes.
- Cache Exa responses per query on disk (`data/cache/exa/`, gitignored) so the recorded demo is
  repeatable and credits last. Live queries still go live.
- No scraping beyond the Exa API. No form submissions. No storing personal data.
- Attend Exa's workshop (Sat 16:30–17:00, Loft, 4th floor) or ask Exa engineers at their booth if stuck.

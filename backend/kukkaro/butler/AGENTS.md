# Workstream BUTLER — `backend/kukkaro/butler/`

Read the root `AGENTS.md` first. You own **only** this folder plus `backend/tests/test_butler_*.py`.
This feature is the **Exa** submission ("The Internet Butler"), so it must work on judges' own live queries.

## Exa's judging (20% each)
Use of Exa for info a model can't know from training data · usefulness to a specific group ·
clarity of sources · originality · works on live queries, including the judges' own.

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
   - "My rent went up. Is that allowed, and what can I do?"
   - "Am I overpaying for electricity / phone / subscriptions?" (uses recurring payments)
   It must also survive free-form questions from judges. Test 10 unseen phrasings.
4. **`router.py`**: `POST /api/butler` per root AGENTS.md §5.4. COACH mounts it in `api/main.py`.

## Rules
- Never claim someone **is** eligible. Say "you may be eligible; here's how to check", with the official link.
- Use the LLM interface from `kukkaro.coach.llm` (don't add another SDK). Ask COACH if you need changes.
- Cache Exa responses per query on disk (`data/cache/exa/`, gitignored) so the recorded demo is
  repeatable and credits last. Live queries still go live.
- No scraping beyond the Exa API. No form submissions. No storing personal data.
- Attend Exa's workshop (Sat 16:30–17:00, Loft, 4th floor) or ask Exa engineers at their booth if stuck.

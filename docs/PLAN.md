# Kukkaro: build plan (Junction 2026)

Hard deadline: **final submission Sun 15 Nov 10:00**. The form closes automatically; no late submissions.
All times are Helsinki time.

## Team and workstreams

Team of 3. Each person owns clear areas so nobody steps on anyone else's work.

| Person | Workstreams | Folders they (and their agent) may edit |
|---|---|---|
| **A** _name_ | DATA → COACH (+ api) → BUTLER from M2 | `backend/kukkaro/data/`, `coach/`, `api/`, `butler/`, `docs/DATA_PROFILE.md` |
| **B** _name_ | WEB + RECEIPTS (code) | `web/`, `backend/kukkaro/receipts/` (except `catalog.csv`) |
| **C** _name_ | Product, content, testing, pitch | `backend/kukkaro/receipts/catalog.csv`, `docs/`, `README.md` |

**C's task list** (product, quality and pitch; ordered by when it's needed):
1. Sat morning: ask the S-Bank mentors about synthetic receipts and the Info Team about tech
   challenges/videos (see Setup). Log the answers in DECISIONS.md.
2. Sat by 12:00: write/check `catalog.csv` (150–300 Finnish grocery products with realistic
   prices, basket, store-brand twins). An LLM can draft it; C checks the prices against what
   things really cost. Columns are in `receipts/AGENTS.md`.
3. Sat afternoon: write the 15 coach test questions (for `coach/eval.py`) and 10 unseen Butler
   phrasings. Try them in the app every few hours and report wrong numbers or broken sources to A.
4. Sat evening: user-test on a real phone; collect UX issues for B.
5. Sat night: draft the pitch deck (S-Bank version + Exa version) and the README "For the judges" sections.
6. Sun 05:00–09:15: record the videos (docs/VIDEO.md), write the Verda summary post, fill both
   submission forms (docs/COMPLIANCE.md). A and B help with recording.
7. Sun 10:30: rehearsed 3-minute pitch ready in case we reach the top 5.

Give each person's AI agent this instruction: *"Read AGENTS.md and backend/kukkaro/<ws>/AGENTS.md
(or web/AGENTS.md). You are workstream <WS>. Do the next unchecked task in docs/PLAN.md for your
workstream, nothing else."* Run one workstream at a time in your agent; finish or reach
a milestone before switching.

## Setup (Fri night / first thing Sat): one person

- [ ] Create the GitHub repo `kukkaro` (public is fine from the start; it must be public by submission). Add these files.
- [ ] Download the S-Bank dataset into `data/raw/` (see `data/README.md`; it's a 346 MB Git LFS file).
- [ ] Everyone claims credits (Developer Tools and Assets page): Gemini (one form per team),
      Verda €200 (each person, redeemed into the shared "Kukkaro" Verda project), Exa $50. A Hugging Face account with the Gemma licence accepted (for self-hosting Gemma on Verda).
- [ ] Create `.env` locally from `.env.example`. Share keys privately, **never in Git or public Discord**.
- [ ] Ask S-Bank's mentors (Calle Holmberg, Chief Innovation Officer): *"OK to add synthetic
      receipt line items on top of your dataset?"* Log the answer in DECISIONS.md.
- [ ] Ask the Info Team on Discord: can the same tech challenges be ticked on both submissions?
      Does each submission need its own video?

## Milestones

### M1: walking skeleton (Sat 13:00)
One customer, end to end, ugly is fine.
- [ ] DATA: prepare.py, db.py, DATA_PROFILE.md, baskets.py v1, `spending_summary`, demo customer picked
- [ ] COACH: FastAPI app, `/api/health`, `/api/customers/{id}/summary`, `/api/chat` with Gemini + 2 tools
- [ ] WEB: Chat screen + Baskets screen against the real API
- [ ] RECEIPTS: models, catalog v1 (~80 items), generator with exact sums, `/api/transactions/{tx_id}/receipt`

### M2: the full story (Sat 20:00)
- [ ] DATA: all metrics in DATA/AGENTS.md, with tests
- [ ] RECEIPTS: personas, full catalogue, `leak_items`, `store_brand_savings`
- [ ] COACH: all tools, system prompt, eval.py passing on Gemini
- [ ] WEB: Receipt view, What-if, "How I got this"
- [ ] BUTLER: the 3 demo tasks working with sources (attend the Exa workshop, Sat 16:30)
- [ ] Gemma running on Verda behind `LLM_PROVIDER=gemma`; eval.py run on both

### M3: sell it (Sun 04:00)
- [ ] Deploy one public demo URL (backend + built frontend on a Verda CPU instance) → "Project Demo" field
- [ ] Verda batch job: precompute summaries/receipts for all 5,100 customers (the scale proof for Verda + S-Bank)
- [ ] WEB: Butler screen, privacy toggle, polish on a real phone
- [ ] Optional stretch: personal inflation, receipt-photo scan (Gemini vision, in-memory only)
- [ ] README sections per challenge filled in; DECISIONS.md tidy (it is our process log)

### Freeze and ship (Sun)
| Time | What |
|---|---|
| 05:00 | **Feature freeze.** Bug fixes only. |
| 05:00–07:30 | Record videos (see docs/VIDEO.md): Kukkaro ≤ 2:00, Butler ≤ 2:00. Upload as public/unlisted YouTube or Vimeo. |
| 07:30–08:30 | Pitch deck PDF (S-Bank version + Exa version), post Verda summary in Verda's Discord channel |
| 08:30–09:15 | Fill both submissions completely (see docs/COMPLIANCE.md), set **FINAL** |
| 09:30 | Buffer. Everything must be FINAL. |
| 10:00 | Deadline |
| 10:30 | **Whole team at our table for live peer review**, or we lose main-prize eligibility |
| 14:00 | Final ceremony (top 5 pitch 3 min + 3 min Q&A; we'd be told before the ceremony) |

## Useful events
- Sat 16:30–17:00: Exa workshop (Loft, 4th floor). BUTLER owner goes.
- Verda booth #6 (3rd floor): Gemma hosting, batch jobs.
- Google DeepMind booth: Gemini questions.
- S-Bank mentors: data questions, "does this fit S-mobiili?" feedback.

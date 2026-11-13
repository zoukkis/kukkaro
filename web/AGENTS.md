# Workstream WEB — `web/`

Read the root `AGENTS.md` first. You own **only** `web/`.

## Your job
A mobile-first web app that looks like it could be a tab inside S-mobiili. S-Bank asked for "a
mobile app, or a web app that can be embedded in a mobile app — our customers are on mobile".
Judges score **clarity of the mobile user experience** (20%).

## Stack (decided)
React + Vite + TypeScript, plain CSS or Tailwind (pick one, don't mix). No UI kit heavier than
that, no state library: React state plus `fetch` is enough. Design for a **390 × 844** viewport
first; the desktop view can just center the phone-width layout.

## Screens (in priority order; ship 1–3 before touching 4–6)
1. **Chat**: message list, input, suggested question chips. Each answer has a small "How I got this"
   expander showing `tool_calls` and `figures` from `/api/chat`.
2. **Baskets overview**: this month's spending in the three baskets (one clear chart, big numbers,
   plain labels), a "safe to spend this week" card, tap a basket to see its transactions.
3. **Receipt view**: tap a grocery transaction → items coloured by basket, leak items highlighted,
   a visible **"Synthetic example receipt"** badge. This screen sells the receipts idea; make it beautiful.
4. **What-if**: pick a category or item plus a slider (−100% … +50%) → monthly and yearly euros.
5. **Butler**: task input plus 3 example chips, answer with numbered source links and a
   next-steps checklist. Needs a loading state (Exa calls take a few seconds).
6. **Privacy toggle**: "EU privacy mode (Gemma on Verda)". Shows which model answered.

## Rules
- Call only the endpoints in root AGENTS.md §5.4 via one `src/api.ts`. If you need a new endpoint,
  request it in `docs/DECISIONS.md`. Don't mock forever: switch to the real API as soon as it exists.
- Every number displayed comes from the API. No computing totals in the frontend.
- Anything synthetic is labelled. No S-Bank or S-Group logos (we are not endorsed), but a calm
  "banking app" look is fine.
- Accessibility basics: 16px+ body text, good contrast, tap targets ≥ 44px.
- `npm run build` must pass before every push. Don't edit anything outside `web/`.

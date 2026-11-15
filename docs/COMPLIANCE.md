# Compliance checklist

Sources: Junction 2026 Participant Guide and the challenge pages on the Junction Platform (read
13 Nov 2026). Re-check the Discord #announcements channel; organizer answers there override this file.

## Junction rules (all prizes)
- [ ] **No code written before the event.** Everything in the repo was created after Fri 13 Nov 19:30.
      Open-source libraries are fine. Don't reuse code from older personal projects.
- [ ] Team size 1–4.
- [ ] Participate in at least one main challenge. **One submission per main challenge** (Info Team,
      13 Nov): Kukkaro → S-Pankki; Kukkaro Butler → Exa.
- [ ] Not related to any existing company of ours.
- [ ] Source code link submitted, accessible to organizers. **All submissions are MIT-licensed**
      (LICENSE file present).
- [ ] Partner APIs and data are used under partner terms (owned by them, not MIT).
- [ ] **Pitch video ≤ 2:00, not a second longer.** Publicly viewable (YouTube or Vimeo).
- [ ] The whole team at the live peer review on Sunday from 10:30, reviewing the projects assigned
      to us. Otherwise no main prize.

## Submission form, per submission
- [ ] Project name (≤ 30 chars), punchline (≤ 200), description (≤ 5000, markdown)
- [ ] Main challenge selected; tech challenges ticked (Kukkaro: Gemini, Gemma, Verda)
- [ ] Project Demo URL (works without login; test on a phone and in incognito)
- [ ] Source code URL (public repo)
- [ ] Video URL (≤ 2:00)
- [ ] Presentation PDF (≤ 20 MB)
- [ ] Phone numbers of team members and Discord usernames (if asked)
- [ ] Status switched from **DRAFT to FINAL** before Sun 10:00 (drafts are not reviewed)

## Data and privacy
- [ ] Only S-Bank's synthetic dataset, our own synthetic receipts and public open data. No real
      personal, banking or receipt data anywhere: repo, demo, video, screenshots.
- [ ] Synthetic receipts labelled as synthetic in the UI, README, video and deck.
- [ ] Raw dataset **not committed** (346 MB; also not ours to redistribute). The README explains how to get it.
- [ ] No API keys in the repo history (`git log -p | grep -i key` check before making the repo public).
- [ ] The receipt-photo scan (if built) processes in memory and stores nothing.
- [ ] No S-Bank or S-Group logos, and no claim of endorsement.

## Challenge-specific requirements

**S-Pankki: Personal Economic Trainer**
- [ ] Mobile app, or a web app embeddable in a mobile app
- [ ] Pedagogical angle: the three baskets are visible in the product
- [ ] Data exploration in the MyData spirit (the user asks freely; not only fixed charts)
- [ ] Pitch covers feasibility and how it fits into S-mobiili

**Exa: Internet Butler**
- [ ] Demo on a real case; works on live queries the judges type
- [ ] Sources shown clearly for every claim
- [ ] Final approval left to the user

**Verda Compute Track (tech)**
- [ ] **Minimum requirement (challenge page, re-checked 15 Nov 03:30): document your process, and submit via Junction Platform → Challenges → Verda Compute Track** (tick Verda on the submission). No Discord post is required; docs/DECISIONS.md is the process log.
- [ ] Explain which Verda products were used and why; show a path to scale

**Gemini API (tech)**
- [ ] The submission text explains: the problem, how Gemini is integrated, what's innovative, and why Gemini matters
- [ ] Credits form filled by one team member (18+ only)

**Gemma (tech)**
- [ ] Gemma actually used (EU privacy mode on Verda); results compared in the README

## Before pressing FINAL
- [ ] Fresh clone → follow the README → the app runs
- [ ] Video length checked in the player: ≤ 2:00
- [ ] Demo URL opened on a phone on mobile data

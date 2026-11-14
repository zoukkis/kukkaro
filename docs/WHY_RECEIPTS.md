# Why combine S-Group receipts with S-Bank data?

S-Bank told us (14 Nov) they **have not yet found a good enough reason** to combine S-Group
purchase data with banking data. Answering that convincingly is the core of our pitch. Every
receipt feature must serve one of the reasons below, and the demo must *show* the difference.

## The one-line answer
**Card data tells you where you shopped. Receipts tell you what you bought. You can only change
what you can see.**

## Reasons (user value first)
1. **The "everyday spending" basket is invisible without receipts.** S-Bank's own model has three
   baskets, but a grocery payment is one line: "Prisma −€47". Card data has to put the whole trip
   in one basket. Receipts split it: milk and bread are regular essentials, the energy drink and
   pastry are everyday leaks. Groceries are one of the biggest spending categories, so without
   receipts the most teachable basket is mostly hidden.
2. **Specific advice changes behaviour, generic advice doesn't.** "Spend less on groceries" is
   ignored. "Halving energy drinks saves €210 a year, that's a weekend trip" is acted on.
   (Reviewers of Revolut's assistant AIR criticised exactly this: generic savings advice without
   specific spending drivers.)
3. **It answers "why is my money disappearing?"** Repeat purchases show the user's *personal*
   inflation compared with Statistics Finland's index: is life getting pricier, or am I buying more?
4. **Better "safe to spend".** Warranty receipts (appliances, electronics) let the coach forecast
   unexpected necessities ("your washing machine is 9 years old") instead of treating them as surprises.
5. **Planned vs impulse shopping.** S-mobiili also shows grocery web-shop orders. Online orders
   are planned; store trips include impulse buys. Comparing the two ("your online orders are 92%
   essentials, your store trips 68%") gives a concrete, measurable saving only a bank + retailer
   combination can calculate. (Synthetic `channel: online_order` receipts in this demo.)
6. **Savings that cost the user nothing.** Store-brand twins and S-Etukortti Bonus show money the
   user can keep without changing *what* they eat.

## Why it's good for S-Bank and S-Group
- **A moat no competitor can copy.** Revolut, Nordea or OP have card data only. S-Group is the only
  group in Finland with a bank *and* the grocery receipts. This feature is uniquely theirs.
- **Engagement in S-mobiili.** A coach that knows what you bought is worth opening weekly.
- **Win-win nudges.** Store-brand and Bonus suggestions save the customer money *and* keep spending
  in the group. Nobody loses.
- **Strategy fit.** Financial literacy for young adults; digital-first service in S-mobiili.

## How it stays trustworthy (pre-empt the objections)
- **Opt-in, per user.** Off by default. The user turns it on in S-mobiili and can turn it off and
  delete it any time (MyData spirit: their data, their choice).
- **Show value before asking.** A preview ("with receipts you'd see that 26% of your grocery spend
  is snacks and drinks") on the user's own data explains *why* to opt in.
- **Purpose-limited.** Used only for the user's own coaching, never for marketing profiling,
  credit decisions or sharing (also required by the Gemma prohibited-use policy).
- **Stays in Europe.** EU privacy mode: open-weight Gemma on Verda, no third-party API.
- **Synthetic in this demo.** All receipt data here is generated and labelled. Production would read
  the receipt archive S-mobiili already has, with consent.
  The full production data path (bank data or PSD2, and the `ReceiptProvider` swap) is in
  `docs/PRODUCTION_PATH.md`.

## How S-Bank could validate it in a pilot
Opt-in rate after the preview · share of users who act on a receipt-based suggestion · change in
"everyday spending" over 3 months · S-mobiili weekly active use · customer satisfaction.

## The demo moment that proves it (build this)
A **"With receipts / Without receipts" toggle** on the same month for the same customer:
- Without: "Groceries €412 (Regular essentials)."
- With: "Groceries €412: €305 essentials, **€107 everyday spending** (energy drinks €38, pastries
  €29, candy €22…)" plus a concrete what-if.
Same data, same coach: the only difference is the receipts. That *is* the reason.

## Prior art (checked 14 Nov 2026): proven pieces, missing coaching
- **ICA (Sweden), the closest analogue:** a grocery chain with its own bank (ICA Banken). In 2018
  it launched the ICA Spara app showing customers' grocery purchases, bills and subscriptions in one
  place, plus the climate impact of their food purchases.
- **Walmart OnePay (US):** a retailer-backed money app (banking, cards, cash-back, BNPL), ~6M monthly
  users. Focus is rewards and credit, not coaching.
- **Itemised receipts inside bank apps:** Nordea Wallet in Finland with ReceiptHero (first major
  Nordic bank partnership), Barclays with Flux (UK), NAB with Slyp (Australia). They *show* the
  receipt next to the card purchase.
- **The gap Kukkaro fills:** these products display receipts or give rewards; none turn line items
  into coaching (baskets, everyday leaks, what-if, store-brand savings, safe-to-spend). And S-Group
  already owns both the bank and the receipts, so it needs no third-party receipt matching.
- Pitch line: "Receipts in bank apps are proven (Nordea, Barclays). Nobody coaches with them yet."

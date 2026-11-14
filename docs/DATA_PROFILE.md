# Data profile: S-Bank synthetic dataset (Junction 2026)

Profiled on 14 Nov 2026 by the DATA workstream from `data/raw/` (source:
https://github.com/hackjunction/Junction-2026-S-pankki). Every basket rule and metric is based on
this file. Reproduce: `cd backend && python -m kukkaro.data.prepare` prints the integrity checks.

## Size and shape
| | |
|---|---|
| Transactions | **3,626,755** rows (`tx_junction_transactions.csv`, 346 MB) |
| Customers | **5,100**, each with exactly **one** bank account |
| Period | **2024-10-01 to 2026-09-30** (24 full months). "Today" defaults to 2026-09-30 |
| Rows per customer | min 148, median 700, max 1,543 (about 29 a month at the median) |

## Columns and formats
- Files start with a UTF-8 BOM. `prepare.py` reads them as UTF-8 and checks the column names.
- `tx_timestamp` uses a SAS-style format: `03OCT24:09:04:04` (`%d%b%y:%H:%M:%S`). Its date always
  equals `tx_date` (0 mismatches).
- `tx_amount_eur` and `balance_after_eur` have at most 2 decimals and are stored as exact `DECIMAL(18,2)`.
- **Sign convention: negative = money out, positive = money in.** Every purchase and bill is
  negative; salary, other income and investment withdrawals are positive.
- `merchant_id` and `mcc_code` are blank on all bills, income and transfers **and on 160,624
  purchases (5% of purchases)**. They are always blank together. No "." values occur, but
  `prepare.py` turns both blank and "." into NULL.
- `merchant_id` looks like `MRC-GRO-0035`; the middle part encodes the category. There are no merchant names.
- `customer_postal_code` is 5 characters with leading zeros (`00990`) and is stored as text.
  Every code starts with 00, 01 or 02 (Helsinki, Vantaa, Espoo area).

## Ordering and integrity
- The file is sorted by customer, then by timestamp (0 out-of-order rows, 59 timestamp ties).
- **The running balance chains perfectly in file order**: `previous balance + amount = balance`
  on all 3,621,655 consecutive pairs. File order is therefore booking order, and
  `tx_id = "{customer_id}-{n}"` (n = 1, 2, … in file order) is stable.

## Categories (each has exactly one `transaction_type`)
| category | transaction_type | rows | sign | median € | MCCs |
|---|---|---:|---|---:|---|
| Groceries | purchase | 868,519 | − | −64.06 | 5411 grocery, 5499 convenience/specialty, 5422 butcher, 5451 dairy |
| Restaurants | purchase | 759,280 | − | −23.49 | 5812 eating places, 5814 fast food, 5813 bars |
| Transportation | purchase | 626,930 | − | −41.26 | 5542/5541 fuel, 7523 parking, 4111 public transport, 4121 taxis |
| Utilities | utilities_payment | 342,728 | − | −50.14 | none |
| Entertainment | purchase | 302,691 | − | −35.20 | 7922 tickets, 7999 recreation, 7832 cinema, 7991 attractions, 7996 amusement parks |
| Health | purchase | 151,912 | − | −53.85 | 5912 pharmacy, 8011 doctor, 8099 health services, 8021 dentist |
| Salary | salary | 121,725 | + | 3,163.99 | none |
| Home & Tech | purchase | 115,086 | − | −111.08 | 5200 home supply, 5732 electronics, 5251 hardware, 5712 furniture, 5734 software |
| Housing | housing_payment | 112,903 | − | −1,037.17 | none |
| Lifestyle | purchase | 110,916 | − | −103.31 | 5941 sports, 5651/5691 clothing, 5999 other retail, 5942 books, 5945 toys/hobby |
| Travel | purchase | 65,377 | − | −129.66 | 4722 travel agency, 4511 airlines, 7011 hotels, 7512 car rental |
| Invest Deposit | investment_deposit | 35,668 | − | −296.45 | none |
| Other Income | other_income | 6,299 | + | 2,081.38 | none |
| Salary Sweep | salary_sweep | 6,189 | − | −3,877.26 | none |
| Invest Withdraw | investment_withdrawal | 532 | + | 1,341.19 | none |

Within a category, amounts have almost the same distribution for every MCC (e.g. every
Transportation MCC has a median near −41 €). In other words, the data generator draws amounts per
category, not per merchant type.

## Income and recurring patterns
- **Salary: exactly one a month for every customer** (24 each). It arrives mostly on the 15th
  (96,097 of 121,725); the rest arrive at month end (26th to 31st). Salary amounts vary every month.
- **Housing: one payment a month** for 4,882 customers. Many miss a few months (2,996 have all
  24). The amount varies around a fixed level (about ±5% a month). **There are no clear rent increases**:
  comparing the last 3 payments with the first 3, every customer is between −10% and +10%.
- **Utilities: about 2.9 bills a month** (1 to 5), with no merchant, so electricity, water and
  internet cannot be told apart. They are mildly seasonal: about 175 € a month in Nov to Mar vs
  about 162 € in Apr to Oct (average per customer).
- Invest Deposit: monthly for 1,500 customers. Salary Sweep: monthly for 264 customers. Other
  Income: irregular, 2,401 customers.
- **No recurring purchases exist**: no customer pays the same merchant in 6+ months at a similar
  amount. Subscriptions do not appear in this data. The typical customer visits a given merchant
  in only 2 different months.

## Outliers and balances
- Purchases have a heavy tail. For example, the largest grocery purchase is −15,902 €, while the
  p99.9 is −242 €. Purchases above 20× their category median: Restaurants 1,053, Entertainment 507,
  Home & Tech 422, Groceries 68 (of 868,519).
- 3,526 of 5,100 customers dip below 0 € at some point (median lowest balance −125.86 €).

## Customers
- Ages 18 to 90, median 44. Age bands: 18-24: 419 · 25-34: 658 · 35-49: 2,712 · 50-64: 1,036 · 65+: 275.
- 290 distinct postal codes. Areas: 00xxx 2,557 · 02xxx 1,427 · 01xxx 1,116.

## Median monthly amounts per customer
Salary 3,163.99 · Housing 1,037.17 · Groceries 440.12 · Restaurants 244.58 · Transportation 236.52 · Utilities 150.94

## What this means for the baskets (`backend/kukkaro/data/baskets.py`)
| Basket (S-Bank label) | Rows |
|---|---|
| 🏠 Regular essentials (`MANDATORY_REGULAR`) | Housing, Utilities, Groceries, Transportation (fuel, public transport, purchases without MCC) |
| 🔧 Unexpected necessities (`MANDATORY_IRREGULAR`) | Health, Home & Tech |
| ☕ Everyday spending (`EVERYDAY`) | Restaurants, Entertainment, Lifestyle, Travel, **Taxis (4121)**, **Parking (7523)** |
| Income | Salary, Other Income |
| Transfers and savings | Invest Deposit, Invest Withdraw, Salary Sweep |

The share of rows per basket is: Regular 1,758,250 · Everyday 1,431,094 · Irregular 266,998 · Income 128,024 · Transfers 42,389.

Consequences:
- **Groceries are one regular-essentials line without receipts.** Card data cannot split a grocery
  trip. That is the case for receipts (`docs/WHY_RECEIPTS.md`).
- **The recurring-merchant rule never fires on this data**, so baskets are assigned by category and
  MCC only. `recurring_payments()` still applies the rule and also reports bills by category.
- **"Taxis", "fast food", "fuel" etc. are subcategories (from MCC).** `tx_enriched.subcategory`
  makes them queryable. The 5% of purchases without an MCC keep their category name as subcategory.
- **Receipts:** groceries have 13,012 purchases without merchant or MCC, and a few extreme amounts
  (68 above 20× the median). The generator should handle or skip implausible trips.
- **Butler:** "my rent went up" cannot be shown from a rise in the data (rent only varies ±10%). Rises do
  show up in utilities from month to month; `recurring_payments()` reports `change_pct`.

## Demo customer: CUST02979
Picked to tell S-Bank's four questions and the With/Without receipts story (reasoning in
`docs/DECISIONS.md`). All figures as of 2026-09-30, from `kukkaro.data.metrics`:
- Age 22, postal code 02360 (Espoo). Rent paid every one of the 24 months (Sep: 607.12 €), salary about 2,170 € a month.
- Spending Jul to Sep: Regular essentials 61.4%, Unexpected necessities 8.6%, Everyday spending
  30.0% (age-band 18-24 medians: 66.5%, 6.5%, 26.7%).
- Groceries are the largest category in September: 611.16 € in 9 trips. Receipts can reveal the leaks inside them.
- Safe to spend until payday 15 Oct: 272.27 € (18.15 € a day, 127.05 € this week).
- Utilities: typical 65.70 € a month, September 144.73 € (+120.3%). This is the Butler's "am I overpaying for electricity?" case.
- Taxis in August: 90.76 € (2 rides). Unexpected necessities in September: Home & Tech 271.09 €, Health 183.18 €.

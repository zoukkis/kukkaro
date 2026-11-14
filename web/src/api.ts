// The ONLY place the web app talks to the backend (root AGENTS.md §5.4).
// While the backend isn't ready, USE_MOCK=true returns hard-coded mock data with the same shapes.
// To switch to the real API: set VITE_USE_MOCK=false in web/.env.local. Nothing else changes.

export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";
export const CUSTOMER_ID: string = import.meta.env.VITE_CUSTOMER_ID ?? "CUST02979";
const BASE = "/api";

// ---------- Types (shared contract §5.2 / §5.4) ----------

export type Basket =
  | "MANDATORY_REGULAR"
  | "MANDATORY_IRREGULAR"
  | "EVERYDAY"
  | "INCOME"
  | "TRANSFER";

export type SpendingBasket = "MANDATORY_REGULAR" | "MANDATORY_IRREGULAR" | "EVERYDAY";

export interface BasketTotal {
  basket: SpendingBasket;
  total_eur: number;
  share_pct: number; // share of total spending, computed by the backend
  tx_count: number;
}

export interface CategoryTotal {
  category: string;
  basket: Basket;
  total_eur: number;
}

// Present on /summary?receipts=true: the grocery payments re-split by receipt line (synthetic).
export interface ReceiptSplit {
  grocery_total_eur: number;
  without_receipt_eur: number;
  split: { basket: SpendingBasket; label: string; total_eur: number }[];
  top_leak_items: { name: string; total_eur: number; qty: number }[];
  synthetic: true;
}

export interface Summary {
  customer_id: string;
  month: string; // YYYY-MM
  income_eur: number;
  spending_eur: number;
  balance_eur: number;
  baskets: BasketTotal[];
  top_categories: CategoryTotal[];
  receipts?: ReceiptSplit | null;
  synthetic?: boolean;
}

// Receipt contract (root AGENTS.md §5.3). Always synthetic in this project.
export interface ReceiptItem {
  name: string;
  category: string;
  qty: number;
  unit_price_eur: number;
  line_total_eur: number;
  basket: SpendingBasket;
  store_brand: boolean;
}

export interface Receipt {
  tx_id: string;
  store: string;
  timestamp: string;
  total_eur: number;
  synthetic: true;
  channel?: "in_store" | "online_order";
  delivery_fee_eur?: number;
  items: ReceiptItem[];
}

export interface ButlerSource {
  n: number;
  title: string;
  url: string;
  published_date?: string | null;
  cited?: boolean;
}

export interface ButlerResponse {
  answer: string;
  sources: ButlerSource[];
  next_steps: string[];
  draft?: { kind: string; to: string | null; subject: string; body: string; open_url: string | null; mailto: string | null } | null;
  model?: string;
  cached?: boolean;
  error?: string;
}

// GET /customers/{id}/butler/suggestions: proactive "your bill went up" cards (numbers from DATA).
export interface BillSuggestion {
  kind: "bill_went_up";
  category: string;
  what: string; // "utility bills" | "rent"
  title: string;
  latest_month: string; // YYYY-MM
  latest_month_eur: number;
  typical_monthly_eur: number;
  change_pct: number;
  task: string; // send this to the Butler on tap
  source: string;
}

export type Provider = "gemini" | "gemma";

export interface Transaction {
  tx_id: string;
  customer_id: string;
  bank_account_id: string;
  tx_date: string;
  tx_timestamp: string;
  category: string;
  subcategory?: string | null; // from MCC, e.g. "Taxis" inside Transportation (DATA)
  tx_amount_eur: number; // negative = money out
  balance_after_eur: number;
  transaction_type: string;
  merchant_id: string | null; // blank on bills, income, transfers and 5% of purchases
  mcc_code: string | null;
  basket: Basket;
}

export interface TransactionPage {
  items: Transaction[];
  total: number;
  limit: number;
  offset: number;
}

export interface SafeToSpend {
  amount_eur: number; // until payday
  until_date: string; // next payday (estimated)
  per_day_eur: number;
  this_week_eur: number;
  status?: string;
  explanation_inputs: Record<string, unknown>;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
}

export interface Figure {
  label: string;
  value: number;
  unit: "EUR" | "%" | "count";
  source: string; // which period / basket the number came from
}

export interface ChatResponse {
  answer: string;
  tool_calls: ToolCall[];
  figures: Figure[];
  model?: string;
  host?: string; // "google" | "verda": "EU privacy mode" may only be shown when "verda"
  provider?: Provider;
  number_check?: "ok" | "retried" | "withheld";
}

// ---------- Real API ----------

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

const real = {
  summary: (id: string, month?: string, receipts = false) => {
    const q = new URLSearchParams();
    if (month) q.set("month", month);
    if (receipts) q.set("receipts", "true");
    return http<Summary>(`/customers/${encodeURIComponent(id)}/summary?${q}`);
  },
  transactions: (id: string, opts: { limit?: number; offset?: number; basket?: Basket; month?: string } = {}) => {
    const q = new URLSearchParams();
    if (opts.limit != null) q.set("limit", String(opts.limit));
    if (opts.offset != null) q.set("offset", String(opts.offset));
    if (opts.basket) q.set("basket", opts.basket);
    if (opts.month) q.set("month", opts.month);
    return http<TransactionPage>(`/customers/${encodeURIComponent(id)}/transactions?${q}`);
  },
  // null = no receipt for this transaction (404: not a grocery purchase)
  receipt: async (txId: string): Promise<Receipt | null> => {
    const res = await fetch(`${BASE}/transactions/${encodeURIComponent(txId)}/receipt`);
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json() as Promise<Receipt>;
  },
  butler: (customer_id: string, task: string) =>
    http<ButlerResponse>(`/butler`, { method: "POST", body: JSON.stringify({ customer_id, task }) }),
  safeToSpend: (id: string) =>
    http<SafeToSpend>(`/customers/${encodeURIComponent(id)}/safe-to-spend`),
  suggestions: (id: string) =>
    http<{ suggestions: BillSuggestion[] }>(`/customers/${encodeURIComponent(id)}/butler/suggestions`),
  chat: (customer_id: string, message: string, history: ChatTurn[], provider?: Provider) =>
    http<ChatResponse>(`/chat`, {
      method: "POST",
      body: JSON.stringify({ customer_id, message, history, ...(provider ? { provider } : {}) }),
    }),
};

// ---------- Mock data (delete once the backend is live) ----------
// Shaped like the demo customer DATA picked (CUST02979, Sep 2026, see docs/DECISIONS.md).
// Values are illustrative except where DECISIONS.md states them (groceries, taxis, safe to spend).

const MOCK_MONTH = "2026-09";
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

const mockSummary: Summary = {
  customer_id: CUSTOMER_ID,
  month: MOCK_MONTH,
  income_eur: 2640.0,
  spending_eur: 2380.4,
  balance_eur: 612.3,
  baskets: [
    { basket: "MANDATORY_REGULAR", total_eur: 1526.6, share_pct: 64.1, tx_count: 13 },
    { basket: "MANDATORY_IRREGULAR", total_eur: 139.7, share_pct: 5.9, tx_count: 2 },
    { basket: "EVERYDAY", total_eur: 714.1, share_pct: 30.0, tx_count: 24 },
  ],
  top_categories: [
    { category: "Housing", basket: "MANDATORY_REGULAR", total_eur: 760.0 },
    { category: "Groceries", basket: "MANDATORY_REGULAR", total_eur: 611.16 },
    { category: "Restaurants", basket: "EVERYDAY", total_eur: 284.3 },
    { category: "Utilities", basket: "MANDATORY_REGULAR", total_eur: 144.73 },
    { category: "Entertainment", basket: "EVERYDAY", total_eur: 132.0 },
  ],
};

type Row = readonly [string, string, string | null, number, Basket, string, string | null, string | null];
const rows: Row[] = [
  ["2026-09-01", "Housing", null, -760.0, "MANDATORY_REGULAR", "housing_payment", null, null],
  ["2026-09-02", "Groceries", "Grocery stores", -72.4, "MANDATORY_REGULAR", "purchase", "MRC-GRO-0035", "5411"],
  ["2026-09-03", "Restaurants", "Fast food", -14.9, "EVERYDAY", "purchase", "MRC-RES-0112", "5814"],
  ["2026-09-05", "Utilities", null, -144.73, "MANDATORY_REGULAR", "utilities_payment", null, null],
  ["2026-09-06", "Groceries", "Grocery stores", -88.15, "MANDATORY_REGULAR", "purchase", "MRC-GRO-0035", "5411"],
  ["2026-09-07", "Transportation", "Taxis", -31.2, "EVERYDAY", "purchase", "MRC-TRA-0041", "4121"],
  ["2026-09-09", "Entertainment", "Cinema", -24.0, "EVERYDAY", "purchase", "MRC-ENT-0007", "7832"],
  ["2026-09-10", "Groceries", "Convenience / specialty", -41.3, "MANDATORY_REGULAR", "purchase", "MRC-GRO-0102", "5499"],
  ["2026-09-12", "Health", "Pharmacy", -39.7, "MANDATORY_IRREGULAR", "purchase", "MRC-HEA-0019", "5912"],
  ["2026-09-13", "Restaurants", "Bars", -46.5, "EVERYDAY", "purchase", "MRC-RES-0090", "5813"],
  ["2026-09-15", "Salary", null, 2640.0, "INCOME", "salary", null, null],
  ["2026-09-16", "Groceries", "Grocery stores", -95.6, "MANDATORY_REGULAR", "purchase", "MRC-GRO-0035", "5411"],
  ["2026-09-18", "Home & Tech", "Electronics", -100.0, "MANDATORY_IRREGULAR", "purchase", "MRC-HOM-0044", "5732"],
  ["2026-09-19", "Transportation", "Public transport", -63.9, "MANDATORY_REGULAR", "purchase", "MRC-TRA-0003", "4111"],
  ["2026-09-20", "Restaurants", "Eating places", -38.4, "EVERYDAY", "purchase", "MRC-RES-0151", "5812"],
  ["2026-09-23", "Groceries", "Grocery stores", -79.2, "MANDATORY_REGULAR", "purchase", "MRC-GRO-0035", "5411"],
  ["2026-09-26", "Lifestyle", "Clothing", -89.9, "EVERYDAY", "purchase", "MRC-LIF-0060", "5651"],
  ["2026-09-28", "Invest Deposit", null, -150.0, "TRANSFER", "investment_deposit", null, null],
];
const mockTx: Transaction[] = rows.map(
  ([date, category, subcategory, amount, basket, type, merchant, mcc], i) => ({
    tx_id: `${CUSTOMER_ID}-${640 + i}`,
    customer_id: CUSTOMER_ID,
    bank_account_id: "ACC-MOCK-1",
    tx_date: date,
    tx_timestamp: `${date}T12:00:00`,
    category,
    subcategory,
    tx_amount_eur: amount,
    balance_after_eur: 0,
    transaction_type: type,
    merchant_id: merchant,
    mcc_code: mcc,
    basket,
  }),
);

const mockSafe: SafeToSpend = {
  amount_eur: 272.27,
  until_date: "2026-10-15",
  per_day_eur: 18.15,
  this_week_eur: 127.05,
  explanation_inputs: {
    balance_eur: 612.3,
    regular_essentials_still_expected_eur: 485.25,
    days_until_salary: 15,
  },
};

const fig = (label: string, value: number, unit: Figure["unit"], source: string): Figure => ({
  label,
  value,
  unit,
  source,
});

function mockChat(message: string): ChatResponse {
  const m = message.toLowerCase();
  const src = `Sep 2026, all baskets`;
  if (m.includes("where") || m.includes("go")) {
    return {
      answer:
        "In September you spent €2,380.40. Most of it (64%) went to 🏠 Regular essentials, mainly rent (€760) and groceries (€611.16 over 9 trips). ☕ Everyday spending was €714.10, led by restaurants and bars.",
      tool_calls: [{ name: "spending_summary", args: { month: MOCK_MONTH } }],
      figures: [
        fig("Total spending", 2380.4, "EUR", src),
        fig("🏠 Regular essentials", 1526.6, "EUR", "Sep 2026, MANDATORY_REGULAR"),
        fig("☕ Everyday spending", 714.1, "EUR", "Sep 2026, EVERYDAY"),
      ],
    };
  }
  if (m.includes("spender") || m.includes("kind")) {
    return {
      answer:
        "On card data alone you look fairly average for your age: 30% of your spending is ☕ Everyday spending, versus a 26.7% median for people aged 18–24. But groceries are your biggest category, and card data can't see what's inside those trips.",
      tool_calls: [{ name: "spender_profile", args: {} }],
      figures: [
        fig("Your everyday share", 30.0, "%", "Last complete months, EVERYDAY"),
        fig("Median everyday share, ages 18–24", 26.7, "%", "Peer customers, EVERYDAY"),
      ],
    };
  }
  if (m.includes("safe") || m.includes("week")) {
    return {
      answer:
        "You can safely spend about €127.05 this week. That's your balance minus the regular essentials still expected before your next salary (around 15 Oct).",
      tool_calls: [{ name: "safe_to_spend", args: {} }],
      figures: [
        fig("Safe to spend", 127.05, "EUR", "30 Sep → 15 Oct 2026"),
        fig("Regular essentials still expected", 485.25, "EUR", "Typical month, MANDATORY_REGULAR"),
      ],
    };
  }
  if (m.includes("save")) {
    return {
      answer:
        "Your biggest lever is ☕ Everyday spending. Cutting restaurants by half would save about €142 a month, or €1,706 a year. Taxis are another: €90.76 in August. Your utilities also jumped to €144.73 (usually about €65.70), worth a check.",
      tool_calls: [
        { name: "spending_summary", args: { month: MOCK_MONTH } },
        { name: "what_if", args: { category_or_item: "Restaurants", change_pct: -50 } },
        { name: "recurring_payments", args: {} },
      ],
      figures: [
        fig("Saving per month", 142.15, "EUR", "What-if on Restaurants, −50%"),
        fig("Saving per year", 1705.8, "EUR", "What-if on Restaurants, −50%"),
        fig("Utilities change", 120.3, "%", "Sep 2026 vs typical month"),
      ],
    };
  }
  return {
    answer:
      "I can answer questions about your own spending, like where your money went or what's safe to spend this week. (Mock mode: only the suggested questions have real-looking answers.)",
    tool_calls: [],
    figures: [],
  };
}

const mockReceiptSplit: ReceiptSplit = {
  grocery_total_eur: 611.16,
  without_receipt_eur: 0,
  split: [
    { basket: "MANDATORY_REGULAR", label: "Regular essentials", total_eur: 404.42 },
    { basket: "MANDATORY_IRREGULAR", label: "Unexpected necessities", total_eur: 5.99 },
    { basket: "EVERYDAY", label: "Everyday spending", total_eur: 200.75 },
  ],
  top_leak_items: [
    { name: "Energy drink 0.5 l", total_eur: 81.59, qty: 41 },
    { name: "Pick-and-mix candy 200 g", total_eur: 40.8, qty: 17 },
  ],
  synthetic: true,
};

const mockReceipt = (txId: string): Receipt => ({
  tx_id: txId,
  store: "S-market (synthetic)",
  timestamp: "2026-09-02T17:42:00",
  total_eur: 12.37,
  synthetic: true,
  channel: "in_store",
  items: [
    { name: "Lactose-free milk 1 l", category: "dairy", qty: 2, unit_price_eur: 1.39, line_total_eur: 2.78, basket: "MANDATORY_REGULAR", store_brand: false },
    { name: "Rye bread", category: "bakery", qty: 1, unit_price_eur: 2.49, line_total_eur: 2.49, basket: "MANDATORY_REGULAR", store_brand: true },
    { name: "Energy drink 0.5 l", category: "drinks", qty: 2, unit_price_eur: 1.99, line_total_eur: 3.98, basket: "EVERYDAY", store_brand: false },
    { name: "Cinnamon bun", category: "bakery", qty: 2, unit_price_eur: 1.56, line_total_eur: 3.12, basket: "EVERYDAY", store_brand: false },
  ],
});

const mock: typeof real = {
  summary: async (_id, _month, receipts = false) => {
    await wait(300);
    return receipts ? { ...mockSummary, receipts: mockReceiptSplit, synthetic: true } : mockSummary;
  },
  receipt: async (txId) => {
    await wait(200);
    return mockTx.find((t) => t.tx_id === txId)?.category === "Groceries" ? mockReceipt(txId) : null;
  },
  butler: async (_id, task) => {
    await wait(1200);
    return {
      answer: `Mock mode: the Butler needs the real backend and an Exa key to answer "${task}".`,
      sources: [],
      next_steps: [],
      model: "mock",
    };
  },
  transactions: async (_id, opts = {}) => {
    await wait(250);
    const all = opts.basket ? mockTx.filter((t) => t.basket === opts.basket) : mockTx;
    const offset = opts.offset ?? 0;
    const limit = opts.limit ?? 50;
    return { items: all.slice(offset, offset + limit), total: all.length, limit, offset };
  },
  safeToSpend: async () => (await wait(200), mockSafe),
  // Values as logged in docs/DECISIONS.md for the demo customer (utility bills, Sep 2026).
  suggestions: async () => (
    await wait(200),
    {
      suggestions: [
        {
          kind: "bill_went_up" as const,
          category: "Utilities",
          what: "utility bills",
          title: "Your utility bills went up",
          latest_month: MOCK_MONTH,
          latest_month_eur: 144.73,
          typical_monthly_eur: 65.7,
          change_pct: 120.3,
          task: "My utility bills went up a lot last month. Why might that be, and how can I pay less?",
          source: "your bank data, 2026-09 vs the 3 months before",
        },
      ],
    }
  ),
  chat: async (_id, message, _history, provider) => (
    await wait(900), { ...mockChat(message), model: "mock", provider: provider ?? "gemini", host: "mock" }
  ),
};

export const api = USE_MOCK ? mock : real;

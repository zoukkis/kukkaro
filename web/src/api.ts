// The ONLY place the web app talks to the backend (root AGENTS.md §5.4).
// While the backend isn't ready, USE_MOCK=true returns hard-coded mock data with the same shapes.
// To switch to the real API: set VITE_USE_MOCK=false in web/.env.local. Nothing else changes.

export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";
export const CUSTOMER_ID: string = import.meta.env.VITE_CUSTOMER_ID ?? "DEMO";
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

export interface Summary {
  customer_id: string;
  month: string; // YYYY-MM
  income_eur: number;
  spending_eur: number;
  balance_eur: number;
  baskets: BasketTotal[];
  top_categories: CategoryTotal[];
}

export interface Transaction {
  tx_id: string;
  customer_id: string;
  bank_account_id: string;
  tx_date: string;
  tx_timestamp: string;
  category: string;
  tx_amount_eur: number; // negative = money out
  balance_after_eur: number;
  transaction_type: string;
  merchant_id: string;
  mcc_code: string;
  basket: Basket;
}

export interface TransactionPage {
  items: Transaction[];
  total: number;
  limit: number;
  offset: number;
}

export interface SafeToSpend {
  amount_eur: number;
  until_date: string;
  explanation_inputs: Record<string, number | string>;
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
  summary: (id: string, month?: string) =>
    http<Summary>(`/customers/${encodeURIComponent(id)}/summary${month ? `?month=${month}` : ""}`),
  transactions: (id: string, opts: { limit?: number; offset?: number; basket?: Basket } = {}) => {
    const q = new URLSearchParams();
    if (opts.limit != null) q.set("limit", String(opts.limit));
    if (opts.offset != null) q.set("offset", String(opts.offset));
    if (opts.basket) q.set("basket", opts.basket);
    return http<TransactionPage>(`/customers/${encodeURIComponent(id)}/transactions?${q}`);
  },
  safeToSpend: (id: string) =>
    http<SafeToSpend>(`/customers/${encodeURIComponent(id)}/safe-to-spend`),
  chat: (customer_id: string, message: string, history: ChatTurn[]) =>
    http<ChatResponse>(`/chat`, {
      method: "POST",
      body: JSON.stringify({ customer_id, message, history }),
    }),
};

// ---------- Mock data (delete once the backend is live) ----------

const MOCK_MONTH = "2026-10";
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

const mockSummary: Summary = {
  customer_id: CUSTOMER_ID,
  month: MOCK_MONTH,
  income_eur: 2850.0,
  spending_eur: 2214.6,
  balance_eur: 1342.18,
  baskets: [
    { basket: "MANDATORY_REGULAR", total_eur: 1388.4, share_pct: 62.7, tx_count: 14 },
    { basket: "MANDATORY_IRREGULAR", total_eur: 289.0, share_pct: 13.0, tx_count: 2 },
    { basket: "EVERYDAY", total_eur: 537.2, share_pct: 24.3, tx_count: 31 },
  ],
  top_categories: [
    { category: "Rent", basket: "MANDATORY_REGULAR", total_eur: 890.0 },
    { category: "Groceries", basket: "MANDATORY_REGULAR", total_eur: 412.0 },
    { category: "Restaurants & takeaway", basket: "EVERYDAY", total_eur: 186.4 },
    { category: "Car service", basket: "MANDATORY_IRREGULAR", total_eur: 249.0 },
    { category: "Taxis", basket: "EVERYDAY", total_eur: 98.5 },
  ],
};

const mockTx: Transaction[] = (
  [
    ["2026-10-01", "Rent", -890.0, "MANDATORY_REGULAR", "M0101", "6513"],
    ["2026-10-02", "Electricity", -48.9, "MANDATORY_REGULAR", "M0207", "4900"],
    ["2026-10-03", "Groceries", -47.1, "MANDATORY_REGULAR", "M0311", "5411"],
    ["2026-10-04", "Coffee", -4.6, "EVERYDAY", "M0420", "5814"],
    ["2026-10-05", "Takeaway", -23.9, "EVERYDAY", "M0433", "5812"],
    ["2026-10-07", "Mobile subscription", -19.9, "MANDATORY_REGULAR", "M0505", "4814"],
    ["2026-10-08", "Taxi", -31.2, "EVERYDAY", "M0612", "4121"],
    ["2026-10-09", "Groceries", -62.35, "MANDATORY_REGULAR", "M0311", "5411"],
    ["2026-10-11", "Car service", -249.0, "MANDATORY_IRREGULAR", "M0702", "7538"],
    ["2026-10-12", "Coffee", -5.2, "EVERYDAY", "M0420", "5814"],
    ["2026-10-14", "Pharmacy", -40.0, "MANDATORY_IRREGULAR", "M0811", "5912"],
    ["2026-10-15", "Home insurance", -21.5, "MANDATORY_REGULAR", "M0909", "6300"],
    ["2026-10-16", "Takeaway", -27.4, "EVERYDAY", "M0433", "5812"],
    ["2026-10-18", "Taxi", -24.8, "EVERYDAY", "M0612", "4121"],
    ["2026-10-20", "Streaming", -12.99, "MANDATORY_REGULAR", "M1003", "4899"],
    ["2026-10-22", "Kiosk snacks", -8.7, "EVERYDAY", "M1101", "5499"],
    ["2026-10-25", "Salary", 2850.0, "INCOME", "M0001", "0000"],
  ] as const
).map(([date, category, amount, basket, merchant, mcc], i) => ({
  tx_id: `${CUSTOMER_ID}-${1100 + i}`,
  customer_id: CUSTOMER_ID,
  bank_account_id: "ACC-MOCK-1",
  tx_date: date,
  tx_timestamp: `${date}T12:00:00`,
  category,
  tx_amount_eur: amount,
  balance_after_eur: 0,
  transaction_type: amount > 0 ? "CREDIT" : "CARD_PAYMENT",
  merchant_id: merchant,
  mcc_code: mcc,
  basket,
}));

const mockSafe: SafeToSpend = {
  amount_eur: 142.5,
  until_date: "2026-11-15",
  explanation_inputs: {
    balance_eur: 1342.18,
    upcoming_regular_bills_eur: 1098.9,
    irregular_buffer_eur: 100.78,
    days_left: 6,
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
  const src = `Oct 2026, all baskets`;
  if (m.includes("where") || m.includes("go")) {
    return {
      answer:
        "In October you spent €2,214.60. Most of it (63%) went to 🏠 Regular essentials, mainly rent (€890) and groceries (€412). ☕ Everyday spending was €537.20, with takeaway and taxis as the biggest items.",
      tool_calls: [{ name: "spending_summary", args: { month: MOCK_MONTH } }],
      figures: [
        fig("Total spending", 2214.6, "EUR", src),
        fig("🏠 Regular essentials", 1388.4, "EUR", "Oct 2026, MANDATORY_REGULAR"),
        fig("☕ Everyday spending", 537.2, "EUR", "Oct 2026, EVERYDAY"),
      ],
    };
  }
  if (m.includes("spender") || m.includes("kind")) {
    return {
      answer:
        "You're a steady planner with a few small leaks: your bills are regular and on time, but about a quarter of your spending is everyday stuff like takeaway, taxis and coffee. Those small buys added up to €537 last month.",
      tool_calls: [
        { name: "spending_summary", args: { month: MOCK_MONTH } },
        { name: "spender_profile", args: { months: 3 } },
      ],
      figures: [
        fig("Everyday share of spending", 24.3, "%", "Oct 2026, EVERYDAY"),
        fig("Everyday purchases", 31, "count", "Oct 2026, EVERYDAY"),
      ],
    };
  }
  if (m.includes("safe") || m.includes("week")) {
    return {
      answer:
        "You can safely spend about €142.50 until 15 Nov. That's your balance minus the bills still coming this month and a small buffer for surprises.",
      tool_calls: [{ name: "safe_to_spend", args: {} }],
      figures: [
        fig("Safe to spend", 142.5, "EUR", "Now → 15 Nov 2026"),
        fig("Upcoming regular bills", 1098.9, "EUR", "Nov 2026, MANDATORY_REGULAR"),
      ],
    };
  }
  if (m.includes("save")) {
    return {
      answer:
        "Your biggest lever is ☕ Everyday spending. Cutting takeaway by half would save about €93 a month, or €1,118 a year. Taxis are next: €98.50 last month.",
      tool_calls: [
        { name: "spending_summary", args: { month: MOCK_MONTH } },
        { name: "what_if", args: { category_or_item: "Restaurants & takeaway", change_pct: -50 } },
      ],
      figures: [
        fig("Saving per month", 93.2, "EUR", "What-if on Oct 2026 takeaway"),
        fig("Saving per year", 1118.4, "EUR", "What-if on Oct 2026 takeaway"),
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

const mock: typeof real = {
  summary: async () => (await wait(300), mockSummary),
  transactions: async (_id, opts = {}) => {
    await wait(250);
    const all = opts.basket ? mockTx.filter((t) => t.basket === opts.basket) : mockTx;
    const offset = opts.offset ?? 0;
    const limit = opts.limit ?? 50;
    return { items: all.slice(offset, offset + limit), total: all.length, limit, offset };
  },
  safeToSpend: async () => (await wait(200), mockSafe),
  chat: async (_id, message) => (await wait(900), { ...mockChat(message), model: "mock" }),
};

export const api = USE_MOCK ? mock : real;

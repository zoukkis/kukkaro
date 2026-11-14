import type { Basket, Figure } from "./api";

const eur = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" });
export const formatEur = (n: number) => eur.format(n);

export const formatFigure = (f: Figure) =>
  f.unit === "EUR" ? formatEur(f.value) : f.unit === "%" ? `${f.value}%` : String(f.value);

export const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

export const formatTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

export const formatMonth = (ym: string) =>
  new Date(`${ym}-01`).toLocaleDateString("en-GB", { month: "long", year: "numeric" });

// S-Bank's own basket labels (root AGENTS.md §1). Use these everywhere.
export const BASKET_INFO: Record<Basket, { emoji: string; label: string; hint: string }> = {
  MANDATORY_REGULAR: { emoji: "🏠", label: "Regular essentials", hint: "Rent, bills, groceries" },
  MANDATORY_IRREGULAR: { emoji: "🔧", label: "Unexpected necessities", hint: "Repairs, health, car" },
  EVERYDAY: { emoji: "☕", label: "Everyday spending", hint: "Coffee, takeaway, taxis" },
  INCOME: { emoji: "💶", label: "Income", hint: "" },
  TRANSFER: { emoji: "🔁", label: "Transfers", hint: "" },
};

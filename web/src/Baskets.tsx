import { useEffect, useState } from "react";
import {
  api,
  CUSTOMER_ID,
  type SafeToSpend,
  type SpendingBasket,
  type Summary,
  type TransactionPage,
} from "./api";
import { BASKET_INFO, formatDate, formatEur, formatMonth } from "./format";

export default function Baskets() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [safe, setSafe] = useState<SafeToSpend | null>(null);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState<SpendingBasket | null>(null);

  useEffect(() => {
    Promise.all([api.summary(CUSTOMER_ID), api.safeToSpend(CUSTOMER_ID)])
      .then(([s, t]) => {
        setSummary(s);
        setSafe(t);
      })
      .catch(() => setError(true));
  }, []);

  if (error) return <p className="status">Couldn't load your baskets. Is the backend running?</p>;
  if (!summary || !safe) return <p className="status">Loading…</p>;
  if (open) return <BasketTransactions basket={open} month={summary.month} onBack={() => setOpen(null)} />;

  return (
    <div className="baskets">
      <section className="safe-card">
        <span className="safe-label">Safe to spend until {formatDate(safe.until_date)}</span>
        <span className="safe-amount">{formatEur(safe.amount_eur)}</span>
        <span className="safe-note">After upcoming bills and a buffer for surprises</span>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>{formatMonth(summary.month)}</h2>
          <span className="muted">Spent {formatEur(summary.spending_eur)}</span>
        </div>
        <div className="stackbar" role="img" aria-label="Share of spending per basket">
          {summary.baskets.map((b) => (
            <span key={b.basket} className={`seg ${b.basket}`} style={{ width: `${b.share_pct}%` }} />
          ))}
        </div>
        <ul className="basket-list">
          {summary.baskets.map((b) => {
            const info = BASKET_INFO[b.basket];
            return (
              <li key={b.basket}>
                <button className="basket-row" onClick={() => setOpen(b.basket)}>
                  <span className={`dot ${b.basket}`} aria-hidden />
                  <span className="basket-name">
                    <strong>
                      {info.emoji} {info.label}
                    </strong>
                    <span className="muted">{info.hint}</span>
                  </span>
                  <span className="basket-amount">
                    <strong>{formatEur(b.total_eur)}</strong>
                    <span className="muted">{b.share_pct}%</span>
                  </span>
                  <span className="chev" aria-hidden>›</span>
                </button>
              </li>
            );
          })}
        </ul>
        <p className="source">Source: your transactions, {formatMonth(summary.month)}</p>
      </section>

      <section className="card">
        <h2>Top categories</h2>
        <ul className="cat-list">
          {summary.top_categories.map((c) => (
            <li key={c.category}>
              <span>
                {BASKET_INFO[c.basket].emoji} {c.category}
              </span>
              <strong>{formatEur(c.total_eur)}</strong>
            </li>
          ))}
        </ul>
        <div className="income-row">
          <span>Income</span>
          <strong>{formatEur(summary.income_eur)}</strong>
        </div>
        <div className="income-row">
          <span>Balance now</span>
          <strong>{formatEur(summary.balance_eur)}</strong>
        </div>
      </section>
    </div>
  );
}

function BasketTransactions({
  basket,
  month,
  onBack,
}: {
  basket: SpendingBasket;
  month: string;
  onBack: () => void;
}) {
  const [page, setPage] = useState<TransactionPage | null>(null);
  const [error, setError] = useState(false);
  const info = BASKET_INFO[basket];

  useEffect(() => {
    api
      .transactions(CUSTOMER_ID, { basket, limit: 50 })
      .then(setPage)
      .catch(() => setError(true));
  }, [basket]);

  return (
    <div className="baskets">
      <button className="back" onClick={onBack}>
        ‹ Baskets
      </button>
      <h1 className="basket-title">
        {info.emoji} {info.label}
      </h1>
      <p className="muted">{formatMonth(month)} · {info.hint}</p>
      {error && <p className="status">Couldn't load transactions.</p>}
      {!page && !error && <p className="status">Loading…</p>}
      {page && (
        <ul className="tx-list card">
          {page.items.length === 0 && <li className="muted">No transactions in this basket.</li>}
          {page.items.map((t) => (
            <li key={t.tx_id}>
              <span className="tx-main">
                <strong>{t.category}</strong>
                <span className="muted">{formatDate(t.tx_date)}</span>
              </span>
              <strong className={t.tx_amount_eur < 0 ? "out" : "in"}>{formatEur(t.tx_amount_eur)}</strong>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

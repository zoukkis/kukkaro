import { useEffect, useState } from "react";
import {
  api,
  CUSTOMER_ID,
  type Receipt,
  type SafeToSpend,
  type SpendingBasket,
  type Summary,
  type Transaction,
  type TransactionPage,
} from "./api";
import { BASKET_INFO, formatDate, formatEur, formatMonth, formatTime } from "./format";

export default function Baskets() {
  const [withReceipts, setWithReceipts] = useState(false);
  const [summaries, setSummaries] = useState<{ card?: Summary; receipts?: Summary }>({});
  const [safe, setSafe] = useState<SafeToSpend | null>(null);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState<SpendingBasket | null>(null);

  useEffect(() => {
    Promise.all([api.summary(CUSTOMER_ID), api.safeToSpend(CUSTOMER_ID)])
      .then(([s, t]) => {
        setSummaries((p) => ({ ...p, card: s }));
        setSafe(t);
        // Pre-fetch the receipts view for the same month so the toggle flips instantly
        return api.summary(CUSTOMER_ID, s.month, true).then((r) => setSummaries((p) => ({ ...p, receipts: r })));
      })
      .catch(() => setError(true));
  }, []);

  const summary = withReceipts ? summaries.receipts : summaries.card;
  if (error) return <p className="status">Couldn't load your baskets. Is the backend running?</p>;
  if (!summaries.card || !safe) return <p className="status">Loading…</p>;
  if (open) return <BasketTransactions basket={open} month={summaries.card.month} onBack={() => setOpen(null)} />;

  const split = summary?.receipts;
  const groceries = summaries.card.top_categories.find((c) => c.category === "Groceries");

  return (
    <div className="baskets">
      <section className="safe-card">
        <span className="safe-label">Safe to spend this week</span>
        <span className="safe-amount">{formatEur(safe.this_week_eur)}</span>
        <span className="safe-note">
          {formatEur(safe.amount_eur)} until payday {formatDate(safe.until_date)} · {formatEur(safe.per_day_eur)}/day
        </span>
        <span className="safe-note">After the regular essentials still expected before payday</span>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>{formatMonth(summaries.card.month)}</h2>
          <span className="muted">Spent {formatEur(summaries.card.spending_eur)}</span>
        </div>

        <div className="segmented" role="group" aria-label="Receipt view">
          <button aria-pressed={!withReceipts} onClick={() => setWithReceipts(false)}>
            Without receipts
          </button>
          <button aria-pressed={withReceipts} onClick={() => setWithReceipts(true)} disabled={!summaries.receipts}>
            🧾 With receipts
          </button>
        </div>

        {!summary ? (
          <p className="status">Loading…</p>
        ) : (
          <>
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

            {withReceipts && split ? (
              <div className="receipt-insight">
                <span className="badge">Synthetic example data</span>
                <p>
                  Your {formatEur(split.grocery_total_eur)} of grocery payments, split by what was on the receipts:
                </p>
                <ul className="split-list">
                  {split.split.map((p) => (
                    <li key={p.basket}>
                      <span>
                        <span className={`dot ${p.basket}`} aria-hidden /> {BASKET_INFO[p.basket].emoji} {p.label}
                      </span>
                      <strong>{formatEur(p.total_eur)}</strong>
                    </li>
                  ))}
                </ul>
                {split.top_leak_items.length > 0 && (
                  <>
                    <h3>Top everyday items in your grocery trips</h3>
                    <ul className="leak-list">
                      {split.top_leak_items.map((it) => (
                        <li key={it.name}>
                          <span>
                            {it.name} <span className="muted">×{it.qty}</span>
                          </span>
                          <strong>{formatEur(it.total_eur)}</strong>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            ) : (
              groceries && (
                <p className="receipt-hint">
                  Card data counts all {formatEur(groceries.total_eur)} of groceries as 🏠 Regular essentials. Switch on{" "}
                  <strong>With receipts</strong> to see what was really in the basket.
                </p>
              )
            )}
            <p className="source">
              Source: your transactions, {formatMonth(summary.month)}
              {withReceipts && " + synthetic receipt lines"}
            </p>
          </>
        )}
      </section>

      <section className="card">
        <h2>Top categories</h2>
        <ul className="cat-list">
          {summaries.card.top_categories.map((c) => (
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
          <strong>{formatEur(summaries.card.income_eur)}</strong>
        </div>
        <div className="income-row">
          <span>Balance now</span>
          <strong>{formatEur(summaries.card.balance_eur)}</strong>
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
  const [receiptTx, setReceiptTx] = useState<Transaction | null>(null);
  const info = BASKET_INFO[basket];

  useEffect(() => {
    api
      .transactions(CUSTOMER_ID, { basket, month, limit: 50 })
      .then(setPage)
      .catch(() => setError(true));
  }, [basket, month]);

  if (receiptTx) return <ReceiptView tx={receiptTx} onBack={() => setReceiptTx(null)} backLabel={info.label} />;

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
          {page.items.map((t) => {
            const body = (
              <>
                <span className="tx-main">
                  <strong>{t.subcategory ?? t.category}</strong>
                  <span className="muted">
                    {formatDate(t.tx_date)}
                    {t.category === "Groceries" && " · 🧾 receipt"}
                  </span>
                </span>
                <strong className={t.tx_amount_eur < 0 ? "out" : "in"}>{formatEur(t.tx_amount_eur)}</strong>
              </>
            );
            return (
              <li key={t.tx_id}>
                {t.category === "Groceries" ? (
                  <button className="tx-button" onClick={() => setReceiptTx(t)}>
                    {body}
                    <span className="chev" aria-hidden>›</span>
                  </button>
                ) : (
                  body
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function ReceiptView({ tx, onBack, backLabel }: { tx: Transaction; onBack: () => void; backLabel: string }) {
  const [receipt, setReceipt] = useState<Receipt | null | undefined>(undefined);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.receipt(tx.tx_id).then(setReceipt).catch(() => setError(true));
  }, [tx.tx_id]);

  return (
    <div className="baskets">
      <button className="back" onClick={onBack}>
        ‹ {backLabel}
      </button>
      {error && <p className="status">Couldn't load the receipt.</p>}
      {receipt === undefined && !error && <p className="status">Loading…</p>}
      {receipt === null && <p className="status">No receipt for this payment.</p>}
      {receipt && (
        <section className="receipt">
          <span className="badge">Synthetic example receipt</span>
          <h1 className="receipt-store">{receipt.store}</h1>
          <p className="muted">
            {formatDate(receipt.timestamp)} {formatTime(receipt.timestamp)}
            {receipt.channel === "online_order" && " · online order"}
          </p>
          <ul className="receipt-items">
            {receipt.items.map((it, i) => (
              <li key={i} className={it.basket === "EVERYDAY" ? "leak" : ""}>
                <span className={`dot ${it.basket}`} aria-hidden />
                <span className="item-name">
                  {it.name}
                  {it.store_brand && <span className="tag">store brand</span>}
                  <span className="muted">
                    {it.qty} × {formatEur(it.unit_price_eur)} · {BASKET_INFO[it.basket].emoji} {BASKET_INFO[it.basket].label}
                  </span>
                </span>
                <strong>{formatEur(it.line_total_eur)}</strong>
              </li>
            ))}
            {!!receipt.delivery_fee_eur && (
              <li>
                <span className="dot" aria-hidden />
                <span className="item-name">Delivery fee</span>
                <strong>{formatEur(receipt.delivery_fee_eur)}</strong>
              </li>
            )}
          </ul>
          <div className="receipt-total">
            <span>Total</span>
            <strong>{formatEur(receipt.total_eur)}</strong>
          </div>
          <p className="source">Matches your card payment of {formatEur(-tx.tx_amount_eur)}. Highlighted lines are ☕ Everyday spending.</p>
        </section>
      )}
    </div>
  );
}

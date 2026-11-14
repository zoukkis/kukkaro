import { useEffect, useState, type CSSProperties } from "react";
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
import { IconArrow, IconBack, IconReceipt } from "./Icons";

const stagger = (i: number) => ({ "--i": i }) as CSSProperties;

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
  if (error) return <p className="status">Couldn't load your baskets. Please try again in a moment.</p>;
  if (!summaries.card || !safe) return <BasketsSkeleton />;
  if (open) return <BasketTransactions basket={open} month={summaries.card.month} onBack={() => setOpen(null)} />;

  const split = summary?.receipts;
  const groceries = summaries.card.top_categories.find((c) => c.category === "Groceries");
  const hiddenEveryday = split?.split.find((p) => p.basket === "EVERYDAY")?.total_eur;

  return (
    <div className="page">
      <section className="hero-card rise" style={stagger(0)}>
        <span className="eyebrow light">Safe to spend this week</span>
        <span className="hero-amount">{formatEur(safe.this_week_eur)}</span>
        <div className="hero-facts">
          <span>
            <strong>{formatEur(safe.per_day_eur)}</strong> a day
          </span>
          <span>
            <strong>{formatEur(safe.amount_eur)}</strong> until payday {formatDate(safe.until_date)}
          </span>
        </div>
        <span className="hero-note">After the regular essentials still due before payday.</span>
      </section>

      <section className="card rise" style={stagger(1)}>
        <div className="card-head">
          <div>
            <p className="eyebrow">Your three baskets</p>
            <h2 className="card-title">{formatMonth(summaries.card.month)}</h2>
          </div>
          <div className="spent">
            <span className="muted">Spent</span>
            <strong className="num">{formatEur(summaries.card.spending_eur)}</strong>
          </div>
        </div>

        <div className="segmented" role="group" aria-label="Receipt view">
          <button aria-pressed={!withReceipts} onClick={() => setWithReceipts(false)}>
            Card data
          </button>
          <button aria-pressed={withReceipts} onClick={() => setWithReceipts(true)} disabled={!summaries.receipts}>
            <IconReceipt size={16} /> With receipts
          </button>
        </div>

        {!summary ? (
          <p className="status">Loading…</p>
        ) : (
          <>
            <div className="stackbar" role="img" aria-label="Share of spending per basket">
              {summary.baskets.map((b) => (
                <span key={b.basket} className={`seg ${b.basket}`} style={{ flexGrow: b.share_pct }} />
              ))}
            </div>
            <ul className="basket-list">
              {summary.baskets.map((b) => {
                const info = BASKET_INFO[b.basket];
                return (
                  <li key={b.basket}>
                    <button className="basket-row" onClick={() => setOpen(b.basket)}>
                      <span className={`swatch ${b.basket}`} aria-hidden>{info.emoji}</span>
                      <span className="basket-name">
                        <strong>{info.label}</strong>
                        <span className="muted">{info.hint}</span>
                      </span>
                      <span className="basket-amount">
                        <strong className="num">{formatEur(b.total_eur)}</strong>
                        <span className="muted num">{b.share_pct}%</span>
                      </span>
                      <span className="chev" aria-hidden><IconArrow size={16} /></span>
                    </button>
                  </li>
                );
              })}
            </ul>

            {withReceipts && split ? (
              <div className="receipt-paper reveal-in">
                <span className="badge">Synthetic example data</span>
                {hiddenEveryday != null && (
                  <p className="reveal">
                    <span className="reveal-amount">{formatEur(hiddenEveryday)}</span> of everyday spending was hiding
                    inside your {formatEur(split.grocery_total_eur)} of grocery payments.
                  </p>
                )}
                <ul className="split-list">
                  {split.split.map((p) => (
                    <li key={p.basket}>
                      <span>
                        <span className={`dot ${p.basket}`} aria-hidden /> {p.label}
                      </span>
                      <strong className="num">{formatEur(p.total_eur)}</strong>
                    </li>
                  ))}
                </ul>
                {split.top_leak_items.length > 0 && (
                  <>
                    <h3 className="paper-title">What slipped through</h3>
                    <ul className="leak-list">
                      {split.top_leak_items.map((it) => (
                        <li key={it.name}>
                          <span>
                            {it.name} <span className="qty">×{it.qty}</span>
                          </span>
                          <strong className="num">{formatEur(it.total_eur)}</strong>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            ) : (
              groceries && (
                <p className="receipt-hint">
                  Card data counts all <strong>{formatEur(groceries.total_eur)}</strong> of groceries as regular
                  essentials. Switch to <strong>With receipts</strong> to see what was really in the basket.
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

      <section className="card rise" style={stagger(2)}>
        <p className="eyebrow">Where it went</p>
        <h2 className="card-title">Top categories</h2>
        <ul className="cat-list">
          {summaries.card.top_categories.map((c) => (
            <li key={c.category}>
              <span>
                <span className={`dot ${c.basket}`} aria-hidden /> {c.category}
              </span>
              <strong className="num">{formatEur(c.total_eur)}</strong>
            </li>
          ))}
        </ul>
        <div className="totals">
          <div>
            <span className="muted">Income</span>
            <strong className="num">{formatEur(summaries.card.income_eur)}</strong>
          </div>
          <div>
            <span className="muted">Balance now</span>
            <strong className="num">{formatEur(summaries.card.balance_eur)}</strong>
          </div>
        </div>
      </section>
    </div>
  );
}

function BasketsSkeleton() {
  return (
    <div className="page" aria-busy="true" aria-label="Loading your baskets">
      <div className="skeleton hero" />
      <div className="skeleton tall" />
      <div className="skeleton" />
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
    <div className="page">
      <button className="back" onClick={onBack}>
        <IconBack /> Baskets
      </button>
      <div className="page-head">
        <span className={`swatch big ${basket}`} aria-hidden>{info.emoji}</span>
        <div>
          <h1 className="page-title">{info.label}</h1>
          <p className="muted">
            {formatMonth(month)} · {info.hint}
          </p>
        </div>
      </div>
      {error && <p className="status">Couldn't load transactions.</p>}
      {!page && !error && <div className="skeleton tall" />}
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
                    {t.category === "Groceries" && (
                      <span className="has-receipt">
                        <IconReceipt size={14} /> receipt
                      </span>
                    )}
                  </span>
                </span>
                <strong className={`num ${t.tx_amount_eur < 0 ? "out" : "in"}`}>{formatEur(t.tx_amount_eur)}</strong>
              </>
            );
            return (
              <li key={t.tx_id}>
                {t.category === "Groceries" ? (
                  <button className="tx-button" onClick={() => setReceiptTx(t)}>
                    {body}
                    <span className="chev" aria-hidden><IconArrow size={16} /></span>
                  </button>
                ) : (
                  <div className="tx-row">{body}</div>
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
    <div className="page">
      <button className="back" onClick={onBack}>
        <IconBack /> {backLabel}
      </button>
      {error && <p className="status">Couldn't load the receipt.</p>}
      {receipt === undefined && !error && <div className="skeleton tall" />}
      {receipt === null && <p className="status">No receipt for this payment.</p>}
      {receipt && (
        <section className="receipt reveal-in">
          <span className="badge">Synthetic example receipt</span>
          <h1 className="receipt-store">{receipt.store}</h1>
          <p className="receipt-when">
            {formatDate(receipt.timestamp)} · {formatTime(receipt.timestamp)}
            {receipt.channel === "online_order" && " · online order"}
          </p>
          <ul className="receipt-items">
            {receipt.items.map((it, i) => (
              <li key={i} className={it.basket === "EVERYDAY" ? "leak" : ""}>
                <span className={`dot ${it.basket}`} aria-hidden />
                <span className="item-name">
                  <span>
                    {it.name}
                    {it.store_brand && <span className="tag">store brand</span>}
                  </span>
                  <span className="item-sub">
                    {it.qty} × {formatEur(it.unit_price_eur)} · {BASKET_INFO[it.basket].label}
                  </span>
                </span>
                <strong className="num">{formatEur(it.line_total_eur)}</strong>
              </li>
            ))}
            {!!receipt.delivery_fee_eur && (
              <li>
                <span className="dot" aria-hidden />
                <span className="item-name">Delivery fee</span>
                <strong className="num">{formatEur(receipt.delivery_fee_eur)}</strong>
              </li>
            )}
          </ul>
          <div className="receipt-total">
            <span>Total</span>
            <strong className="num">{formatEur(receipt.total_eur)}</strong>
          </div>
          <p className="source">
            Matches your card payment of {formatEur(-tx.tx_amount_eur)}. Highlighted lines are everyday spending.
          </p>
        </section>
      )}
    </div>
  );
}

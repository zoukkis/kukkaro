// Bank-style Home: Kukkaro as a feature inside a banking app. Account card, one Kukkaro insight,
// recent transactions (grocery rows open the synthetic receipt). Every number comes from the API:
// the balance is the latest transaction's balance_after_eur, the insight is the receipts split.
import { useEffect, useState } from "react";
import { api, CUSTOMER_ID, type Summary, type Transaction, type Upcoming } from "./api";
import { ReceiptView } from "./Baskets";
import { formatDate, formatEur, formatMonth } from "./format";
import { IconArrow, IconBell, IconReceipt, IconShield, IconSpark } from "./Icons";

const RECENT = 8;

// "ACC002979" -> "•••• 2979": only the last four characters are ever shown.
const maskAccount = (id: string) => `•••• ${id.slice(-4)}`;

// Bills have no merchant in the data: say "utility bills", never "electricity".
const BILL_NAMES: Record<string, string> = { Housing: "Rent / housing", Utilities: "Utility bills" };
const billName = (category: string) => BILL_NAMES[category] ?? category;

export default function Home({ onOpenBaskets, onOpenHelp }: { onOpenBaskets: () => void; onOpenHelp: () => void }) {
  const [tx, setTx] = useState<Transaction[] | null>(null);
  const [split, setSplit] = useState<Summary | null>(null);
  const [error, setError] = useState(false);
  const [receiptTx, setReceiptTx] = useState<Transaction | null>(null);
  const [upcoming, setUpcoming] = useState<Upcoming | null>(null);

  useEffect(() => {
    api.transactions(CUSTOMER_ID, { limit: RECENT }).then((p) => setTx(p.items)).catch(() => setError(true));
    api.summary(CUSTOMER_ID, undefined, true).then(setSplit).catch(() => setSplit(null));
    api.upcoming(CUSTOMER_ID).then(setUpcoming).catch(() => setUpcoming(null));
  }, []);

  if (receiptTx) return <ReceiptView tx={receiptTx} onBack={() => setReceiptTx(null)} backLabel="Home" />;

  const latest = tx?.[0];
  const hiddenEveryday = split?.receipts?.split.find((p) => p.basket === "EVERYDAY")?.total_eur;

  return (
    <div className="page home">
      <h1 className="home-greeting">Good to see you</h1>

      {error && <p className="status">Couldn't load your account. Please try again in a moment.</p>}

      {!tx && !error && <div className="skeleton account-skeleton" />}
      {latest && (
        <section className="account-card reveal-in" aria-label="Current account">
          <div className="account-top">
            <span className="account-name">Current account</span>
            <span className="account-number mono">{maskAccount(latest.bank_account_id)}</span>
          </div>
          <span className="account-label">Balance</span>
          <span className="account-balance num">{formatEur(latest.balance_after_eur)}</span>
          <span className="account-asof">After the latest transaction, {formatDate(latest.tx_date)}</span>
        </section>
      )}

      {upcoming && (upcoming.items.length > 0 || upcoming.other_essentials_eur > 0) && (
        <section className="upcoming card reveal-in" aria-label="Coming up before payday">
          <h2 className="upcoming-title">
            <IconBell size={18} /> Coming up before payday · {formatDate(upcoming.until_date)}
          </h2>
          <ul className="upcoming-list">
            {upcoming.items.map((i) => (
              <li key={i.name}>
                <span className="tx-main">
                  <strong>{billName(i.name)}</strong>
                  <span className="muted">
                    {i.expected_around ? `around ${formatDate(i.expected_around)}` : "before payday"} · expected
                  </span>
                  {i.rising && i.change_pct != null && (
                    <button className="rising" onClick={onOpenHelp}>
                      Up {Math.round(i.change_pct)}% vs your usual month · ask why <IconArrow size={13} />
                    </button>
                  )}
                </span>
                <strong className="num">~{formatEur(i.expected_eur)}</strong>
              </li>
            ))}
            {upcoming.other_essentials_eur > 0 && (
              <li>
                <span className="tx-main">
                  <strong>Other regular essentials</strong>
                  <span className="muted">{upcoming.other_essentials.join(", ")}</span>
                </span>
                <strong className="num">~{formatEur(upcoming.other_essentials_eur)}</strong>
              </li>
            )}
          </ul>
          <p className="upcoming-left">
            Left to spend after these: <strong className="num">{formatEur(upcoming.left_after_eur)}</strong>
            <span className="muted"> · {formatEur(upcoming.this_week_eur)} this week</span>
          </p>
          <p className="upcoming-note">Estimated from your last 3 months. In S-mobiili, your e-invoices would make this exact.</p>
        </section>
      )}

      {hiddenEveryday != null && split && (
        <section className="insight-card reveal-in" aria-label="Kukkaro insight">
          <span className="insight-icon" aria-hidden><IconSpark /></span>
          <div className="insight-body">
            <p className="insight-kicker">Kukkaro insight · {formatMonth(split.month)}</p>
            <p className="insight-text">
              Kukkaro found <strong className="num">{formatEur(hiddenEveryday)}</strong> of everyday spending in your
              groceries.
            </p>
            <button className="link-button" onClick={onOpenBaskets}>
              See what was in your baskets <IconArrow size={14} />
            </button>
          </div>
        </section>
      )}

      {tx && (
        <section className="recent" aria-label="Recent transactions">
          <h2 className="section-heading">Recent transactions</h2>
          <ul className="tx-list card">
            {tx.map((t) => {
              const grocery = t.category === "Groceries";
              const body = (
                <>
                  <span className="tx-main">
                    <strong>{t.subcategory ?? t.category}</strong>
                    <span className="muted">
                      {formatDate(t.tx_date)}
                      {t.subcategory && t.subcategory !== t.category && ` · ${t.category}`}
                      {grocery && (
                        <span className="has-receipt">
                          <IconReceipt size={14} /> receipt
                        </span>
                      )}
                    </span>
                  </span>
                  <strong className={`num ${t.tx_amount_eur < 0 ? "out" : "in"}`}>
                    {t.tx_amount_eur > 0 ? "+" : ""}
                    {formatEur(t.tx_amount_eur)}
                  </strong>
                </>
              );
              return (
                <li key={t.tx_id}>
                  {grocery ? (
                    <button className="tx-button" onClick={() => setReceiptTx(t)} aria-label={`Receipt for ${formatDate(t.tx_date)}`}>
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
        </section>
      )}

      <p className="privacy-line">
        <IconShield size={14} /> Your data stays private: Kukkaro reads it only to answer you, and nothing personal is
        sent to web searches.
      </p>
    </div>
  );
}

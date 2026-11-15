// Bank-style Home: Kukkaro as a feature inside a banking app. Account card, one Kukkaro insight,
// recent transactions (grocery rows open the synthetic receipt). Every number comes from the API:
// the balance is the latest transaction's balance_after_eur, the insight is the receipts split.
import { useEffect, useState } from "react";
import { api, CUSTOMER_ID, type Summary, type Transaction } from "./api";
import { ReceiptView } from "./Baskets";
import { formatDate, formatEur, formatMonth } from "./format";
import { IconArrow, IconReceipt, IconShield, IconSpark } from "./Icons";

const RECENT = 8;
const SHOWN = 4; // one phone screen: the rest behind "See all"

// "ACC002979" -> "•••• 2979": only the last four characters are ever shown.
const maskAccount = (id: string) => `•••• ${id.slice(-4)}`;

export default function Home({ onOpenBaskets }: { onOpenBaskets: () => void }) {
  const [tx, setTx] = useState<Transaction[] | null>(null);
  const [split, setSplit] = useState<Summary | null>(null);
  const [error, setError] = useState(false);
  const [receiptTx, setReceiptTx] = useState<Transaction | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    api.transactions(CUSTOMER_ID, { limit: RECENT }).then((p) => setTx(p.items)).catch(() => setError(true));
    api.summary(CUSTOMER_ID, undefined, true).then(setSplit).catch(() => setSplit(null));
  }, []);

  if (receiptTx) return <ReceiptView tx={receiptTx} onBack={() => setReceiptTx(null)} backLabel="Home" />;

  const latest = tx?.[0];
  const hiddenEveryday = split?.receipts?.split.find((p) => p.basket === "EVERYDAY")?.total_eur;

  return (
    <div className="page home">
      <h1 className="sr-only">Home</h1>

      {error && <p className="status">Couldn't load your account. Please try again in a moment.</p>}

      {!tx && !error && <div className="skeleton account-skeleton" />}
      {latest && (
        <section className="account-card reveal-in" aria-label="Current account">
          <div className="account-top">
            <span className="account-name">Current account</span>
            <span className="account-number mono">{maskAccount(latest.bank_account_id)}</span>
          </div>
          <span className="account-balance num">{formatEur(latest.balance_after_eur)}</span>
          <span className="account-asof">Balance after the latest transaction, {formatDate(latest.tx_date)}</span>
        </section>
      )}

      {hiddenEveryday != null && split && (
        <section className="insight-card reveal-in" aria-label="Kukkaro insight">
          <span className="insight-icon" aria-hidden><IconSpark /></span>
          <div className="insight-body">
            <p className="insight-text">
              <strong className="num">{formatEur(hiddenEveryday)}</strong> of everyday spending hid in your groceries
              in {formatMonth(split.month)}.
            </p>
            <button className="link-button" onClick={onOpenBaskets}>
              See your baskets <IconArrow size={14} />
            </button>
          </div>
        </section>
      )}

      {tx && (
        <section className="recent" aria-label="Recent transactions">
          <h2 className="section-heading">Recent transactions</h2>
          <ul className="tx-list card">
            {tx.slice(0, showAll ? undefined : SHOWN).map((t) => {
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
          {tx.length > SHOWN && (
            <button className="link-button see-all" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "Show fewer" : `See all ${tx.length}`}
            </button>
          )}
        </section>
      )}

      <p className="privacy-line">
        <IconShield size={14} /> Private: nothing personal goes to web searches.
      </p>
    </div>
  );
}

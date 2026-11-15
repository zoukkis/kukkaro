import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { api, CUSTOMER_ID, type BillSuggestion, type ButlerResponse, type ButlerSource, type Product, type SwapsResponse, type Watch } from "./api";
import { useOrderBasket } from "./basket";
import { formatDate, formatEur, formatMonth } from "./format";
import { IconBell, IconClose, IconCopy, IconExternal, IconMail, IconReceipt, IconSend, IconSpark, IconTrend } from "./Icons";

// The three demo tasks from backend/kukkaro/butler/AGENTS.md.
const EXAMPLES = [
  "Am I possibly eligible for Kela housing allowance?",
  "My rent went up. Is that allowed, and what can I do?",
  "Am I overpaying for electricity?",
];

// What the Butler really does, in order (backend/kukkaro/butler/agent.py).
const STAGES = ["Reading your bills and income", "Searching official sources and current prices", "Checking every number", "Preparing a draft for you"];

// Keep the Help screen short: long answers fold after ~7 lines, next steps after 3.
const ANSWER_CLAMP_CHARS = 380;
const STEPS_SHOWN = 3;

const stagger = (i: number) => ({ "--i": i }) as CSSProperties;

export default function Butler() {
  const [input, setInput] = useState("");
  const [task, setTask] = useState<string | null>(null);
  const [res, setRes] = useState<ButlerResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const [stage, setStage] = useState(0);
  const [cards, setCards] = useState<BillSuggestion[]>([]);
  const [watches, setWatches] = useState<Watch[]>([]);

  useEffect(() => {
    api.suggestions(CUSTOMER_ID).then((r) => setCards(r.suggestions)).catch(() => setCards([]));
    api.watchlist(CUSTOMER_ID).then((r) => setWatches(r.items)).catch(() => setWatches([]));
  }, []);

  useEffect(() => {
    if (!busy) return;
    setStage(0);
    const t = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 2600);
    return () => clearInterval(t);
  }, [busy]);

  // A new answer scrolls into view, so nobody has to hunt for it.
  const answerRef = useRef<HTMLElement | null>(null);
  const [more, setMore] = useState(false);
  const [allSteps, setAllSteps] = useState(false);
  useEffect(() => {
    setMore(false);
    setAllSteps(false);
    if (res) answerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [res]);
  const long = (res?.answer.length ?? 0) > ANSWER_CLAMP_CHARS;

  async function run(text: string) {
    const t = text.trim();
    if (t.length < 3 || busy) return;
    setTask(t);
    setRes(null);
    setError(false);
    setBusy(true);
    try {
      setRes(await api.butler(CUSTOMER_ID, t));
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page butler">
      <div className="welcome">
        <p className="eyebrow mono rise" style={stagger(0)}>
          Kukkaro Butler <span className="powered">· search by Exa</span>
        </p>
        <h1 className="display butler-title rise" style={stagger(1)}>
          Money you might be <em>missing.</em>
        </h1>
      </div>

      <form
        className="composer butler-input rise"
        style={stagger(4)}
        onSubmit={(e) => {
          e.preventDefault();
          run(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Benefits, prices, your rights…"
          aria-label="Your task for the Butler"
        />
        <button type="submit" className="send" disabled={busy || input.trim().length < 3} aria-label="Ask">
          <IconSend />
        </button>
      </form>
      <div className="chips chips-row rise" style={stagger(3)} aria-label="Example tasks">
        {EXAMPLES.map((s) => (
          <button key={s} className="chip" disabled={busy} onClick={() => { setInput(s); run(s); }}>
            {s}
          </button>
        ))}
      </div>

      {busy && (
        <section className="card exa progress" aria-live="polite">
          <p className="butler-task"><span className="q" aria-hidden>search</span>{task}</p>
          <ol className="stages">
            {STAGES.map((s, i) => (
              <li key={s} className={i < stage ? "done" : i === stage ? "now" : ""}>
                <span className="stage-n" aria-hidden>{String(i + 1).padStart(2, "0")}</span> {s}
              </li>
            ))}
          </ol>
        </section>
      )}
      {error && <p className="status">Couldn't reach the Butler. Please try again in a moment.</p>}

      {res && !busy && (
        <section ref={answerRef} className="card exa butler-answer reveal-in" aria-live="polite">
          <p className="butler-task"><span className="q" aria-hidden>search</span>{task}</p>
          <p className={`answer${long && !more ? " clamped" : ""}`}>{withCitations(res.answer, res.sources)}</p>
          {long && (
            <button className="link-button read-more" onClick={() => setMore((m) => !m)}>
              {more ? "Show less" : "Read more"}
            </button>
          )}

          {res.products && res.products.length > 0 && <ProductCards products={res.products} />}

          {res.next_steps.length > 0 && (
            <>
              <h3 className="section-title">Next steps</h3>
              <ol className="steps">
                {res.next_steps.slice(0, allSteps ? undefined : STEPS_SHOWN).map((s, i) => (
                  <li key={i}>
                    <label>
                      <input type="checkbox" /> <span>{withCitations(s, res.sources)}</span>
                    </label>
                  </li>
                ))}
              </ol>
              {res.next_steps.length > STEPS_SHOWN && !allSteps && (
                <button className="link-button read-more" onClick={() => setAllSteps(true)}>
                  Show all {res.next_steps.length} steps
                </button>
              )}
            </>
          )}

          {res.draft && <Draft draft={res.draft} />}

          {task && res.research?.question_sent && (
            <WatchButton task={task} watching={watches.some((w) => w.task === task)}
              onWatched={(w) => setWatches((ws) => [w, ...ws.filter((x) => x.id !== w.id)])} />
          )}

          {res.sources.length > 0 && (
            <details className="sources-fold" id="answer-sources">
              <summary className="section-title">
                {res.sources.length} {res.sources.length === 1 ? "source" : "sources"}{" "}
                <span className="powered">· found with Exa</span>
              </summary>
              <ol className="sources">
                {res.sources.map((s) => (
                  <li key={s.n} id={`src-${s.n}`} className={s.cited ? "cited" : ""}>
                    <span className="src-n">{s.n}</span>
                    <a href={s.url} target="_blank" rel="noreferrer">
                      <span className="src-title">{s.title || s.url}</span>
                      <span className="src-meta">
                        {new URL(s.url).hostname.replace(/^www\./, "")}
                        {s.published_date && ` · ${s.published_date.slice(0, 10)}`}
                        <IconExternal size={13} />
                      </span>
                    </a>
                  </li>
                ))}
              </ol>
            </details>
          )}
          <p className="source">
            Kukkaro is a coach, not a licensed advisor. You decide what to do; check the official source before acting.
            {res.model && ` Answered by ${res.model}${res.cached ? " (saved answer)" : ""}.`}
          </p>
        </section>
      )}

      {watches.length > 0 && (
        <Watching watches={watches} onChange={(w) => setWatches((ws) => ws.map((x) => (x.id === w.id ? w : x)))}
          onRemove={(id) => setWatches((ws) => ws.filter((x) => x.id !== id))} />
      )}

      {cards.map((c) => (
        <section key={c.category} className="nudge-row rise">
          <span className="nudge-icon"><IconTrend /></span>
          <div className="nudge-text">
            <h2 className="nudge-title">
              {c.title} <span className="up num">+{c.change_pct}%</span>
            </h2>
            <p className="muted small">
              {formatMonth(c.latest_month)}: <strong className="num">{formatEur(c.latest_month_eur)}</strong> vs{" "}
              <strong className="num">{formatEur(c.typical_monthly_eur)}</strong> typical
            </p>
          </div>
          <button className="button primary small-button" disabled={busy} onClick={() => { setInput(c.task); run(c.task); }}>
            <IconSpark size={15} /> Why?
          </button>
        </section>
      ))}

      <Swaps />
    </div>
  );
}

// "Watch this": Kukkaro re-checks the question's sources with Exa and tells you only when they change.
function WatchButton({ task, watching, onWatched }: { task: string; watching: boolean; onWatched: (w: Watch) => void }) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  if (watching)
    return (
      <p className="watch-saved" role="status">
        <IconBell size={16} /> Watching · we'll tell you when the sources change
      </p>
    );
  async function save() {
    setBusy(true);
    setFailed(false);
    try {
      onWatched(await api.watch(CUSTOMER_ID, task));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="watch-row">
      <button className="button ghost watch-button" disabled={busy} onClick={save}>
        <IconBell size={16} /> {busy ? "Saving…" : "Watch this"}
      </button>
      {failed && <span className="muted">Couldn't save it. Please try again.</span>}
    </div>
  );
}

// "Watching": saved questions, re-checked on demand (and by a nightly job). Every change, count and date
// comes from the API; the UI only shows it.
function Watching({ watches, onChange, onRemove }: {
  watches: Watch[];
  onChange: (w: Watch) => void;
  onRemove: (id: string) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set()); // checked in this visit: open the change card

  async function check(w: Watch) {
    setBusy(w.id);
    setFailed(null);
    try {
      const r = await api.checkWatch(w.id);
      setFresh((s) => new Set(s).add(w.id));
      onChange({ ...w, last_result: r, last_checked_at: r.error && !r.changed ? w.last_checked_at : r.checked_at });
    } catch {
      setFailed(w.id);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="watching card exa rise" aria-label="Watching">
      <h2 className="watching-title" title="Re-checked with Exa. You only hear about changes.">
        <IconBell size={17} /> Watching
      </h2>
      <ul className="watch-list">
        {watches.map((w) => {
          const r = w.last_result;
          const n = r ? r.new_sources.length + r.updated_sources.length + r.gone_sources.length : 0;
          const cites = r ? r.sources.map((s) => ({ n: s.n ?? 0, title: s.title, url: s.url })) : [];
          return (
            <li key={w.id} className="watch-item">
              <div className="watch-head">
                <div className="watch-text">
                  <p className="watch-q">{w.task}</p>
                  <p className="watch-meta">
                    Last checked {formatDate(w.last_checked_at.slice(0, 10))}
                    {r && !r.changed && (r.error ? " · couldn't check" : " · No changes")}
                  </p>
                </div>
                <button className="button ghost small-button" disabled={busy === w.id} onClick={() => check(w)}>
                  {busy === w.id ? "Checking…" : "Check now"}
                </button>
                <button className="icon-button" aria-label="Stop watching" title="Stop watching"
                  onClick={() => api.unwatch(w.id).then(() => onRemove(w.id)).catch(() => setFailed(w.id))}>
                  <IconClose size={16} />
                </button>
              </div>
              {failed === w.id && <p className="muted">Couldn't reach Kukkaro. Please try again.</p>}
              {r && r.changed && (
                <details className="watch-change reveal-in" open={fresh.has(w.id)}>
                  <summary className="watch-change-title">
                    {n} {n === 1 ? "source" : "sources"} changed
                    <span className="watch-counts">
                      {r.new_sources.length > 0 && ` · ${r.new_sources.length} new`}
                      {r.updated_sources.length > 0 && ` · ${r.updated_sources.length} updated`}
                      {r.gone_sources.length > 0 && ` · ${r.gone_sources.length} gone`}
                    </span>
                  </summary>
                  {r.summary && <p className="answer">{withCitations(r.summary, cites, `w-${w.id}-src`)}</p>}
                  {r.sources.length > 0 && (
                    <details className="sources-fold">
                    <summary className="section-title">
                      {r.sources.length} changed {r.sources.length === 1 ? "source" : "sources"}
                    </summary>
                    <ol className="sources">
                      {r.sources.map((s) => (
                        <li key={s.url} id={`w-${w.id}-src-${s.n}`} className="cited">
                          <span className="src-n">{s.n}</span>
                          <a href={s.url} target="_blank" rel="noreferrer">
                            <span className="src-title">{s.title || s.url}</span>
                            <span className="src-meta">
                              {s.status === "new" ? "New" : "Updated"} · {s.site}
                              {s.published_date && ` · ${s.published_date.slice(0, 10)}`}
                              <IconExternal size={13} />
                            </span>
                          </a>
                        </li>
                      ))}
                    </ol>
                    </details>
                  )}
                  {r.gone_sources.length > 0 && (
                    <p className="watch-gone">No longer found: {r.gone_sources.map((g) => g.site).join(", ")}</p>
                  )}
                </details>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// "[2]" or "[1, 2]" in the text becomes small links to those sources.
function withCitations(text: string, sources: ButlerSource[], idPrefix = "src"): ReactNode[] {
  const known = new Set(sources.map((s) => s.n));
  return text.split(/(\[\d+(?:\s*,\s*\d+)*\])/g).map((part, i) => {
    const m = part.match(/^\[([\d,\s]+)\]$/);
    if (!m) return part;
    const ns = m[1].split(",").map((x) => Number(x.trim())).filter((n) => known.has(n));
    if (ns.length === 0) return part;
    return ns.map((n) => (
      <a key={`${i}-${n}`} className="cite" href={`#${idPrefix}-${n}`} aria-label={`Source ${n}`}
        onClick={() => document.getElementById(`${idPrefix}-${n}`)?.closest("details")?.setAttribute("open", "")}>
        {n}
      </a>
    ));
  });
}

function Draft({ draft }: { draft: NonNullable<ButlerResponse["draft"]> }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(draft.body);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };
  return (
    <details className="draft-card draft-fold">
      <summary>
        <span className="eyebrow">{draft.kind === "email" ? "Draft ready to send" : "Draft ready to fill in"}</span>
        {draft.subject && <span className="draft-subject">{draft.subject}</span>}
      </summary>
      <pre className="draft-text">{draft.body}</pre>
      <div className="draft-actions">
        {draft.mailto ? (
          <a className="button primary" href={draft.mailto}>
            <IconMail /> Open in email app
          </a>
        ) : (
          draft.open_url && (
            <a className="button primary" href={draft.open_url} target="_blank" rel="noreferrer">
              <IconExternal /> Open the official page
            </a>
          )
        )}
        <button className="button ghost" onClick={copy}>
          <IconCopy /> {copied ? "Copied" : "Copy text"}
        </button>
      </div>
      <p className="muted small">Nothing is sent automatically. You review it and send it yourself.</p>
    </details>
  );
}

// "Same food, smaller bill": branded items from the receipts, with the real S-Group own-brand product.
function Swaps() {
  const [data, setData] = useState<SwapsResponse | null>(null);
  const [failed, setFailed] = useState(false);
  const basket = useOrderBasket();

  useEffect(() => {
    api.swaps(CUSTOMER_ID).then(setData).catch(() => setFailed(true));
  }, []);

  if (failed) return null;
  if (!data) return <div className="skeleton swap-skeleton" aria-label="Looking for store-brand swaps" />;
  const shown = data.swaps.filter((s) => s.product && s.product.price_eur != null);
  if (shown.length === 0) return null;

  return (
    <details className="swaps card fold-card rise" aria-label="Store-brand swaps">
      <summary>
        <span className="swaps-head">
          <span className="swaps-kicker"><IconReceipt size={15} /> From your receipts</span>
          <span className="swaps-title">Same food, smaller bill</span>
        </span>
        <span className="swaps-save num">−{formatEur(data.monthly_saving_eur)}/mo</span>
      </summary>
      <ul className="swap-list">
        {shown.map((s) => {
          const p = s.product!;
          const added = basket.has(p.id);
          return (
            <li key={s.item} className="swap">
              {p.image && <img className="product-img" src={p.image} alt="" loading="lazy" />}
              <div className="swap-body">
                <span className="swap-instead">Instead of {s.item}</span>
                <a className="product-name" href={p.url} target="_blank" rel="noreferrer">{p.name}</a>
                <span className="product-price">
                  <span className="num">{formatEur(p.price_eur!)}</span> at {p.store}
                </span>
                <span className="swap-save">
                  Save about <strong className="num">{formatEur(s.monthly_saving_eur)}</strong> a month
                </span>
                <button className={`button small-button ${added ? "ghost" : "primary"}`}
                        onClick={() => (added ? basket.remove(p.id) : basket.add("swap", p.id))}>
                  {added ? "Swapped in your order ✓" : "Swap in my order"}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      <p className="source">
        Savings come from your synthetic receipts ({formatMonth(data.start.slice(0, 7))}–{formatMonth(data.end.slice(0, 7))});
        prices and pictures are read from the S-kaupat product pages.
      </p>
    </details>
  );
}

// Product cards in a Butler answer: picture, page price and source. Only priced products can be added.
function ProductCards({ products }: { products: Product[] }) {
  const basket = useOrderBasket();
  return (
    <>
      <h3 className="section-title">Products <span className="powered">· S-kaupat</span></h3>
      <ul className="product-grid">
        {products.map((p) => {
          const added = basket.has(p.id);
          return (
            <li key={p.id} className="product-card">
              {p.image ? <img className="product-img" src={p.image} alt="" loading="lazy" /> : <span className="product-img empty" aria-hidden />}
              <a className="product-name" href={p.url} target="_blank" rel="noreferrer">{p.name}</a>
              <span className="product-price">
                {p.price_eur != null ? <span className="num">{formatEur(p.price_eur)}</span> : "Price on the page"}
                {p.n != null && <a className="cite" href={`#src-${p.n}`} aria-label={`Source ${p.n}`}>{p.n}</a>}
              </span>
              {p.price_eur != null && (
                <button className={`button small-button ${added ? "ghost" : "primary"}`}
                        onClick={() => (added ? basket.remove(p.id) : basket.add("extra", p.id))}>
                  {added ? "In your order ✓" : "Add to my order"}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}

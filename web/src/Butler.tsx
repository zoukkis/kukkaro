import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { api, CUSTOMER_ID, type BillSuggestion, type ButlerResponse, type ButlerSource } from "./api";
import { formatEur, formatMonth } from "./format";
import { IconCopy, IconExternal, IconMail, IconSend, IconSpark, IconTrend } from "./Icons";

// The three demo tasks from backend/kukkaro/butler/AGENTS.md.
const EXAMPLES = [
  "Am I possibly eligible for Kela housing allowance?",
  "My rent went up. Is that allowed, and what can I do?",
  "Am I overpaying for electricity?",
];

// What the Butler really does, in order (backend/kukkaro/butler/agent.py).
const STAGES = ["Reading your bills and income", "Searching official sources and current prices", "Checking every number", "Preparing a draft for you"];

const stagger = (i: number) => ({ "--i": i }) as CSSProperties;

export default function Butler() {
  const [input, setInput] = useState("");
  const [task, setTask] = useState<string | null>(null);
  const [res, setRes] = useState<ButlerResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const [stage, setStage] = useState(0);
  const [cards, setCards] = useState<BillSuggestion[]>([]);

  useEffect(() => {
    api.suggestions(CUSTOMER_ID).then((r) => setCards(r.suggestions)).catch(() => setCards([]));
  }, []);

  useEffect(() => {
    if (!busy) return;
    setStage(0);
    const t = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 2600);
    return () => clearInterval(t);
  }, [busy]);

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
        <h1 className="display rise" style={stagger(1)}>
          Money you might be <em>missing.</em>
        </h1>
        <p className="lede rise" style={stagger(2)}>
          I search the live web for benefits, fairer prices and your rights, show every source, and prepare the next
          step. You decide what to send.
        </p>
      </div>

      {cards.map((c, i) => (
        <section key={c.category} className="nudge rise" style={stagger(3 + i)}>
          <span className="nudge-icon"><IconTrend /></span>
          <div className="nudge-body">
            <p className="eyebrow">Noticed in your bank data</p>
            <h2 className="nudge-title">
              {c.title} <span className="up num">+{c.change_pct}%</span>
            </h2>
            <p className="muted">
              {formatMonth(c.latest_month)}: <strong className="num">{formatEur(c.latest_month_eur)}</strong> vs a typical
              month of <strong className="num">{formatEur(c.typical_monthly_eur)}</strong>
            </p>
            <button className="button primary" disabled={busy} onClick={() => { setInput(c.task); run(c.task); }}>
              <IconSpark /> Ask the Butler why
            </button>
          </div>
        </section>
      ))}

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
      <div className="chips wrap rise" style={stagger(5)} aria-label="Example tasks">
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
        <section className="card exa butler-answer reveal-in" aria-live="polite">
          <p className="butler-task"><span className="q" aria-hidden>search</span>{task}</p>
          <p className="answer">{withCitations(res.answer, res.sources)}</p>

          {res.draft && <Draft draft={res.draft} />}

          {res.next_steps.length > 0 && (
            <>
              <h3 className="section-title">Next steps</h3>
              <ol className="steps">
                {res.next_steps.map((s, i) => (
                  <li key={i}>
                    <label>
                      <input type="checkbox" /> <span>{withCitations(s, res.sources)}</span>
                    </label>
                  </li>
                ))}
              </ol>
            </>
          )}

          {res.sources.length > 0 && (
            <>
              <h3 className="section-title">Sources <span className="powered">· found with Exa</span></h3>
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
            </>
          )}
          <p className="source">
            Kukkaro is a coach, not a licensed advisor. You decide what to do; check the official source before acting.
            {res.model && ` Answered by ${res.model}${res.cached ? " (saved answer)" : ""}.`}
          </p>
        </section>
      )}
    </div>
  );
}

// "[2]" or "[1, 2]" in the text becomes small links to those sources.
function withCitations(text: string, sources: ButlerSource[]): ReactNode[] {
  const known = new Set(sources.map((s) => s.n));
  return text.split(/(\[\d+(?:\s*,\s*\d+)*\])/g).map((part, i) => {
    const m = part.match(/^\[([\d,\s]+)\]$/);
    if (!m) return part;
    const ns = m[1].split(",").map((x) => Number(x.trim())).filter((n) => known.has(n));
    if (ns.length === 0) return part;
    return ns.map((n) => (
      <a key={`${i}-${n}`} className="cite" href={`#src-${n}`} aria-label={`Source ${n}`}>
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
    <div className="draft-card">
      <p className="eyebrow">{draft.kind === "email" ? "Ready to send" : "Ready to fill in"}</p>
      {draft.subject && <h3 className="draft-subject">{draft.subject}</h3>}
      <details className="draft-body">
        <summary>Read the draft</summary>
        <pre>{draft.body}</pre>
      </details>
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
    </div>
  );
}

import { useState } from "react";
import { api, CUSTOMER_ID, type ButlerResponse } from "./api";

// The three demo tasks from backend/kukkaro/butler/AGENTS.md.
const EXAMPLES = [
  "Am I possibly eligible for Kela housing allowance?",
  "My rent went up. Is that allowed, and what can I do?",
  "Am I overpaying for electricity?",
];

export default function Butler() {
  const [input, setInput] = useState("");
  const [task, setTask] = useState<string | null>(null);
  const [res, setRes] = useState<ButlerResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

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
    <div className="baskets butler">
      <div className="welcome">
        <h1>Kukkaro Butler</h1>
        <p>I search the live web for money you might be missing (benefits, fairer prices, your rights) and always show my sources.</p>
      </div>

      <form
        className="composer butler-input"
        onSubmit={(e) => {
          e.preventDefault();
          run(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask the Butler…"
          aria-label="Your task for the Butler"
        />
        <button type="submit" disabled={busy || input.trim().length < 3} aria-label="Ask">
          ➤
        </button>
      </form>
      <div className="chips wrap" aria-label="Example tasks">
        {EXAMPLES.map((s) => (
          <button
            key={s}
            className="chip"
            disabled={busy}
            onClick={() => {
              setInput(s);
              run(s);
            }}
          >
            {s}
          </button>
        ))}
      </div>

      {busy && (
        <section className="card butler-loading" aria-live="polite">
          <div className="typing" aria-hidden>
            <span /> <span /> <span />
          </div>
          <p className="muted">Searching official sources and current prices for “{task}”…</p>
        </section>
      )}
      {error && <p className="status">Couldn't reach the Butler. Try again in a moment.</p>}

      {res && !busy && (
        <section className="card butler-answer" aria-live="polite">
          <p className="butler-task muted">{task}</p>
          <p>{res.answer}</p>

          {res.next_steps.length > 0 && (
            <>
              <h3>Next steps</h3>
              <ol className="steps">
                {res.next_steps.map((s, i) => (
                  <li key={i}>
                    <label>
                      <input type="checkbox" /> <span>{s}</span>
                    </label>
                  </li>
                ))}
              </ol>
            </>
          )}

          {res.draft && (
            <details className="how">
              <summary>Ready-to-send draft{res.draft.subject ? `: ${res.draft.subject}` : ""}</summary>
              <pre className="draft">{res.draft.body}</pre>
              {res.draft.mailto && (
                <a className="link-button" href={res.draft.mailto}>
                  Open in email app
                </a>
              )}
              {!res.draft.mailto && res.draft.open_url && (
                <a className="link-button" href={res.draft.open_url} target="_blank" rel="noreferrer">
                  Open the official page
                </a>
              )}
            </details>
          )}

          {res.sources.length > 0 && (
            <>
              <h3>Sources</h3>
              <ol className="sources">
                {res.sources.map((s) => (
                  <li key={s.n} value={s.n}>
                    <a href={s.url} target="_blank" rel="noreferrer">
                      {s.title || s.url}
                    </a>
                    <span className="muted">
                      {new URL(s.url).hostname}
                      {s.published_date && ` · ${s.published_date.slice(0, 10)}`}
                    </span>
                  </li>
                ))}
              </ol>
            </>
          )}
          <p className="source">
            Kukkaro is a coach, not a licensed advisor. You decide what to do; check the official source before acting.
            {res.model && ` · Answered by ${res.model}`}
          </p>
        </section>
      )}
    </div>
  );
}

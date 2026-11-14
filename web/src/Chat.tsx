import { useEffect, useRef, useState, type CSSProperties } from "react";
import { api, CUSTOMER_ID, type ChatResponse, type ChatTurn } from "./api";
import { formatFigure } from "./format";
import { IconArrow, IconSend, IconShield, Mark, Robot } from "./Icons";
import OrderCard from "./Order";

// S-Bank's four brief questions come first (web/AGENTS.md).
const SUGGESTIONS = [
  "Where did my money go?",
  "What kind of spender am I?",
  "What can I safely spend this week?",
  "How could I save more?",
];
// Concept demo (Order.tsx): the coach prepares a grocery order for robot delivery; nothing is bought.
const ERRAND = "Order my usual groceries";

// The order card appears under an answer when the coach prepared an order.
function orderCall(res?: ChatResponse) {
  return res?.tool_calls.find((t) => t.name === "plan_grocery_order");
}

interface Message {
  role: "user" | "assistant";
  content: string;
  response?: ChatResponse;
  error?: boolean;
}

const stagger = (i: number) => ({ "--i": i }) as CSSProperties;

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Only follow the conversation; on first load keep the welcome headline in view.
    if (messages.length > 0 || busy) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    const history: ChatTurn[] = messages
      .filter((m) => !m.error)
      .map(({ role, content }) => ({ role, content }));
    setMessages((ms) => [...ms, { role: "user", content: message }]);
    setInput("");
    setBusy(true);
    try {
      const res = await api.chat(CUSTOMER_ID, message, history);
      setMessages((ms) => [...ms, { role: "assistant", content: res.answer, response: res }]);
    } catch {
      setMessages((ms) => [
        ...ms,
        { role: "assistant", content: "I couldn't reach the coach just now. Please try again in a moment.", error: true },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat">
      <div className="messages">
        {messages.length === 0 && (
          <div className="welcome">
            <p className="eyebrow mono rise" style={stagger(0)}>Your money coach</p>
            <h1 className="display rise" style={stagger(1)}>
              Ask your <em>money.</em>
            </h1>
            <p className="lede rise" style={stagger(2)}>
              I read your own transactions and explain them in plain language. Every number I give comes from your
              data, and you can check how I got it.
            </p>
            <ul className="question-list" aria-label="Suggested questions">
              {SUGGESTIONS.map((s, i) => (
                <li key={s} className="rise" style={stagger(3 + i)}>
                  <button className="question" disabled={busy} onClick={() => send(s)}>
                    <span>{s}</span>
                    <IconArrow />
                  </button>
                </li>
              ))}
              <li className="rise" style={stagger(7)}>
                <button className="question errand" disabled={busy} onClick={() => send(ERRAND)}>
                  <span className="errand-text">
                    <span className="errand-tag mono">Concept · new</span>
                    {ERRAND}
                    <span className="errand-sub">I prepare it, you approve, a robot delivers.</span>
                  </span>
                  <Robot size={44} />
                </button>
              </li>
            </ul>
          </div>
        )}

        {messages.map((m, i) => {
          const order = orderCall(m.response);
          return m.role === "user" ? (
            <div key={i} className="bubble user pop">
              {m.content}
            </div>
          ) : (
            <div key={i} className="assistant-turn">
            <div className="assistant-row pop">
              <span className="avatar"><Mark size={26} /></span>
              <div className={`bubble assistant${m.error ? " error" : ""}${m.response?.number_check === "withheld" ? " notice" : ""}`}>
                <p className="answer">{m.content}</p>
                {m.response && <AnswerMeta res={m.response} />}
                {m.response && <HowIGotThis res={m.response} />}
              </div>
            </div>
            {order && <OrderCard initialTreats={order.args.include_treats === true} />}
            </div>
          );
        })}

        {busy && (
          <div className="assistant-row pop" aria-label="The coach is thinking">
            <span className="avatar"><Mark size={26} /></span>
            <div className="bubble assistant typing">
              <span /> <span /> <span />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {messages.length > 0 && (
        <div className="chips" aria-label="Suggested questions">
          {[...SUGGESTIONS, ERRAND].map((s) => (
            <button key={s} className="chip" disabled={busy} onClick={() => send(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="dock">
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your spending…"
            aria-label="Your question"
          />
          <button type="submit" className="send" disabled={busy || !input.trim()} aria-label="Send">
            <IconSend />
          </button>
        </form>
      </div>
    </div>
  );
}

// Privacy labels instead of a model picker (root AGENTS.md §4). Gemma (the trusted zone) is the only model
// that sees the customer's data; "in the EU" only when it really runs on Verda.
function AnswerMeta({ res }: { res: ChatResponse }) {
  if (!res.model || res.model === "mock") return null;
  const web = res.zones?.includes("public") ?? false;
  const where = res.trusted_host === "verda" ? "open model in the EU" : "open model";
  return (
    <div className="answer-labels">
      {!res.fallback && (
        <p className="answer-meta private">
          <IconShield /> Answered privately with your own data · {where}
        </p>
      )}
      {res.fallback && <p className="answer-meta backup">↩︎ Backup model used</p>}
      {web && (
        <>
          <p className="answer-meta web">🌐 Also searched public sources</p>
          {res.sources && res.sources.length > 0 && (
            <ol className="answer-sources">
              {res.sources.map((s) => (
                <li key={s.url}>
                  <span className="src-n">{s.n}</span>
                  <a href={s.url} target="_blank" rel="noreferrer">
                    {s.title || s.url}
                    <span className="src-meta">{hostOf(s.url)}</span>
                  </a>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </div>
  );
}

function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function HowIGotThis({ res }: { res: ChatResponse }) {
  if (res.tool_calls.length === 0 && res.figures.length === 0) return null;
  return (
    <details className="how exa">
      <summary>
        How I got this
        {res.figures.length > 0 && <span className="count">{res.figures.length}</span>}
      </summary>
      {res.figures.length > 0 && (
        <ul className="ledger">
          {res.figures.map((f, i) => (
            <li key={i}>
              <span className="ledger-label">{f.label}</span>
              <span className="ledger-value">{formatFigure(f)}</span>
              <span className="ledger-source">{f.source}</span>
            </li>
          ))}
        </ul>
      )}
      {res.research && res.research.length > 0 && (
        <div className="tools sent">
          <span>Sent to the web search (no personal data):</span>
          {res.research.map((r, i) =>
            r.question_sent ? <q key={i}>{r.question_sent}</q> : <em key={i}>Not sent: it contained {r.blocked.join(", ")}</em>,
          )}
        </div>
      )}
      {res.tool_calls.length > 0 && (
        <div className="tools">
          <span>Calculated from your data with</span>
          {res.tool_calls.map((t, i) => (
            <code key={i} title={Object.entries(t.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")}>
              {t.name}
            </code>
          ))}
        </div>
      )}
    </details>
  );
}

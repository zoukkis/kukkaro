import { useEffect, useRef, useState, type CSSProperties } from "react";
import { api, CUSTOMER_ID, type ChatResponse, type ChatTurn, type Provider } from "./api";
import { formatFigure } from "./format";
import { IconArrow, IconSend, IconShield, Mark } from "./Icons";

// S-Bank's four brief questions come first (web/AGENTS.md).
const SUGGESTIONS = [
  "Where did my money go?",
  "What kind of spender am I?",
  "What can I safely spend this week?",
  "How could I save more?",
];

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
  const [provider, setProvider] = useState<Provider>("gemini");
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
      const res = await api.chat(CUSTOMER_ID, message, history, provider);
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
            <p className="eyebrow rise" style={stagger(0)}>Your money coach</p>
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
            </ul>
          </div>
        )}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="bubble user pop">
              {m.content}
            </div>
          ) : (
            <div key={i} className="assistant-row pop">
              <span className="avatar"><Mark size={26} /></span>
              <div className={`bubble assistant${m.error ? " error" : ""}${m.response?.number_check === "withheld" ? " notice" : ""}`}>
                <p className="answer">{m.content}</p>
                {m.response && <AnswerMeta res={m.response} />}
                {m.response && <HowIGotThis res={m.response} />}
              </div>
            </div>
          ),
        )}

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
          {SUGGESTIONS.map((s) => (
            <button key={s} className="chip" disabled={busy} onClick={() => send(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="dock">
        <div className="model-switch" role="group" aria-label="Which model answers">
          <span className="model-switch-label">Model</span>
          <button aria-pressed={provider === "gemini"} onClick={() => setProvider("gemini")} disabled={busy}>
            Gemini
          </button>
          <button aria-pressed={provider === "gemma"} onClick={() => setProvider("gemma")} disabled={busy}>
            Gemma 4 <span className="dim">· open</span>
          </button>
        </div>
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

// Which model answered. "EU privacy mode" only when the answer really came from Verda (overseer decision E).
function AnswerMeta({ res }: { res: ChatResponse }) {
  if (!res.model || res.model === "mock") return null;
  if (res.host === "verda") {
    return (
      <p className="answer-meta eu">
        <IconShield /> EU privacy mode · Gemma 4 on Verda
      </p>
    );
  }
  return (
    <p className="answer-meta">{res.provider === "gemma" ? "Open model · Gemma 4 (via Google API)" : `Gemini · ${res.model}`}</p>
  );
}

function HowIGotThis({ res }: { res: ChatResponse }) {
  if (res.tool_calls.length === 0 && res.figures.length === 0) return null;
  return (
    <details className="how">
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

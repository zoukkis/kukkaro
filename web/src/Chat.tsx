import { useEffect, useRef, useState } from "react";
import { api, CUSTOMER_ID, type ChatResponse, type ChatTurn } from "./api";
import { formatFigure } from "./format";

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

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
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
        { role: "assistant", content: "Sorry, I couldn't reach the coach. Try again in a moment.", error: true },
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
            <h1>Ask your money</h1>
            <p>I look at your own transactions and explain them in plain language. Every number comes from your data.</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}${m.error ? " error" : ""}`}>
            <p>{m.content}</p>
            {m.response && <HowIGotThis res={m.response} />}
          </div>
        ))}
        {busy && (
          <div className="bubble assistant typing" aria-label="Coach is thinking">
            <span /> <span /> <span />
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="chips" aria-label="Suggested questions">
        {SUGGESTIONS.map((s) => (
          <button key={s} className="chip" disabled={busy} onClick={() => send(s)}>
            {s}
          </button>
        ))}
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
        <button type="submit" disabled={busy || !input.trim()} aria-label="Send">
          ➤
        </button>
      </form>
    </div>
  );
}

function HowIGotThis({ res }: { res: ChatResponse }) {
  if (res.tool_calls.length === 0 && res.figures.length === 0) return null;
  return (
    <details className="how">
      <summary>How I got this</summary>
      {res.figures.length > 0 && (
        <ul className="figures">
          {res.figures.map((f, i) => (
            <li key={i}>
              <span className="fig-label">{f.label}</span>
              <span className="fig-value">{formatFigure(f)}</span>
              <span className="fig-source">{f.source}</span>
            </li>
          ))}
        </ul>
      )}
      {res.tool_calls.length > 0 && (
        <div className="tools">
          <span>Calculated with:</span>
          {res.tool_calls.map((t, i) => (
            <code key={i}>
              {t.name}({Object.entries(t.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})
            </code>
          ))}
        </div>
      )}
      {res.model && <div className="model">Answered by: {res.model}</div>}
    </details>
  );
}

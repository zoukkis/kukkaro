import { useState } from "react";
import { USE_MOCK } from "./api";
import Chat from "./Chat";
import Baskets from "./Baskets";
import Butler from "./Butler";

type Tab = "chat" | "baskets" | "butler";

export default function App() {
  const [tab, setTab] = useState<Tab>("chat");
  return (
    <div className="phone">
      <header className="topbar">
        <span className="brand">Kukkaro</span>
        <span className="subtitle">your money coach</span>
      </header>
      {USE_MOCK && <div className="mock-banner">Mock data: backend not connected</div>}
      {/* Both stay mounted so chat history survives tab switches */}
      <main className="content" hidden={tab !== "chat"}>
        <Chat />
      </main>
      <main className="content" hidden={tab !== "baskets"}>
        <Baskets />
      </main>
      <main className="content" hidden={tab !== "butler"}>
        <Butler />
      </main>
      <nav className="tabbar" aria-label="Main">
        <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
          <span aria-hidden>💬</span> Ask
        </button>
        <button className={tab === "baskets" ? "active" : ""} onClick={() => setTab("baskets")}>
          <span aria-hidden>🧺</span> Baskets
        </button>
        <button className={tab === "butler" ? "active" : ""} onClick={() => setTab("butler")}>
          <span aria-hidden>🔎</span> Butler
        </button>
      </nav>
    </div>
  );
}

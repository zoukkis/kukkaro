import { useState } from "react";
import { USE_MOCK } from "./api";
import Chat from "./Chat";
import Baskets from "./Baskets";
import Butler from "./Butler";
import { IconAsk, IconBaskets, IconButler, Mark } from "./Icons";

type Tab = "chat" | "baskets" | "butler";

const TABS: { id: Tab; label: string; Icon: typeof IconAsk }[] = [
  { id: "chat", label: "Ask", Icon: IconAsk },
  { id: "baskets", label: "Baskets", Icon: IconBaskets },
  { id: "butler", label: "Butler", Icon: IconButler },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("chat");
  return (
    <div className="stage">
      <div className="phone">
        <a className="skip" href="#main">Skip to content</a>
        <header className="topbar">
          <div className="brand">
            <Mark size={30} />
            <span className="wordmark">Kukkaro</span>
          </div>
          <span className="demo-flag" title="All data in this demo is synthetic">
            {USE_MOCK ? "Mock data" : "Synthetic demo data"}
          </span>
        </header>
        {/* All three stay mounted so chat history and Butler answers survive tab switches */}
        <main id="main" className="content">
          <section className="screen" hidden={tab !== "chat"} aria-label="Ask">
            <Chat />
          </section>
          <section className="screen" hidden={tab !== "baskets"} aria-label="Baskets">
            <Baskets />
          </section>
          <section className="screen" hidden={tab !== "butler"} aria-label="Butler">
            <Butler />
          </section>
        </main>
        <nav className="tabbar" aria-label="Main">
          {TABS.map(({ id, label, Icon }) => (
            <button key={id} className="tab" aria-current={tab === id ? "page" : undefined} onClick={() => setTab(id)}>
              <span className="tab-icon"><Icon /></span>
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </div>
    </div>
  );
}

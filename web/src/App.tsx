import { useState } from "react";
import { USE_MOCK } from "./api";
import Home from "./Home";
import Chat from "./Chat";
import Baskets from "./Baskets";
import Butler from "./Butler";
import { IconAsk, IconBaskets, IconButler, IconHouse, Mark } from "./Icons";

type Tab = "home" | "baskets" | "chat" | "help";

const TABS: { id: Tab; label: string; Icon: typeof IconAsk }[] = [
  { id: "home", label: "Home", Icon: IconHouse },
  { id: "baskets", label: "Baskets", Icon: IconBaskets },
  { id: "chat", label: "Ask Kukkaro", Icon: IconAsk },
  { id: "help", label: "Help", Icon: IconButler },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("home");
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
        {/* All screens stay mounted so chat history and Butler answers survive tab switches */}
        <main id="main" className="content">
          <section className="screen" hidden={tab !== "home"} aria-label="Home">
            <Home onOpenBaskets={() => setTab("baskets")} />
          </section>
          <section className="screen" hidden={tab !== "baskets"} aria-label="Baskets">
            <Baskets />
          </section>
          <section className="screen" hidden={tab !== "chat"} aria-label="Ask Kukkaro">
            <Chat />
          </section>
          <section className="screen" hidden={tab !== "help"} aria-label="Help">
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

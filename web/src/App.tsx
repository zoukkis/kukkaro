import { useState } from "react";
import { USE_MOCK } from "./api";
import Home from "./Home";
import Chat from "./Chat";
import Baskets from "./Baskets";
import Butler from "./Butler";
import OrderCard from "./Order";
import { OrderBasketProvider, useOrderBasket } from "./basket";
import { IconAsk, IconBaskets, IconButler, IconClose, IconHouse, Mark, Robot } from "./Icons";

type Tab = "home" | "baskets" | "chat" | "help";

const TABS: { id: Tab; label: string; Icon: typeof IconAsk }[] = [
  { id: "home", label: "Home", Icon: IconHouse },
  { id: "baskets", label: "Baskets", Icon: IconBaskets },
  { id: "chat", label: "Ask Kukkaro", Icon: IconAsk },
  { id: "help", label: "Help", Icon: IconButler },
];

export default function App() {
  return (
    <OrderBasketProvider>
      <Shell />
    </OrderBasketProvider>
  );
}

function Shell() {
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
            <Home onOpenBaskets={() => setTab("baskets")} onOpenHelp={() => setTab("help")} />
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
        <OrderSheet />
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

// Products added from Help (swaps, Butler products) go to the planned order. A pill opens it as a sheet.
function OrderSheet() {
  const basket = useOrderBasket();
  if (basket.count === 0 && !basket.open) return null;
  return (
    <>
      {!basket.open && (
        <button className="order-pill" onClick={() => basket.setOpen(true)}>
          <Robot size={22} /> Your order · {basket.count} added
        </button>
      )}
      {basket.open && (
        <div className="sheet-backdrop" onClick={() => basket.setOpen(false)}>
          <div className="sheet" role="dialog" aria-label="Your grocery order" onClick={(e) => e.stopPropagation()}>
            <button className="sheet-close" onClick={() => basket.setOpen(false)} aria-label="Close">
              <IconClose />
            </button>
            <OrderCard />
          </div>
        </div>
      )}
    </>
  );
}

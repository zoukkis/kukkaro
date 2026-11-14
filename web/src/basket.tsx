// What the customer added to the planned grocery order from the Help tab: own-brand swaps and
// Butler products, by product id only. The server prices them; the browser never sends a price.
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

interface OrderBasket {
  extras: string[];
  swaps: string[];
  count: number;
  has: (id: string) => boolean;
  add: (kind: "extra" | "swap", id: string) => void;
  remove: (id: string) => void;
  open: boolean;
  setOpen: (v: boolean) => void;
}

const Ctx = createContext<OrderBasket | null>(null);

export function OrderBasketProvider({ children }: { children: ReactNode }) {
  const [extras, setExtras] = useState<string[]>([]);
  const [swaps, setSwaps] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const value = useMemo<OrderBasket>(
    () => ({
      extras,
      swaps,
      count: extras.length + swaps.length,
      has: (id) => extras.includes(id) || swaps.includes(id),
      add: (kind, id) =>
        kind === "swap"
          ? setSwaps((s) => (s.includes(id) ? s : [...s, id]))
          : setExtras((s) => (s.includes(id) ? s : [...s, id])),
      remove: (id) => {
        setExtras((s) => s.filter((x) => x !== id));
        setSwaps((s) => s.filter((x) => x !== id));
      },
      open,
      setOpen,
    }),
    [extras, swaps, open],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useOrderBasket(): OrderBasket {
  const v = useContext(Ctx);
  if (!v) throw new Error("useOrderBasket outside OrderBasketProvider");
  return v;
}

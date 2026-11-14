// Concept demo: the coach prepares "your usual groceries" from your receipts, you approve, a delivery
// robot brings them. Nothing is ordered or paid (root AGENTS.md §7-8): approval is simulated and
// every number on this card comes from GET /customers/{id}/grocery-order.
import { useEffect, useRef, useState } from "react";
import { api, CUSTOMER_ID, type DeliveryOption, type GroceryPlan, type OrderConfirmation } from "./api";
import { formatEur } from "./format";
import { useOrderBasket } from "./basket";
import { IconClose, IconHouse, Robot } from "./Icons";

const SHOWN = 5;
const STAGES: Record<DeliveryOption, string[]> = {
  robot: ["Order approved", "Packing at the store", "Robot on its way", "At your door"],
  home: ["Order approved", "Packing at the store", "Courier on its way", "At your door"],
  pickup: ["Order approved", "Packing at the store", "Ready to pick up"],
};

export default function OrderCard({ initialTreats = false }: { initialTreats?: boolean }) {
  const [includeTreats, setIncludeTreats] = useState(initialTreats);
  const [delivery, setDelivery] = useState<DeliveryOption>("robot");
  const [plan, setPlan] = useState<GroceryPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [approving, setApproving] = useState(false);
  const [done, setDone] = useState<OrderConfirmation | null>(null);
  const basket = useOrderBasket();

  useEffect(() => {
    let live = true;
    setError(null);
    api
      .groceryPlan(CUSTOMER_ID, includeTreats, delivery, basket.extras, basket.swaps)
      .then((p) => live && setPlan(p))
      .catch(() => live && setError("I couldn't prepare the order just now. Please try again."));
    return () => {
      live = false;
    };
  }, [includeTreats, delivery, basket.extras, basket.swaps]);

  async function approve() {
    if (!plan) return;
    setApproving(true);
    setError(null);
    try {
      setDone(await api.approveOrder(CUSTOMER_ID, plan.plan_id, includeTreats, delivery, basket.extras, basket.swaps));
    } catch {
      setError("The order changed or the server is busy. Please review it again.");
    } finally {
      setApproving(false);
    }
  }

  if (done) return <OrderTracking done={done} />;
  if (!plan) {
    return error ? <p className="order-card bubble error">{error}</p> : <div className="order-card skeleton" aria-label="Preparing the order" />;
  }

  // Lines added from Help (swaps, Butler products) are always shown first.
  const added = plan.items.filter((i) => i.added);
  const usual = plan.items.filter((i) => !i.added);
  const items = [...added, ...(showAll ? usual : usual.slice(0, Math.max(0, SHOWN - added.length)))];
  return (
    <section className="order-card card reveal-in" aria-label="Grocery order to approve">
      <div className="order-head">
        <div>
          <p className="eyebrow mono">Ready for your approval</p>
          <h2 className="order-title">Your usual groceries</h2>
        </div>
        <span className="badge">Concept demo</span>
      </div>
      <p className="order-basis mono">
        A week's worth of what you bought on at least {plan.based_on.min_trips} of your {plan.based_on.receipts} grocery
        trips · synthetic receipts
      </p>

      <ul className="order-items">
        {items.map((i) =>
          i.added ? (
            <li key={i.product_id} className="added">
              {i.image ? <img className="order-thumb" src={i.image} alt="" loading="lazy" /> : <span className="order-qty mono">{i.qty}×</span>}
              <span className="order-name">
                {i.name}
                <span className="added-tag">
                  {i.added === "swap" ? `Store-brand swap · instead of ${i.swapped_from}` : "Added from Help"}
                  {i.url && (
                    <> · <a href={i.url} target="_blank" rel="noreferrer">price on S-kaupat</a></>
                  )}
                </span>
              </span>
              <strong className="mono">{formatEur(i.line_total_eur)}</strong>
              <button className="remove-added" onClick={() => i.product_id && basket.remove(i.product_id)} aria-label={`Remove ${i.name}`}>
                <IconClose size={16} />
              </button>
            </li>
          ) : (
            <li key={i.name} className={i.basket === "EVERYDAY" ? "treat" : undefined}>
              <span className="order-qty mono">
                {i.qty}
                {i.unit === "kg" ? " kg" : "×"}
              </span>
              <span className="order-name">{i.name}</span>
              <strong className="mono">{formatEur(i.line_total_eur)}</strong>
            </li>
          ),
        )}
      </ul>
      {plan.items.length > items.length || showAll ? (
        <button className="link-button" onClick={() => setShowAll((s) => !s)}>
          {showAll ? "Show less" : `Show all ${plan.items.length} items`}
        </button>
      ) : null}

      <div className={`treats${includeTreats ? " on" : ""}`}>
        <div>
          <strong>{includeTreats ? "Treats included" : "Treats left out"}</strong>
          <span className="muted small">
            {includeTreats
              ? `Your usual treats add ${formatEur(plan.treats_per_week_eur)} a week.`
              : `${plan.left_out.map((t) => t.name).join(", ")}: ${formatEur(plan.treats_per_week_eur)} a week you keep.`}
          </span>
        </div>
        <button className="button ghost small-button" onClick={() => setIncludeTreats((t) => !t)}>
          {includeTreats ? "Leave out" : "Add back"}
        </button>
      </div>

      <div className="delivery" role="radiogroup" aria-label="Delivery">
        {plan.delivery_options.map((o) => (
          <button
            key={o.option}
            role="radio"
            aria-checked={delivery === o.option}
            className="delivery-option"
            onClick={() => setDelivery(o.option)}
          >
            {o.option === "robot" ? <Robot size={30} /> : <IconHouse />}
            <span className="delivery-label">{o.label}</span>
            <span className="delivery-fee mono">{o.fee_eur > 0 ? formatEur(o.fee_eur) : "Free"}</span>
          </button>
        ))}
      </div>
      <p className="muted small">
        {plan.delivery.eta}. Delivery fees are example values.
      </p>

      <dl className="order-sum">
        <div>
          <dt>Groceries</dt>
          <dd className="mono">{formatEur(plan.items_total_eur)}</dd>
        </div>
        <div>
          <dt>{plan.delivery.label}</dt>
          <dd className="mono">{formatEur(plan.delivery.fee_eur)}</dd>
        </div>
        <div className="order-total">
          <dt>Total</dt>
          <dd className="mono">{formatEur(plan.order_total_eur)}</dd>
        </div>
      </dl>
      <p className={`fit ${plan.fits_this_week ? "ok" : "over"}`}>
        {plan.fits_this_week
          ? `Fits this week: ${formatEur(plan.left_this_week_after_order_eur)} of your ${formatEur(plan.safe_to_spend_this_week_eur)} safe to spend is left.`
          : `Over this week's ${formatEur(plan.safe_to_spend_this_week_eur)} safe to spend by ${formatEur(-plan.left_this_week_after_order_eur)}.`}
      </p>

      {error && <p className="bubble error small">{error}</p>}
      <button className="button primary approve" onClick={approve} disabled={approving}>
        {approving ? "Approving…" : `Approve ${formatEur(plan.order_total_eur)}`}
      </button>
      <p className="concept-note">Concept demo: nothing is ordered or paid. In production you would approve this in your banking app.</p>
    </section>
  );
}

function OrderTracking({ done }: { done: OrderConfirmation }) {
  const robot = done.delivery.option === "robot";
  const stages = STAGES[done.delivery.option];
  const [stage, setStage] = useState(0);
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    const t = setInterval(() => setStage((s) => Math.min(s + 1, stages.length - 1)), 2600);
    return () => clearInterval(t);
  }, [stages.length]);

  const arrived = stage === stages.length - 1;
  return (
    <section ref={ref} className="order-card card tracking reveal-in" aria-live="polite">
      <div className="order-head">
        <div>
          <p className="eyebrow mono">Simulated · {done.order_ref}</p>
          <h2 className="order-title">{arrived
              ? done.delivery.option === "pickup" ? "Ready to pick up." : "Your groceries are here."
              : robot ? "A robot is on its way." : "Order approved."}</h2>
        </div>
        <span className="badge">Concept demo</span>
      </div>

      {robot && (
        <div className={`road${arrived ? " arrived" : ""}`} data-stage={stage} aria-hidden>
          <span className="road-store mono">Store</span>
          <span className="road-bot">
            <Robot size={58} />
          </span>
          <span className="road-home">
            <IconHouse size={30} />
          </span>
        </div>
      )}

      <ol className="stages">
        {stages.map((s, i) => (
          <li key={s} className={i < stage ? "done" : i === stage ? "now" : ""}>
            <span className="stage-n">{String(i + 1).padStart(2, "0")}</span>
            {s}
          </li>
        ))}
      </ol>

      <dl className="order-sum">
        <div>
          <dt>{done.items} items · {done.delivery.label}</dt>
          <dd className="mono">{formatEur(done.order_total_eur)}</dd>
        </div>
        <div className="order-total">
          <dt>Left to spend this week</dt>
          <dd className="mono">{formatEur(done.left_this_week_after_order_eur)}</dd>
        </div>
      </dl>
      <p className="concept-note">{done.note}</p>
    </section>
  );
}

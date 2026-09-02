import { dec, formatAmount } from "@/api/money";
import { Money } from "@/design-system";

/**
 * Gross -> discount -> net -> cost -> margin, as a waterfall.
 *
 * charts.csv "Cumulative Changes" row: increases green, decreases red. This is
 * the single most useful chart in the product — it turns the four numbers the
 * engine returns into the story of where the money went, which a KPI card row
 * cannot do.
 *
 * Rendered as bars rather than a chart library instance: five known steps, no
 * axes, no tooltips needed, and no 40KB of Recharts on the builder's critical
 * path.
 */
interface Step {
  id: string;
  label: string;
  value: string;
  kind: "base" | "down" | "total" | "result";
}

export function MarginWaterfall({
  gross, discount, net, cost, margin, currency = "USD",
}: {
  gross: string; discount: string; net: string; cost: string; margin: string; currency?: string;
}) {
  const steps: Step[] = [
    { id: "gross", label: "Gross", value: gross, kind: "base" },
    { id: "discount", label: "Discount", value: discount, kind: "down" },
    { id: "net", label: "Net revenue", value: net, kind: "total" },
    { id: "cost", label: "Cost", value: cost, kind: "down" },
    { id: "margin", label: "Margin", value: margin, kind: "result" },
  ];

  const scale = dec(gross);
  const pct = (v: string) => (scale.isZero() ? 0 : dec(v).abs().div(scale).times(100).toNumber());

  const COLOR: Record<Step["kind"], string> = {
    base: "var(--ink-400)",
    down: "var(--value-down)",
    total: "var(--accent-500)",
    result: "var(--margin-healthy)",
  };

  // Left offset so each deduction starts where the previous bar ended.
  const offset = (id: string) => {
    if (id === "discount") return 100 - pct(discount);
    if (id === "cost") return pct(net) - pct(cost);
    return 0;
  };

  return (
    <div className="space-y-2">
      {steps.map((s) => {
        const width = Math.max(pct(s.value), 0.6);
        return (
          <div key={s.id}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xs text-content-secondary">{s.label}</span>
              <Money
                value={s.value}
                currency={currency}
                className="text-sm font-semibold"
                style={s.kind === "result" ? { color: COLOR.result } : undefined}
              />
            </div>
            <div className="mt-1 h-2.5 w-full overflow-hidden rounded-sm bg-ink-100">
              <span
                className="block h-full rounded-sm transition-all duration-slow ease-smooth"
                style={{
                  width: `${width}%`,
                  marginLeft: `${offset(s.id)}%`,
                  background: COLOR[s.kind],
                  opacity: s.kind === "down" ? 0.75 : 1,
                }}
              />
            </div>
          </div>
        );
      })}
      <p className="pt-0.5 text-2xs text-content-faint">
        Bars are proportional to gross revenue of {formatAmount(gross)}.
      </p>
    </div>
  );
}

import { Info } from "lucide-react";
import type { BlendedRiskRead } from "@/api/types";
import { BulletGauge, RISK, RiskBadge, Score, Tooltip } from "@/design-system";
import { dec } from "@/api/money";

/**
 * The blended risk score, decomposed.
 *
 * The wireframe explains the model in prose ("worst single line plus overall
 * pattern"); the API returns it structured — four weighted components, each
 * with a raw value, weight, cap and its own explanation. Showing the arithmetic
 * is what makes the score trustworthy rather than magic.
 */
const COMPONENT_LABEL: Record<string, string> = {
  WEIGHTED_DISCOUNT_OVERAGE: "Discount over ceiling",
  VIOLATION_BREADTH: "How many lines breach",
  MARGIN_SHORTFALL: "Margin below floor",
  DISCOUNT_DEPTH: "Overall discount depth",
};

export function RiskBreakdown({
  risk, escalationThreshold,
}: { risk: BlendedRiskRead; escalationThreshold?: string | null }) {
  const score = dec(risk.score).toNumber();
  const tone = RISK[risk.band];
  const threshold = escalationThreshold ? dec(escalationThreshold).toNumber() : undefined;

  return (
    <div>
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="micro">Blended risk</div>
          <div className="mt-0.5 flex items-baseline gap-2">
            <Score value={risk.score} dp={2} className="font-ui text-4xl font-semibold" style={{ color: tone.fg }} />
            <RiskBadge value={risk.band} />
          </div>
        </div>
        {risk.tier ? (
          <div className="text-right">
            <div className="micro">Tier sensitivity</div>
            <div className="num mt-0.5 text-md font-medium text-content-secondary">
              {risk.tier} &times;{dec(risk.tier_sensitivity ?? "1").toFixed(2)}
            </div>
          </div>
        ) : null}
      </div>

      <BulletGauge
        className="mt-3"
        value={score}
        max={100}
        color={tone.fg}
        threshold={threshold}
        thresholdLabel={threshold ? `Finance escalation at ${threshold}` : undefined}
        label={
          threshold !== undefined ? (
            <span>
              Finance escalation threshold marked at <span className="num">{threshold}</span>
            </span>
          ) : null
        }
      />

      <ul className="mt-3 space-y-2">
        {(risk.components ?? []).map((c) => {
          const points = dec(c.points).toNumber();
          const cap = Number(c.cap ?? 0) || 1;
          const share = Math.min(100, (points / cap) * 100);
          const dim = points === 0;
          return (
            <li key={c.name}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="flex min-w-0 items-center gap-1 text-xs text-content-secondary">
                  <span className="truncate">{COMPONENT_LABEL[c.name] ?? c.name}</span>
                  <Tooltip content={c.explanation}>
                    <Info aria-label={`How ${c.name} is calculated`} className="size-3 shrink-0 cursor-help text-content-faint" />
                  </Tooltip>
                </span>
                <span className="num shrink-0 text-xs">
                  <span className={dim ? "text-content-faint" : "font-semibold text-content"}>
                    {dec(c.points).toFixed(2)}
                  </span>
                  <span className="text-content-faint"> / {c.cap}</span>
                </span>
              </div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-pill bg-ink-100">
                <span
                  className="block h-full rounded-pill transition-[width] duration-slow ease-smooth"
                  style={{ width: `${share}%`, background: dim ? "var(--ink-300)" : tone.fg }}
                />
              </div>
              <p className="mt-1 text-2xs leading-[15px] text-content-faint">{c.explanation}</p>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

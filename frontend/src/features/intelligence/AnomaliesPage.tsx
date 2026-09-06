import { TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import { dec, formatRelative } from "@/api/money";
import { useReport, useSettings } from "@/api/queries";
import type { DiscountAnomalyReport } from "@/api/types";
import { useAuth } from "@/app/auth";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, GovNote, Panel, PanelHead, Percent, Score, SeverityBadge, Skeleton, Tooltip,
} from "@/design-system";

/**
 * Discount anomalies answer a different question from the policy engine: not
 * "is this above the ceiling" but "is this unusual for this person". A fully
 * compliant quote can fire here, and a breaching one can stay silent.
 */
export function AnomaliesPage() {
  const { user } = useAuth();
  const query = useReport<DiscountAnomalyReport>("discount-anomalies");
  const settings = useSettings(user?.role === "ADMIN");

  return (
    <Page
      title="Discount anomalies"
      subtitle="Quotes discounted well above the rep's own historical average."
    >
      <GovNote className="mb-3" title="How this is detected">
        Each rep&rsquo;s own history forms the baseline. A version is flagged when it sits more than{" "}
        <span className="num font-semibold">{settings.data ? dec(settings.data.discount_anomaly_sigma).toFixed(1) : "2.0"}</span>{" "}
        standard deviations above that personal average, and only once at least{" "}
        <span className="num font-semibold">{settings.data?.discount_anomaly_min_samples ?? 5}</span> prior versions exist.
        Deliberately not a fixed threshold — 20% can be routine for one rep and exceptional for another.
      </GovNote>

      <Panel>
        <PanelHead
          icon={<TrendingUp className="size-4" />}
          title="Flagged versions"
          subtitle={query.data ? `${query.data.anomaly_count} flagged \u00b7 generated ${formatRelative(query.data.generated_at)}` : undefined}
        />
        <Async
          query={query}
          skeleton={<div className="space-y-2 p-4">{[0, 1].map((i) => <Skeleton key={i} className="h-16 w-full" />)}</div>}
          isEmpty={(d) => (d.items?.length ?? 0) === 0}
          empty={
            <div className="px-6 py-12 text-center">
              <p className="font-ui text-md font-semibold text-content">No anomalies detected</p>
              <p className="mx-auto mt-1 max-w-lg text-sm leading-relaxed text-content-muted">
                Either every quote sits inside its author&rsquo;s normal range, or there is not yet enough
                history per rep to form a reliable baseline. This is a genuine empty result, not a missing
                feature.
              </p>
            </div>
          }
        >
          {(report) => (
            <ul className="divide-y divide-line/70">
              {report.items.map((a) => (
                <li key={a.quote_version_id} className="relative py-3 pl-4 pr-3">
                  <span aria-hidden className="absolute inset-y-0 left-0 w-[3px]" style={{ background: "var(--gov-500)" }} />

                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge value={a.severity as never} size="sm" />
                    <Link to={`/quotes/${a.quote_id}`} className="num font-ui text-sm font-semibold text-accent-600 hover:underline">
                      {a.quote_number}
                    </Link>
                    <span className="text-xs text-content-faint">v{a.version_number}</span>
                    <span className="text-sm text-content-secondary">{a.customer_name}</span>
                    <span className="ml-auto text-xs text-content-muted">{a.rep_name}</span>
                  </div>

                  <div className="mt-2 flex flex-wrap items-baseline gap-x-6 gap-y-1">
                    <span className="flex items-baseline gap-1.5">
                      <span className="micro">This version</span>
                      <Percent value={a.effective_discount_pct} dp={2} className="text-md font-semibold text-gov-600" />
                    </span>
                    <span className="flex items-baseline gap-1.5">
                      <span className="micro">Their average</span>
                      <Percent value={a.baseline.mean_discount_pct} dp={2} className="text-sm text-content-secondary" />
                    </span>
                    <span className="flex items-baseline gap-1.5">
                      <span className="micro">Deviation</span>
                      <Tooltip content={`Flagged beyond ${dec(a.sigma_threshold).toFixed(1)} standard deviations`}>
                        <span className="num cursor-help text-sm font-semibold text-content">
                          <Score value={a.deviations_above_mean} dp={2} />&sigma;
                        </span>
                      </Tooltip>
                    </span>
                    <span className="flex items-baseline gap-1.5">
                      <span className="micro">Would flag above</span>
                      <Percent value={a.trigger_at_pct} dp={2} className="text-sm text-content-muted" />
                    </span>
                    <span className="flex items-baseline gap-1.5">
                      <span className="micro">Baseline from</span>
                      <span className="num text-sm text-content-muted">{a.baseline.sample_count} versions</span>
                    </span>
                  </div>

                  {a.reason ? (
                    <p className="mt-1.5 text-sm leading-[18px] text-content-secondary">{a.reason}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Async>
      </Panel>
    </Page>
  );
}

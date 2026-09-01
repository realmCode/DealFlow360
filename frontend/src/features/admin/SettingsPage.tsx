import { SlidersHorizontal } from "lucide-react";
import * as React from "react";
import { dec } from "@/api/money";
import { useAdminMutations, useSettings } from "@/api/queries";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Button, ErrorState, FormField, GovNote, NumericInput, Panel, PanelHead,
  SectionLabel, Skeleton, toast,
} from "@/design-system";

/**
 * Governance tuning.
 *
 * This is the screen that proves routing is not hardcoded: changing a weight
 * here visibly changes which quotes escalate to Finance. Each field explains
 * what it does in the risk formula rather than just naming itself.
 */
const GROUPS = [
  {
    title: "Blended risk weights",
    hint: "Each component is multiplied by its weight, then capped. Raising a weight makes that behaviour matter more.",
    fields: [
      { key: "risk_discount_overage_weight", label: "Discount over ceiling", hint: "Per percentage point above the ceiling, revenue-weighted." },
      { key: "risk_breadth_weight", label: "Violation breadth", hint: "Per line that breaches a ceiling." },
      { key: "risk_margin_weight", label: "Margin shortfall", hint: "Per point below the margin floor." },
      { key: "risk_depth_weight", label: "Discount depth", hint: "Per point of overall blended discount." },
    ],
  },
  {
    title: "Escalation and SLA",
    hint: "Where a quotation stops being a manager decision and becomes a finance one.",
    fields: [
      { key: "finance_escalation_threshold", label: "Finance escalation threshold", hint: "Blended risk at or above this pulls Finance into the chain." },
      { key: "approval_sla_hours", label: "Approval SLA (hours)", hint: "Beyond this, an approval raises an SLA breach signal.", integer: true },
    ],
  },
  {
    title: "Signals",
    hint: "How the Command Center decides something is worth surfacing.",
    fields: [
      { key: "stalled_deal_days", label: "Stalled deal (days)", hint: "No movement for this long raises a stalled-deal signal.", integer: true },
      { key: "discount_anomaly_sigma", label: "Anomaly sensitivity (sigma)", hint: "Standard deviations above a rep's own average before flagging." },
      { key: "discount_anomaly_min_samples", label: "Anomaly minimum history", hint: "Prior quotes needed before a baseline exists.", integer: true },
      { key: "recommendation_min_margin_pct", label: "Recommendation margin floor", hint: "Attach opportunities below this margin are not suggested." },
    ],
  },
] as const;

export function SettingsPage() {
  const query = useSettings();
  const { updateSettings } = useAdminMutations();
  const [draft, setDraft] = React.useState<Record<string, string>>({});

  React.useEffect(() => {
    if (!query.data) return;
    const next: Record<string, string> = {};
    for (const g of GROUPS) {
      for (const f of g.fields) {
        const raw = (query.data as unknown as Record<string, unknown>)[f.key];
        next[f.key] = typeof raw === "number" ? String(raw) : dec(String(raw ?? "0")).toString();
      }
    }
    setDraft(next);
  }, [query.data]);

  const dirty = React.useMemo(() => {
    if (!query.data) return false;
    return GROUPS.some((g) =>
      g.fields.some((f) => {
        const raw = (query.data as unknown as Record<string, unknown>)[f.key];
        const original = typeof raw === "number" ? String(raw) : dec(String(raw ?? "0")).toString();
        return draft[f.key] !== undefined && draft[f.key] !== original;
      }),
    );
  }, [draft, query.data]);

  const save = () => {
    const body: Record<string, unknown> = {};
    for (const g of GROUPS) {
      for (const f of g.fields) {
        const v = draft[f.key];
        if (v === undefined || v === "") continue;
        body[f.key] = "integer" in f && f.integer ? Number(v) : v;
      }
    }
    updateSettings.mutate(body, {
      onSuccess: () => toast.success("Governance updated", "Routing uses the new values on the next evaluation."),
      onError: toast.fromError,
    });
  };

  if (query.isError) {
    return (
      <Page title="Governance">
        <Panel><ErrorState error={query.error} onRetry={query.refetch} /></Panel>
      </Page>
    );
  }

  return (
    <Page
      title="Governance settings"
      subtitle="The constants behind risk scoring, approval escalation and signal detection."
      actions={
        <Button variant="primary" disabled={!dirty} loading={updateSettings.isPending} onClick={save}>
          Save configuration
        </Button>
      }
    >
      <GovNote className="mb-3" title="These values are live" icon={<SlidersHorizontal className="size-3.5" />}>
        Nothing about approval routing is hardcoded. Raise the finance escalation threshold and fewer quotes
        reach Finance; raise a risk weight and more of them do. The change takes effect the next time a version
        is calculated or submitted.
      </GovNote>

      <Async query={query} skeleton={<div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-48 w-full rounded-lg" />)}</div>}>
        {() => (
          <div className="grid gap-3 lg:grid-cols-3">
            {GROUPS.map((g) => (
              <Panel key={g.title}>
                <PanelHead dense title={g.title} />
                <div className="p-3.5">
                  <p className="mb-3 text-sm leading-[18px] text-content-muted">{g.hint}</p>
                  <div className="space-y-3">
                    {g.fields.map((f) => (
                      <FormField key={f.key} label={f.label} hint={f.hint}>
                        {(p) => (
                          <NumericInput
                            id={p.id}
                            value={draft[f.key] ?? ""}
                            onValueChange={(v) => setDraft((d) => ({ ...d, [f.key]: v }))}
                          />
                        )}
                      </FormField>
                    ))}
                  </div>
                </div>
              </Panel>
            ))}
          </div>
        )}
      </Async>

      <SectionLabel className="mt-4">
        Changes apply to future evaluations only — decisions already recorded are not rewritten.
      </SectionLabel>
    </Page>
  );
}

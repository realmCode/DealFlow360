import {
  ArrowLeft, ArrowRight, Ban, CheckCircle2, CircleAlert, FileWarning, Lock, ShieldOff, Unlock,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { dec, formatDateTime, formatRelative } from "@/api/money";
import { useImpact, useQuote, useVersion, useVersionApproval } from "@/api/queries";
import type { ChangeRead, MaterialChangeRead } from "@/api/types";
import { Page } from "@/app/shells/InternalShell";
import {
  ApprovalStatusBadge, Button, Delta, ErrorState, GovNote, Money, Panel, PanelHead, Percent,
  SEVERITY, SectionLabel, Score, SeverityBadge, Skeleton, VersionStatusBadge,
} from "@/design-system";
import { cn } from "@/lib/cn";

/**
 * The stale-approval experience.
 *
 * This is the screen the product exists for. It tells one story top to bottom:
 *
 *   approved -> customer changed terms -> material change -> approval
 *   invalidated -> confirmation blocked -> re-approval -> confirmation
 *
 * Every element is a field the Decision Fabric returned. The narrative is real.
 */

const STAGES = [
  { id: "approved", label: "Approved", icon: CheckCircle2 },
  { id: "changed", label: "Terms changed", icon: FileWarning },
  { id: "material", label: "Material change", icon: CircleAlert },
  { id: "invalidated", label: "Approval invalidated", icon: ShieldOff },
  { id: "blocked", label: "Confirmation blocked", icon: Lock },
  { id: "reapproval", label: "Re-approval", icon: Unlock },
  { id: "confirmed", label: "Confirmation", icon: CheckCircle2 },
];

function StaleNarrative({ reached }: { reached: number }) {
  return (
    <ol className="flex flex-wrap items-stretch gap-y-3" aria-label="What happened to this approval">
      {STAGES.map((s, i) => {
        const done = i < reached;
        const active = i === reached - 1;
        const Icon = s.icon;
        const color = done
          ? active
            ? "var(--risk-critical)"
            : "var(--ink-500)"
          : "var(--ink-300)";
        return (
          <li key={s.id} className="flex min-w-0 flex-1 items-center gap-2">
            <div className="flex min-w-0 flex-col items-center gap-1 px-1">
              <span
                className={cn(
                  "flex size-8 shrink-0 items-center justify-center rounded-lg border-2 transition-all duration-base",
                  active && "animate-rail-pulse",
                )}
                style={{
                  borderColor: color,
                  background: active ? "var(--risk-critical)" : done ? "var(--ink-100)" : "transparent",
                  color: active ? "#fff" : color,
                  boxShadow: active ? "0 0 0 5px var(--risk-critical-bg)" : undefined,
                }}
              >
                <Icon className="size-4" />
              </span>
              <span
                className={cn(
                  "text-center font-ui text-2xs font-semibold uppercase leading-tight tracking-wide",
                  active ? "text-[var(--risk-critical)]" : done ? "text-content-secondary" : "text-content-faint",
                )}
              >
                {s.label}
              </span>
            </div>
            {i < STAGES.length - 1 ? (
              <span
                aria-hidden
                className="mb-4 h-[2px] min-w-3 flex-1 rounded-full"
                style={{ background: i < reached - 1 ? "var(--ink-400)" : "var(--ink-200)" }}
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

/** One changed field, old -> new, with the engine's own reason. */
function ChangeRow({ change, material }: { change: ChangeRead; material?: MaterialChangeRead }) {
  const isMoney = ["total_revenue", "net_revenue", "margin", "total_cost"].includes(change.field);
  const isPct = change.field.includes("pct");
  const tone = material ? SEVERITY[material.severity] : undefined;

  const render = (val: unknown) => {
    if (val === null || val === undefined) return <span className="text-content-faint">—</span>;
    const str = String(val);
    if (isMoney) return <Money value={str} />;
    if (isPct) return <Percent value={str} dp={4} />;
    return <span className="num">{str}</span>;
  };

  return (
    <div className="relative border-b border-line/70 py-3 pl-4 pr-3 last:border-b-0">
      {tone ? <span aria-hidden className="absolute inset-y-0 left-0 w-[3px]" style={{ background: tone.fg }} /> : null}

      <div className="flex flex-wrap items-center gap-2">
        <span className="font-ui text-sm font-semibold text-content">{change.subject}</span>
        <span className="rounded-sm bg-ink-100 px-1.5 py-0.5 font-ui text-2xs uppercase tracking-wide text-content-muted">
          {change.field.replace(/_/g, " ")}
        </span>
        {material ? <SeverityBadge value={material.severity} size="sm" /> : (
          <span className="text-2xs uppercase tracking-wide text-content-faint">not material</span>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-3">
        <div className="rounded-md border border-line bg-surface-sunken px-2.5 py-1.5">
          <div className="micro">Was</div>
          <div className="text-sm text-content-secondary line-through decoration-content-faint/60">
            {render(change.old_value)}
          </div>
        </div>
        <ArrowRight aria-hidden className="size-4 shrink-0 text-content-faint" />
        <div
          className="rounded-md border px-2.5 py-1.5"
          style={{ borderColor: tone ? `${tone.fg}44` : "var(--line)", background: tone ? tone.bg : "var(--surface)" }}
        >
          <div className="micro">Now</div>
          <div className="text-sm font-semibold" style={{ color: tone?.fg }}>
            {render(change.new_value)}
          </div>
        </div>
        {change.old_value && change.new_value && (isMoney || isPct) ? (
          <div>
            <div className="micro">Change</div>
            <Delta from={String(change.old_value)} to={String(change.new_value)} kind={isMoney ? "money" : "pct"} />
          </div>
        ) : null}
      </div>

      {material ? (
        <p className="mt-2 text-sm leading-[19px] text-content-secondary">{material.reason}</p>
      ) : null}
    </div>
  );
}

export function ImpactPage() {
  const { quoteId, versionId } = useParams<{ quoteId: string; versionId: string }>();
  const quote = useQuote(quoteId);
  const version = useVersion(versionId);
  const previous = useVersion(version.data?.parent_version_id ?? undefined);
  const impact = useImpact(versionId);
  const approval = useVersionApproval(versionId);

  if (impact.isPending || version.isPending) {
    return (
      <Page title={<Skeleton className="h-7 w-64" />}>
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="mt-3 h-72 w-full rounded-lg" />
      </Page>
    );
  }
  if (impact.isError) {
    return (
      <Page title="Version impact">
        <Panel><ErrorState error={impact.error} onRetry={impact.refetch} /></Panel>
      </Page>
    );
  }

  const im = impact.data!;
  const v = version.data!;
  const prev = previous.data;
  const stale = im.stale_decisions ?? [];
  const materials = im.material_changes ?? [];
  const materialByField = new Map(materials.map((mc) => [`${mc.field}:${mc.subject}`, mc]));
  const req = approval.data?.approval_request;

  const isBlocked = Boolean(im.blocks_confirmation);
  const reApproved = stale.length > 0 && req?.status === "APPROVED";
  const confirmed = v.status === "CONFIRMED";

  const reached = confirmed ? 7 : reApproved ? 6 : isBlocked ? 5 : stale.length > 0 ? 4 : materials.length > 0 ? 3 : im.changes?.length ? 2 : 1;

  return (
    <Page
      title={
        <span className="flex flex-wrap items-center gap-2.5">
          <span>Version impact</span>
          <span className="num text-content-muted">{quote.data?.quote_number}</span>
          <VersionStatusBadge value={v.status} />
        </span>
      }
      subtitle={
        <Link to={`/quotes/${quoteId}`} className="inline-flex items-center gap-1 hover:text-content">
          <ArrowLeft className="size-3.5" /> Back to the quotation
        </Link>
      }
      actions={
        req && isBlocked ? (
          <Button variant="primary" icon={<ArrowRight className="size-3.5" />} asChild>
            <Link to={`/approvals/${req.id}`}>Go to re-approval</Link>
          </Button>
        ) : null
      }
    >
      {/* -- headline ------------------------------------------------------- */}
      <Panel
        rail={isBlocked ? "var(--risk-critical)" : "var(--policy-passed)"}
        className={cn("mb-3", isBlocked && "bg-[var(--risk-critical-bg)]/30")}
      >
        <div className="p-4">
          <div className="flex flex-wrap items-start gap-3">
            {isBlocked ? (
              <Ban aria-hidden className="mt-0.5 size-6 shrink-0 text-[var(--risk-critical)]" />
            ) : (
              <CheckCircle2 aria-hidden className="mt-0.5 size-6 shrink-0 text-[var(--policy-passed)]" />
            )}
            <div className="min-w-0 flex-1">
              <h2 className="font-ui text-xl font-semibold tracking-tight text-content">
                {isBlocked
                  ? "This quotation changed after approval. The previous approval is no longer valid."
                  : im.has_material_change
                    ? "This version contains material changes."
                    : "No material change detected on this version."}
              </h2>
              {im.explanation?.summary ? (
                <p className="mt-1.5 text-md leading-relaxed text-content-secondary">{im.explanation.summary}</p>
              ) : null}
            </div>
          </div>

          <div className="mt-5 border-t border-line/70 pt-4">
            <StaleNarrative reached={reached} />
          </div>
        </div>
      </Panel>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-3">
          {/* -- side-by-side versions ----------------------------------- */}
          <Panel>
            <PanelHead
              title="Version comparison"
              subtitle={prev ? `v${prev.version_number} superseded by v${v.version_number}` : `Version ${v.version_number}`}
            />
            <div className="grid gap-px bg-line sm:grid-cols-2">
              {[
                { label: `Version ${prev?.version_number ?? "\u2014"}`, ver: prev, muted: true },
                { label: `Version ${v.version_number}`, ver: v, muted: false },
              ].map((side) => (
                <div key={side.label} className={cn("bg-surface p-4", side.muted && "bg-surface-sunken")}>
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <span className="font-ui text-sm font-semibold text-content">{side.label}</span>
                    {side.ver ? <VersionStatusBadge value={side.ver.status} size="sm" /> : null}
                  </div>
                  {side.ver ? (
                    <dl className="space-y-1.5">
                      {[
                        ["Net revenue", <Money key="a" value={side.ver.net_revenue} currency={side.ver.currency} />],
                        ["Margin", <Money key="b" value={side.ver.margin} currency={side.ver.currency} />],
                        ["Margin %", <Percent key="c" value={side.ver.margin_pct} />],
                        ["Effective discount", <Percent key="d" value={side.ver.effective_discount_pct} />],
                        ["Blended risk", <Score key="e" value={side.ver.blended_risk_score ?? "0"} dp={2} />],
                      ].map(([label, node]) => (
                        <div key={label as string} className="flex items-baseline justify-between gap-3">
                          <dt className="text-sm text-content-muted">{label}</dt>
                          <dd className={cn("text-sm", side.muted ? "text-content-secondary" : "font-semibold text-content")}>
                            {node}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  ) : (
                    <p className="text-sm text-content-muted">
                      This is the first version — there is nothing to compare against.
                    </p>
                  )}
                </div>
              ))}
            </div>

            {prev ? (
              <div className="grid grid-cols-2 gap-px border-t border-line bg-line sm:grid-cols-4">
                {[
                  { label: "Revenue", from: prev.net_revenue, to: v.net_revenue, kind: "money" as const },
                  { label: "Margin", from: prev.margin, to: v.margin, kind: "money" as const },
                  { label: "Margin %", from: prev.margin_pct, to: v.margin_pct, kind: "pct" as const },
                  { label: "Risk", from: prev.blended_risk_score ?? "0", to: v.blended_risk_score ?? "0", kind: "score" as const },
                ].map((d) => (
                  <div key={d.label} className="bg-surface px-3 py-2.5">
                    <div className="micro">{d.label} change</div>
                    <div className="mt-0.5 font-ui text-md">
                      <Delta from={d.from} to={d.to} kind={d.kind} currency={v.currency} />
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </Panel>

          {/* -- changed fields -------------------------------------------- */}
          <Panel>
            <PanelHead
              title="What changed"
              subtitle={`${im.changes?.length ?? 0} detected \u00b7 ${materials.length} material`}
            />
            {(im.changes?.length ?? 0) === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-content-muted">
                No field-level differences were detected against the previous version.
              </p>
            ) : (
              <div>
                {im.changes!.map((c, i) => (
                  <ChangeRow
                    key={`${c.field}-${c.subject}-${i}`}
                    change={c}
                    material={materialByField.get(`${c.field}:${c.subject}`)}
                  />
                ))}
              </div>
            )}
          </Panel>

          {/* -- causal chain ---------------------------------------------- */}
          {im.explanation?.causal_chain?.length ? (
            <Panel>
              <PanelHead title="Why the engine reached that conclusion" />
              <ol className="space-y-0 p-4">
                {im.explanation.causal_chain.map((step: string, i: number) => (
                  <li key={i} className="relative flex gap-3 pb-3 last:pb-0">
                    {i < im.explanation!.causal_chain!.length - 1 ? (
                      <span aria-hidden className="absolute left-[11px] top-6 bottom-0 w-px bg-line" />
                    ) : null}
                    <span className="num relative z-10 flex size-6 shrink-0 items-center justify-center rounded-full bg-ink-100 text-2xs font-semibold text-content-muted">
                      {i + 1}
                    </span>
                    <p className="pt-1 text-sm leading-[19px] text-content-secondary">{step}</p>
                  </li>
                ))}
              </ol>
            </Panel>
          ) : null}
        </div>

        {/* -- rail ----------------------------------------------------------- */}
        <div className="min-w-0 space-y-3">
          {isBlocked ? (
            <Panel rail="var(--risk-critical)">
              <div className="p-4">
                <SectionLabel>Required next action</SectionLabel>
                <p className="font-ui text-md font-semibold text-content">
                  Re-approve version {v.version_number}
                </p>
                <p className="mt-1 text-sm leading-[19px] text-content-secondary">
                  The customer cannot confirm this quotation while an approval is stale. Approving the current
                  version clears the block.
                </p>
                {req ? (
                  <Button variant="danger" className="mt-3 w-full" asChild icon={<ArrowRight className="size-3.5" />}>
                    <Link to={`/approvals/${req.id}`}>Open the approval</Link>
                  </Button>
                ) : null}
              </div>
            </Panel>
          ) : null}

          {stale.length > 0 ? (
            <Panel>
              <PanelHead dense icon={<ShieldOff className="size-4" />} title="Invalidated approvals" />
              <ul className="divide-y divide-line/70">
                {stale.map((s) => (
                  <li key={s.approval_request_id} className="px-3.5 py-3">
                    <div className="flex items-center gap-2">
                      <span className="rounded-sm bg-[var(--risk-critical-bg)] px-1.5 py-0.5 font-ui text-2xs font-semibold uppercase tracking-wide text-[var(--risk-critical)]">
                        was {s.previous_decision}
                      </span>
                      <span className="ml-auto text-xs text-content-faint">{formatRelative(s.decided_at)}</span>
                    </div>
                    <p className="mt-1.5 text-sm leading-[19px] text-content-secondary">{s.reason}</p>
                    {s.decided_by ? (
                      <p className="mt-1 text-xs text-content-faint">Originally approved by {s.decided_by}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </Panel>
          ) : null}

          {req ? (
            <Panel>
              <PanelHead dense title="Current approval" />
              <div className="p-3.5">
                <div className="flex items-center justify-between gap-2">
                  <ApprovalStatusBadge value={req.status} />
                  <Button size="xs" variant="ghost" asChild>
                    <Link to={`/approvals/${req.id}`}>Open</Link>
                  </Button>
                </div>
                <ol className="mt-3 space-y-1.5">
                  {req.steps?.map((s) => (
                    <li key={s.sequence} className="flex items-center gap-2 text-sm">
                      <span className="num w-4 text-content-faint">{s.sequence}</span>
                      <span className="min-w-0 flex-1 truncate text-content-secondary">{s.level.replace(/_/g, " ")}</span>
                      <span className="shrink-0 text-xs text-content-muted">{s.status.toLowerCase().replace(/_/g, " ")}</span>
                    </li>
                  ))}
                </ol>
                {req.stale_reason ? (
                  <p className="mt-2 border-t border-line pt-2 text-xs text-content-faint">{req.stale_reason}</p>
                ) : null}
              </div>
            </Panel>
          ) : null}

          {(im.required_approvals?.length ?? 0) > 0 ? (
            <Panel rail="var(--gov-500)">
              <PanelHead dense title="Approval this version needs" />
              <div className="space-y-2 p-3.5">
                {im.required_approvals!.map((a) => (
                  <GovNote key={a.type} title={a.type.replace(/_/g, " ")}>{a.reason}</GovNote>
                ))}
              </div>
            </Panel>
          ) : null}

          {(im.attention_items?.length ?? 0) > 0 ? (
            <Panel>
              <PanelHead dense title="Signals raised" />
              <ul className="divide-y divide-line/70">
                {im.attention_items!.map((a, i) => (
                  <li key={i} className="px-3.5 py-2.5">
                    <div className="flex items-center gap-2">
                      <SeverityBadge value={a.severity} size="sm" />
                      <span className="min-w-0 truncate font-ui text-xs font-semibold text-content">{a.title}</span>
                    </div>
                    <p className="mt-1 text-sm leading-[18px] text-content-secondary">{a.impact}</p>
                  </li>
                ))}
              </ul>
            </Panel>
          ) : null}

          {(im.affected_entities?.length ?? 0) > 0 ? (
            <Panel>
              <PanelHead dense title="Affected downstream" />
              <ul className="divide-y divide-line/70">
                {(im.affected_entities as { type?: string; id?: string; reason?: string }[]).map((e, i) => (
                  <li key={e.id ?? i} className="px-3.5 py-2.5">
                    <div className="micro">{(e.type ?? "entity").replace(/_/g, " ")}</div>
                    <p className="mt-0.5 text-sm leading-[18px] text-content-secondary">{e.reason}</p>
                  </li>
                ))}
              </ul>
            </Panel>
          ) : null}

          <p className="px-1 text-2xs text-content-faint">
            Evaluated {formatDateTime(im.evaluated_at)} &middot; blended risk now{" "}
            <span className="num">{dec(v.blended_risk_score ?? "0").toFixed(2)}</span>
          </p>
        </div>
      </div>
    </Page>
  );
}

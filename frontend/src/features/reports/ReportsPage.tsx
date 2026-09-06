import { BarChart3, Download } from "lucide-react";
import * as React from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis,
} from "recharts";
import { download } from "@/api/client";
import { dec, formatAmount } from "@/api/money";
import { useReport, useSalesTeams } from "@/api/queries";
import type {
  ApprovalStatusReport, DiscountReport, PipelineReport, ProductReport, SalesPerformanceReport,
} from "@/api/types";
import { useAuth } from "@/app/auth";
import { Page } from "@/app/shells/InternalShell";
import {
  APPROVAL_STATUS, Async, Button, DEAL_STAGE, Metric, Money, Panel, PanelHead, Percent,
  Score, SectionLabel, Select, Skeleton, TabPanel, Tabs, toast,
} from "@/design-system";

const PERIODS = [
  { value: "all", label: "All time" },
  { value: "month", label: "This month" },
  { value: "quarter", label: "This quarter" },
  { value: "year", label: "This year" },
];

const REPORTS = [
  { value: "pipeline", label: "Pipeline" },
  { value: "sales-performance", label: "Sales performance" },
  { value: "discounts", label: "Discounts" },
  { value: "products", label: "Products" },
  { value: "approval-status", label: "Approvals" },
];

function ExportBar({ report, params }: { report: string; params: Record<string, string> }) {
  const [busy, setBusy] = React.useState<string | null>(null);
  const go = async (format: string) => {
    setBusy(format);
    try {
      const { blob, filename } = await download(`/reports/${report}/export`, { ...params, format });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Export downloaded", filename);
    } catch (e) {
      toast.fromError(e);
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="flex items-center gap-1">
      {["csv", "xlsx", "pdf"].map((f) => (
        <Button key={f} size="xs" variant="ghost" loading={busy === f} icon={<Download className="size-3" />} onClick={() => go(f)}>
          {f.toUpperCase()}
        </Button>
      ))}
    </div>
  );
}

const chartAxis = { fontSize: 11, fill: "var(--text-muted)" };
const tipStyle = { borderRadius: 8, border: "1px solid var(--line)", fontSize: 12 };

const stageTone = (key: string) =>
  (DEAL_STAGE as Record<string, { fg: string; bg: string; label: string }>)[key] ?? {
    fg: "var(--accent-500)", bg: "var(--accent-100)", label: key,
  };
const statusTone = (key: string) =>
  (APPROVAL_STATUS as Record<string, { fg: string; bg: string; label: string }>)[key] ?? {
    fg: "var(--ink-500)", bg: "var(--ink-100)", label: key,
  };

/** `by_stage` / `by_status` arrive as objects keyed by the enum value. */
const entries = (o: Record<string, Record<string, unknown>> | undefined) =>
  Object.entries(o ?? {}).map(([key, v]) => ({ key, ...v }));

const th = (_h: string, right: boolean) =>
  `h-8 px-3 font-ui text-2xs font-semibold uppercase tracking-wider text-content-faint${right ? " text-right" : ""}`;

export function ReportsPage() {
  const { user } = useAuth();
  const [tab, setTab] = React.useState("pipeline");
  const [period, setPeriod] = React.useState("all");
  const [team, setTeam] = React.useState("");
  const teams = useSalesTeams(user?.role === "ADMIN");

  const params: Record<string, string> = { period, ...(team ? { team_id: team } : {}) };

  const pipeline = useReport<PipelineReport>("pipeline", params, tab === "pipeline");
  const perf = useReport<SalesPerformanceReport>("sales-performance", params, tab === "sales-performance");
  const discounts = useReport<DiscountReport>("discounts", params, tab === "discounts");
  const products = useReport<ProductReport>("products", params, tab === "products");
  const approvals = useReport<ApprovalStatusReport>("approval-status", params, tab === "approval-status");

  return (
    <Page
      title="Reports"
      subtitle="Sales trends, discount behaviour, catalogue performance and approval bottlenecks."
      actions={
        <>
          <Select size="sm" className="w-36" value={period} onValueChange={setPeriod} options={PERIODS} ariaLabel="Period" />
          {teams.data?.length ? (
            <Select
              size="sm" className="w-44" value={team} onValueChange={setTeam} ariaLabel="Sales team"
              placeholder="All teams"
              options={[{ value: "", label: "All teams" }, ...teams.data.map((t) => ({ value: t.id, label: t.name }))]}
            />
          ) : null}
        </>
      }
    >
      <Tabs value={tab} onValueChange={setTab} tabs={REPORTS}>
        {/* -- pipeline ------------------------------------------------------ */}
        <TabPanel value="pipeline" className="pt-3">
          <Async query={pipeline} skeleton={<Skeleton className="h-72 w-full rounded-lg" />}>
            {(d) => {
              const stages = entries(d.by_stage as never) as { key: string; count: number; expected_value: string }[];
              return (
                <div className="space-y-3">
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                    <Panel className="px-3.5 py-2.5"><Metric label="Total deals" size="lg">{d.total_deals}</Metric></Panel>
                    <Panel className="px-3.5 py-2.5"><Metric label="Won" size="lg" tone="var(--policy-passed)">{d.won_count}</Metric></Panel>
                    <Panel className="px-3.5 py-2.5"><Metric label="Lost" size="lg" tone={d.lost_count ? "var(--policy-violated)" : undefined}>{d.lost_count}</Metric></Panel>
                    <Panel className="px-3.5 py-2.5"><Metric label="Win rate" size="lg"><Percent value={d.win_rate_pct} dp={1} /></Metric></Panel>
                  </div>

                  <Panel>
                    <PanelHead icon={<BarChart3 className="size-4" />} title="Expected value by stage" actions={<ExportBar report="pipeline" params={params} />} />
                    <div className="p-4">
                      <div className="h-64 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={stages.map((s) => ({ name: stageTone(s.key).label, value: dec(s.expected_value).toNumber() }))}>
                            <CartesianGrid strokeDasharray="2 4" stroke="var(--line)" vertical={false} />
                            <XAxis dataKey="name" tick={chartAxis} axisLine={{ stroke: "var(--line)" }} tickLine={false} />
                            <YAxis tick={chartAxis} axisLine={false} tickLine={false} width={72} tickFormatter={(v: number) => formatAmount(String(v), 0)} />
                            <RTooltip cursor={{ fill: "var(--accent-50)" }} contentStyle={tipStyle} formatter={(v: number) => formatAmount(String(v))} />
                            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                              {stages.map((s) => <Cell key={s.key} fill={stageTone(s.key).fg} />)}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                      <div className="mt-3 grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
                        {stages.map((s) => (
                          <div key={s.key} className="rounded-md border border-line px-3 py-2">
                            <div className="micro">{stageTone(s.key).label}</div>
                            <div className="mt-0.5"><Money value={s.expected_value} className="text-md font-semibold" /></div>
                            <div className="num text-xs text-content-muted">{s.count} deals</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </Panel>
                </div>
              );
            }}
          </Async>
        </TabPanel>

        {/* -- sales performance ---------------------------------------------- */}
        <TabPanel value="sales-performance" className="pt-3">
          <Async query={perf} skeleton={<Skeleton className="h-64 w-full rounded-lg" />}>
            {(d) => (
              <div className="space-y-3">
                <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
                  {[
                    ["Net revenue", <Money key="a" value={d.totals.net_revenue} />],
                    ["Margin", <Money key="b" value={d.totals.margin} />],
                    ["Margin %", <Percent key="c" value={d.totals.margin_pct} dp={1} />],
                    ["Effective discount", <Percent key="d" value={d.totals.effective_discount_pct} dp={1} />],
                    ["Quotes", <span key="e" className="num">{d.totals.quote_count}</span>],
                    ["Win rate", <Percent key="f" value={d.totals.win_rate_pct} dp={0} />],
                  ].map(([label, node]) => (
                    <Panel key={label as string} className="px-3.5 py-2.5">
                      <Metric label={label as string} size="md">{node}</Metric>
                    </Panel>
                  ))}
                </div>

                <Panel>
                  <PanelHead title={`Grouped by ${d.group_by}`} actions={<ExportBar report="sales-performance" params={params} />} />
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-left">
                      <thead>
                        <tr className="border-b border-line bg-surface-sunken">
                          {["Group", "Quotes", "Net revenue", "Margin", "Margin %", "Avg discount", "Avg risk", "Won", "Win rate"].map((h, i) => (
                            <th key={h} className={th(h, i > 0)}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {d.rows.map((r) => (
                          <tr key={r.group_key} className="border-b border-line/60">
                            <td className="px-3 py-2 font-medium text-content">{r.group_label}</td>
                            <td className="num px-3 py-2 text-right">{r.quote_count}</td>
                            <td className="px-3 py-2 text-right"><Money value={r.net_revenue} className="font-semibold" /></td>
                            <td className="px-3 py-2 text-right"><Money value={r.margin} /></td>
                            <td className="px-3 py-2 text-right"><Percent value={r.margin_pct} dp={1} /></td>
                            <td className="px-3 py-2 text-right"><Percent value={r.avg_discount_pct} dp={1} /></td>
                            <td className="px-3 py-2 text-right"><Score value={r.avg_blended_risk} dp={1} /></td>
                            <td className="num px-3 py-2 text-right">{r.won_count}</td>
                            <td className="px-3 py-2 text-right"><Percent value={r.win_rate_pct} dp={0} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              </div>
            )}
          </Async>
        </TabPanel>

        {/* -- discounts -------------------------------------------------------- */}
        <TabPanel value="discounts" className="pt-3">
          <Async query={discounts} skeleton={<Skeleton className="h-64 w-full rounded-lg" />}>
            {(d) => (
              <div className="space-y-3">
                <Panel>
                  <PanelHead title="Discount behaviour per rep" actions={<ExportBar report="discounts" params={params} />} />
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-left">
                      <thead>
                        <tr className="border-b border-line bg-surface-sunken">
                          {["Rep", "Versions", "Average", "Min", "Max", "Std dev", "Avg margin", "Needed approval", "Total given"].map((h, i) => (
                            <th key={h} className={th(h, i > 0)}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {d.by_rep.map((r) => (
                          <tr key={r.rep_user_id ?? r.rep_name} className="border-b border-line/60">
                            <td className="px-3 py-2 font-medium text-content">{r.rep_name}</td>
                            <td className="num px-3 py-2 text-right">{r.version_count}</td>
                            <td className="px-3 py-2 text-right"><Percent value={r.avg_discount_pct} dp={2} className="font-semibold" /></td>
                            <td className="px-3 py-2 text-right"><Percent value={r.min_discount_pct} dp={1} className="text-content-muted" /></td>
                            <td className="px-3 py-2 text-right"><Percent value={r.max_discount_pct} dp={1} /></td>
                            <td className="px-3 py-2 text-right"><Score value={r.stdev_discount_pct} dp={2} className="text-content-muted" /></td>
                            <td className="px-3 py-2 text-right"><Percent value={r.avg_margin_pct} dp={1} /></td>
                            <td className="num px-3 py-2 text-right">{r.required_approval_count}</td>
                            <td className="px-3 py-2 text-right"><Money value={r.total_discount_given} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>

                <Panel>
                  <PanelHead title="Distribution by discount band" subtitle="How many quote versions land in each band" />
                  <div className="p-4">
                    <div className="h-56 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={d.distribution.map((h) => ({ name: h.band === "0" ? "None" : `${h.band}%`, value: h.count }))}>
                          <CartesianGrid strokeDasharray="2 4" stroke="var(--line)" vertical={false} />
                          <XAxis dataKey="name" tick={chartAxis} axisLine={{ stroke: "var(--line)" }} tickLine={false} />
                          <YAxis tick={chartAxis} axisLine={false} tickLine={false} allowDecimals={false} width={32} />
                          <RTooltip cursor={{ fill: "var(--accent-50)" }} contentStyle={tipStyle} />
                          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                            {d.distribution.map((h, i) => (
                              <Cell key={h.band} fill={i >= 5 ? "var(--risk-high)" : i >= 4 ? "var(--gov-500)" : "var(--accent-500)"} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </Panel>
              </div>
            )}
          </Async>
        </TabPanel>

        {/* -- products ----------------------------------------------------------- */}
        <TabPanel value="products" className="pt-3">
          <Async query={products} skeleton={<Skeleton className="h-64 w-full rounded-lg" />}>
            {(d) => (
              <div className="space-y-3">
                {([
                  ["Best selling", d.best_selling],
                  ["Most discounted", d.most_discounted],
                  ["Highest margin contribution", d.highest_margin_contribution],
                ] as const).map(([title, rows], idx) => (
                  <Panel key={title}>
                    <PanelHead title={title} actions={idx === 0 ? <ExportBar report="products" params={params} /> : undefined} />
                    <div className="overflow-x-auto">
                      <table className="w-full border-collapse text-left">
                        <thead>
                          <tr className="border-b border-line bg-surface-sunken">
                            {["Product", "Units", "Orders", "Net revenue", "Margin", "Margin %", "Avg discount"].map((h, i) => (
                              <th key={h} className={th(h, i > 0)}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {(rows ?? []).map((r) => (
                            <tr key={r.product_id} className="border-b border-line/60">
                              <td className="px-3 py-2">
                                <div className="font-medium text-content">{r.name}</div>
                                <div className="num text-2xs text-content-faint">{r.sku} &middot; {r.category}</div>
                              </td>
                              <td className="num px-3 py-2 text-right">{dec(r.units_sold).toFixed(0)}</td>
                              <td className="num px-3 py-2 text-right">{r.order_count}</td>
                              <td className="px-3 py-2 text-right"><Money value={r.net_revenue} className="font-semibold" /></td>
                              <td className="px-3 py-2 text-right"><Money value={r.margin} /></td>
                              <td className="px-3 py-2 text-right"><Percent value={r.margin_pct} dp={1} /></td>
                              <td className="px-3 py-2 text-right"><Percent value={r.avg_discount_pct} dp={1} /></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Panel>
                ))}
              </div>
            )}
          </Async>
        </TabPanel>

        {/* -- approvals ------------------------------------------------------------ */}
        <TabPanel value="approval-status" className="pt-3">
          <Async query={approvals} skeleton={<Skeleton className="h-48 w-full rounded-lg" />}>
            {(d) => {
              const rows = entries(d.by_status as never) as {
                key: string; count: number; total_value: string;
                avg_blended_risk: string; avg_hours_to_decision: string | null;
              }[];
              return (
                <div className="space-y-3">
                  <Panel>
                    <PanelHead
                      title="Approval pipeline"
                      subtitle={`${d.total_requests} requests in the period`}
                      actions={<ExportBar report="approval-status" params={params} />}
                    />
                    <div className="grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-3">
                      {rows.map((r) => {
                        const tone = statusTone(r.key);
                        return (
                          <div key={r.key} className="relative bg-surface px-4 py-3">
                            <span aria-hidden className="absolute inset-y-0 left-0 w-[3px]" style={{ background: r.count ? tone.fg : "var(--ink-200)" }} />
                            <div className="micro">{tone.label}</div>
                            <div className="mt-0.5 flex items-baseline gap-2">
                              <span className="num font-ui text-2xl font-semibold" style={{ color: r.count ? tone.fg : "var(--ink-400)" }}>
                                {r.count}
                              </span>
                              <Money value={r.total_value} className="text-sm text-content-muted" />
                            </div>
                            <div className="mt-1 flex gap-4 text-xs text-content-muted">
                              <span>risk <Score value={r.avg_blended_risk} dp={1} /></span>
                              <span>
                                {r.avg_hours_to_decision !== null
                                  ? <>decided in <Score value={r.avg_hours_to_decision} dp={2} />h</>
                                  : "not yet decided"}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </Panel>
                  <SectionLabel>
                    Stale requests are approvals invalidated by a change after the decision — they are counted separately
                    because they represent work that has to be redone.
                  </SectionLabel>
                </div>
              );
            }}
          </Async>
        </TabPanel>
      </Tabs>
    </Page>
  );
}

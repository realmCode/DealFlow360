import {
  ArrowLeft, Lock, Plus, RefreshCw, Send, Trash2, TriangleAlert,
} from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { dec } from "@/api/money";
import { errorHint, errorTitle, isDealFlowError } from "@/api/errors";
import {
  useDeal, useDismissRecommendation, usePolicyResults, useProducts, useQuote,
  useRecommendations, useSettings, useVersion, useVersionMutations,
} from "@/api/queries";
import type { ProductRead, QuoteLineRead, SimulationResult } from "@/api/types";
import { useAuth, useCan } from "@/app/auth";
import {
  Button, ErrorState, GovNote, IconButton, Money, NumericInput, Panel, Percent, Qty,
  Select, Skeleton, TierBadge, toast, VersionStatusBadge,
} from "@/design-system";
import { cn } from "@/lib/cn";
import { IntelligencePanel } from "./IntelligencePanel";

/** A line row with debounced numeric edits so typing does not spam the API. */
function LineRow({
  line, editable, onPatch, onDelete, currency,
}: {
  line: QuoteLineRead;
  editable: boolean;
  onPatch: (body: { quantity?: string; discount_pct?: string }) => void;
  onDelete: () => void;
  currency: string;
}) {
  const [qty, setQty] = React.useState(dec(line.quantity).toString());
  const [disc, setDisc] = React.useState(dec(line.discount_pct).toString());
  const dirty = React.useRef(false);

  // Re-sync when the server sends new authoritative values.
  React.useEffect(() => {
    if (dirty.current) return;
    setQty(dec(line.quantity).toString());
    setDisc(dec(line.discount_pct).toString());
  }, [line.quantity, line.discount_pct]);

  const commit = (patch: { quantity?: string; discount_pct?: string }) => {
    dirty.current = false;
    onPatch(patch);
  };

  return (
    <tr className="border-b border-line/60 transition-colors hover:bg-surface-sunken/60">
      <td className="px-3 py-2">
        <div className="min-w-0">
          <div className="truncate font-medium text-content">{line.description}</div>
          <div className="flex items-center gap-1.5 text-2xs text-content-faint">
            <span className="uppercase tracking-wide">{line.category}</span>
            {line.billing_type === "RECURRING" ? (
              <span className="rounded-xs bg-[var(--state-negotiating-bg)] px-1 font-semibold text-[var(--state-negotiating)]">
                {line.recurring_interval}
              </span>
            ) : null}
          </div>
        </div>
      </td>

      <td className="px-2 py-2 text-right">
        {editable ? (
          <NumericInput
            size="sm" className="w-20" aria-label={`Quantity for ${line.description}`}
            value={qty}
            onValueChange={(v) => { dirty.current = true; setQty(v); }}
            onBlur={() => qty !== "" && dec(qty).greaterThan(0) && commit({ quantity: qty })}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          />
        ) : (
          <Qty value={line.quantity} />
        )}
      </td>

      <td className="px-2 py-2 text-right">
        <Money value={line.unit_list_price} currency={currency} dp={2} className="text-content-secondary" />
      </td>

      <td className="px-2 py-2 text-right">
        {editable ? (
          <NumericInput
            size="sm" className="w-[74px]" suffix="%" aria-label={`Discount for ${line.description}`}
            value={disc}
            onValueChange={(v) => { dirty.current = true; setDisc(v); }}
            onBlur={() => disc !== "" && dec(disc).lte(100) && commit({ discount_pct: disc })}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          />
        ) : (
          <Percent value={line.discount_pct} dp={2} />
        )}
      </td>

      <td className="px-2 py-2 text-right">
        <Money value={line.unit_net_price} currency={currency} dp={2} />
      </td>

      <td className="px-2 py-2 text-right">
        <Money value={line.net_amount} currency={currency} className="font-semibold" />
      </td>

      <td className="px-2 py-2 text-right">
        <MarginPill pct={line.line_margin_pct} />
      </td>

      <td className="w-9 px-1 py-2">
        {editable ? (
          <IconButton
            label={`Remove ${line.description}`}
            size="sm"
            onClick={onDelete}
            className="text-content-faint hover:bg-[var(--policy-violated-bg)] hover:text-[var(--policy-violated)]"
          >
            <Trash2 className="size-3.5" />
          </IconButton>
        ) : null}
      </td>
    </tr>
  );
}

function MarginPill({ pct }: { pct: string | null | undefined }) {
  const v = Number(pct ?? 0);
  const color = v >= 25 ? "var(--margin-healthy)" : v >= 12 ? "var(--margin-thin)" : "var(--margin-breach)";
  return <Percent value={pct} dp={1} className="text-xs font-semibold" style={{ color }} />;
}

export function QuoteBuilderPage() {
  const { quoteId, versionId } = useParams<{ quoteId: string; versionId: string }>();
  const nav = useNavigate();
  const can = useCan();
  const { user } = useAuth();

  const quote = useQuote(quoteId);
  // QuoteRead carries no customer fields; the deal is where tier lives.
  const deal = useDeal(quote.data?.deal_id);
  const version = useVersion(versionId);
  const evaluation = usePolicyResults(versionId);
  const recommendations = useRecommendations(quoteId);
  const settings = useSettings(user?.role === "ADMIN");
  const products = useProducts({ limit: 200, is_active: true });
  const m = useVersionMutations(versionId!, quoteId);
  const dismiss = useDismissRecommendation(quoteId!);

  const [addingProduct, setAddingProduct] = React.useState("");
  const [addQty, setAddQty] = React.useState("1");
  const [addDisc, setAddDisc] = React.useState("0");
  const [orderDiscount, setOrderDiscount] = React.useState("");
  const [simulation, setSimulation] = React.useState<SimulationResult | null>(null);
  const [blocked, setBlocked] = React.useState<unknown>(null);

  const v = version.data;
  const editable = Boolean(v?.is_editable) && can.authorQuotes;

  React.useEffect(() => {
    if (v && orderDiscount === "") setOrderDiscount(dec(v.order_discount_pct).toString());
  }, [v, orderDiscount]);

  if (version.isPending) {
    return (
      <div className="mx-auto max-w-[1600px] px-4 py-5">
        <Skeleton className="h-8 w-72" />
        <div className="mt-4 grid gap-3 xl:grid-cols-[minmax(0,1fr)_400px]">
          <Skeleton className="h-96 w-full rounded-lg" />
          <Skeleton className="h-96 w-full rounded-lg" />
        </div>
      </div>
    );
  }
  if (version.isError) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <Panel><ErrorState error={version.error} onRetry={version.refetch} /></Panel>
      </div>
    );
  }
  if (!v) return null;

  const productList: ProductRead[] = products.data?.items ?? [];
  const currency = v.currency;

  const run = <A,>(fn: { mutate: (a: A, o?: object) => void }, arg: A, ok?: string) =>
    fn.mutate(arg, {
      onSuccess: () => ok && toast.success(ok),
      onError: (e: unknown) => {
        if (isDealFlowError(e) && ["IMMUTABLE_VERSION", "VERSION_NOT_DRAFT", "STALE_APPROVAL"].includes(e.code)) {
          setBlocked(e);
        } else {
          toast.fromError(e);
        }
      },
    } as object);

  return (
    <div className="mx-auto w-full max-w-[1700px] px-3 py-4 lg:px-4">
      {/* -- header -------------------------------------------------------- */}
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            to={`/quotes/${quoteId}`}
            className="inline-flex items-center gap-1 text-sm text-content-muted transition-colors hover:text-content"
          >
            <ArrowLeft className="size-3.5" />
            {quote.data?.quote_number ?? "Quotation"}
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="font-ui text-2xl font-semibold tracking-tight text-content">
              {quote.data?.title ?? "Quote builder"}
            </h1>
            <VersionStatusBadge value={v.status} />
            <span className="text-sm text-content-muted">Version {v.version_number}</span>
            {deal.data?.customer_tier ? <TierBadge tier={deal.data.customer_tier} /> : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="ghost" size="md"
            icon={<RefreshCw className={cn("size-3.5", m.calculate.isPending && "animate-spin")} />}
            loading={m.calculate.isPending}
            onClick={() => run(m.calculate, undefined, "Recalculated")}
          >
            Recalculate
          </Button>
          {editable ? (
            <Button
              variant="primary" size="md" icon={<Send className="size-3.5" />}
              loading={m.submit.isPending}
              disabled={(v.lines ?? []).length === 0}
              onClick={() =>
                m.submit.mutate(undefined, {
                  onSuccess: (impact) => {
                    toast.success(
                      impact.required_approvals?.length ? "Submitted for approval" : "Approved automatically",
                      impact.required_approvals?.length
                        ? `Routed to ${impact.required_approvals.map((a) => a.type.replace(/_/g, " ")).join(" then ")}.`
                        : "This version was inside policy.",
                    );
                    nav(`/quotes/${quoteId}`);
                  },
                  onError: toast.fromError,
                })
              }
            >
              Submit for approval
            </Button>
          ) : (
            <Button variant="secondary" asChild>
              <Link to={`/quotes/${quoteId}`}>Open quotation</Link>
            </Button>
          )}
        </div>
      </div>

      {/* -- locked banner -------------------------------------------------- */}
      {!v.is_editable ? (
        <GovNote
          className="mb-3"
          tone="neutral"
          icon={<Lock className="size-3.5" />}
          title={`This version is ${v.status.replace(/_/g, " ").toLowerCase()} and cannot be edited`}
        >
          Only a DRAFT version accepts line changes. Create a revision from the quotation page to alter the
          commercial terms — the engine will re-run governance on the new version.
        </GovNote>
      ) : null}

      {blocked ? (
        <GovNote className="mb-3" tone="critical" icon={<TriangleAlert className="size-3.5" />} title={errorTitle(blocked)}>
          {errorHint(blocked)}{" "}
          <button type="button" className="underline underline-offset-2" onClick={() => setBlocked(null)}>
            Dismiss
          </button>
        </GovNote>
      ) : null}

      {/* -- split: workspace | intelligence -------------------------------- */}
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="min-w-0 space-y-3">
          <Panel>
            <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
              <div>
                <h2 className="font-ui text-base font-semibold text-content">Line items</h2>
                <p className="text-xs text-content-muted">
                  Discount is checked against each line&rsquo;s own ceiling as soon as it changes — not only at submit.
                </p>
              </div>
              <span className="num shrink-0 text-xs text-content-muted">{(v.lines ?? []).length} lines</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-b border-line bg-surface-sunken">
                    {["Product", "Qty", "List", "Disc.", "Net unit", "Amount", "Margin", ""].map((h, i) => (
                      <th
                        key={h || i}
                        scope="col"
                        className={cn(
                          "h-8 whitespace-nowrap px-3 font-ui text-2xs font-semibold uppercase tracking-wider text-content-faint",
                          i > 0 && i < 7 && "text-right",
                        )}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(v.lines ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-4 py-10 text-center">
                        <p className="font-ui text-md font-medium text-content">No lines yet</p>
                        <p className="mt-1 text-sm text-content-muted">
                          Add a product below. Totals, margin and risk are computed the moment you do.
                        </p>
                      </td>
                    </tr>
                  ) : (
                    (v.lines ?? []).map((line) => (
                      <LineRow
                        key={line.id}
                        line={line}
                        editable={editable}
                        currency={currency}
                        onPatch={(body) => run(m.updateLine, { lineId: line.id, body })}
                        onDelete={() => run(m.deleteLine, line.id, "Line removed")}
                      />
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {editable ? (
              <div className="flex flex-wrap items-end gap-2 border-t border-line bg-surface-sunken px-3 py-2.5">
                <div className="min-w-[220px] flex-1">
                  <label className="micro mb-1 block" htmlFor="add-product">Add product</label>
                  <Select
                    id="add-product"
                    size="sm"
                    value={addingProduct}
                    onValueChange={setAddingProduct}
                    placeholder={products.isPending ? "Loading catalogue\u2026" : "Choose a product"}
                    options={productList.map((p) => ({
                      value: p.id,
                      label: `${p.name}`,
                      hint: p.sku,
                    }))}
                  />
                </div>
                <div>
                  <label className="micro mb-1 block" htmlFor="add-qty">Qty</label>
                  <NumericInput id="add-qty" size="sm" className="w-20" value={addQty} onValueChange={setAddQty} />
                </div>
                <div>
                  <label className="micro mb-1 block" htmlFor="add-disc">Discount</label>
                  <NumericInput id="add-disc" size="sm" className="w-[74px]" suffix="%" value={addDisc} onValueChange={setAddDisc} />
                </div>
                <Button
                  size="sm" variant="secondary" icon={<Plus className="size-3.5" />}
                  disabled={!addingProduct || addQty === "" || dec(addQty).lte(0)}
                  loading={m.addLine.isPending}
                  onClick={() => {
                    run(
                      m.addLine,
                      { product_id: addingProduct, quantity: addQty, discount_pct: addDisc || "0" },
                      "Line added",
                    );
                    setAddingProduct("");
                    setAddQty("1");
                    setAddDisc("0");
                  }}
                >
                  Add line
                </Button>
              </div>
            ) : null}
          </Panel>

          {/* -- order-level discount + totals ------------------------------ */}
          <Panel>
            <div className="grid gap-4 p-4 sm:grid-cols-[220px_minmax(0,1fr)]">
              <div>
                <label className="micro mb-1 block" htmlFor="order-discount">Order-level discount</label>
                <div className="flex items-center gap-2">
                  <NumericInput
                    id="order-discount"
                    className="w-24"
                    suffix="%"
                    value={orderDiscount}
                    disabled={!editable}
                    onValueChange={setOrderDiscount}
                    onBlur={() =>
                      editable &&
                      orderDiscount !== "" &&
                      !dec(orderDiscount).eq(dec(v.order_discount_pct)) &&
                      run(m.setDiscount, orderDiscount, "Order discount updated")
                    }
                  />
                  {dec(v.order_discount_amount).greaterThan(0) ? (
                    <Money value={v.order_discount_amount} currency={currency} className="text-sm text-content-muted" />
                  ) : null}
                </div>
                <p className="mt-1.5 text-2xs leading-[15px] text-content-faint">
                  Compounds with each line discount rather than replacing it.
                </p>
              </div>

              <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-3">
                {[
                  ["Gross", <Money key="g" value={v.gross_revenue} currency={currency} />],
                  ["Discount", <Money key="d" value={v.total_discount} currency={currency} />],
                  ["Effective disc.", <Percent key="e" value={v.effective_discount_pct} dp={2} />],
                  ["Net revenue", <Money key="n" value={v.net_revenue} currency={currency} className="font-semibold" />],
                  ["Cost", <Money key="c" value={v.total_cost} currency={currency} />],
                  ["Tax", <Money key="t" value={v.tax_amount} currency={currency} />],
                ].map(([label, node]) => (
                  <div key={label as string} className="flex items-baseline justify-between gap-2 border-b border-line/60 pb-1">
                    <dt className="text-xs text-content-muted">{label}</dt>
                    <dd className="text-sm">{node}</dd>
                  </div>
                ))}
                <div className="col-span-2 flex items-baseline justify-between gap-2 pt-1 sm:col-span-3">
                  <dt className="font-ui text-sm font-semibold text-content">Margin</dt>
                  <dd className="flex items-baseline gap-2">
                    <Money value={v.margin} currency={currency} className="text-lg font-semibold" />
                    <MarginPill pct={v.margin_pct} />
                  </dd>
                </div>
              </dl>
            </div>
          </Panel>
        </div>

        {/* -- intelligence column ------------------------------------------ */}
        <aside className="min-w-0">
          <div className="xl:sticky xl:top-[104px]">
            <IntelligencePanel
              version={v}
              evaluation={evaluation.data}
              evaluationPending={evaluation.isPending}
              recommendations={recommendations.data}
              escalationThreshold={settings.data?.finance_escalation_threshold}
              editable={editable}
              simulation={simulation}
              simulating={m.simulate.isPending}
              onClearSimulation={() => setSimulation(null)}
              onSimulate={(pct) =>
                m.simulate.mutate(
                  { order_discount_pct: pct },
                  { onSuccess: setSimulation, onError: toast.fromError },
                )
              }
              onAddRecommendation={(productId, qty) =>
                run(m.addLine, { product_id: productId, quantity: qty, discount_pct: "0" })
              }
              onDismissRecommendation={(productId) =>
                dismiss.mutate(productId, {
                  onSuccess: () => toast.info("Recommendation dismissed"),
                  onError: toast.fromError,
                })
              }
            />
          </div>
        </aside>
      </div>
    </div>
  );
}


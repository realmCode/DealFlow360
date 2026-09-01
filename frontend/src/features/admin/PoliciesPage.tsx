import { Plus, Scale } from "lucide-react";
import * as React from "react";
import { dec, sortKey } from "@/api/money";
import { useAdminMutations, usePolicies } from "@/api/queries";
import type { PolicyRead } from "@/api/types";
import { useCan } from "@/app/auth";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Badge, Button, type Column, DataTable, Dialog, EmptyState, FormField, GovNote,
  Input, NumericInput, Panel, PanelHead, SEVERITY, SectionLabel, Select, SeverityBadge,
  Textarea, TierBadge, toast,
} from "@/design-system";

/**
 * The wireframe splits "Discount rules" and "Approval chains" into two screens.
 * They are one concept in the backend: a policy row's `required_action` IS the
 * approval rule. Showing them together is what makes the chain legible.
 */
const TYPE_LABEL: Record<string, string> = {
  CATEGORY_DISCOUNT_CEILING: "Category discount ceiling",
  MIN_MARGIN: "Minimum margin",
  DISCOUNT_AMOUNT_AUTHORITY: "Signing authority",
  PAYMENT_TERMS_LIMIT: "Payment terms limit",
};

const ACTION_TONE: Record<string, { fg: string; bg: string; label: string }> = {
  SALES_MANAGER: { fg: "var(--gov-600)", bg: "var(--gov-100)", label: "Sales manager" },
  FINANCE: { fg: "var(--risk-high)", bg: "var(--risk-high-bg)", label: "Finance" },
  EXECUTIVE: { fg: "var(--risk-critical)", bg: "var(--risk-critical-bg)", label: "Executive" },
};

export function PoliciesPage() {
  const can = useCan();
  const query = usePolicies();
  const { updatePolicy, createPolicy } = useAdminMutations();
  const [editing, setEditing] = React.useState<PolicyRead | "new" | null>(null);

  const policies = query.data ?? [];
  const ceilings = policies.filter((p) => p.policy_type === "CATEGORY_DISCOUNT_CEILING");
  const others = policies.filter((p) => p.policy_type !== "CATEGORY_DISCOUNT_CEILING");

  const columns: Column<PolicyRead>[] = [
    {
      id: "policy",
      header: "Policy",
      sortValue: (p) => p.code,
      cell: (p) => (
        <div>
          <div className="font-medium text-content">{p.name}</div>
          <div className="num text-2xs text-content-faint">{p.code}</div>
        </div>
      ),
    },
    { id: "type", header: "Type", sortValue: (p) => p.policy_type, cell: (p) => <span className="text-xs text-content-secondary">{TYPE_LABEL[p.policy_type] ?? p.policy_type}</span>, hideBelow: "md" },
    {
      id: "scope",
      header: "Applies to",
      cell: (p) => (
        <span className="flex flex-wrap items-center gap-1.5">
          {p.customer_tier ? <TierBadge tier={p.customer_tier} /> : <span className="text-xs text-content-faint">any tier</span>}
          {p.product_category ? (
            <span className="rounded-sm border border-line px-1.5 py-0.5 text-2xs uppercase tracking-wide text-content-muted">
              {p.product_category}
            </span>
          ) : null}
        </span>
      ),
    },
    {
      id: "threshold",
      header: "Threshold",
      align: "right",
      sortValue: (p) => sortKey(p.threshold_value),
      cell: (p) => (
        <span className="num font-semibold">
          {p.comparison === "LTE" ? "\u2264 " : "\u2265 "}
          {dec(p.threshold_value).toFixed(p.unit === "DAYS" ? 0 : 2)}
          {p.unit === "PERCENT" ? "%" : p.unit === "DAYS" ? "d" : ""}
        </span>
      ),
    },
    {
      id: "action",
      header: "Breach routes to",
      cell: (p) =>
        p.required_action ? (
          <Badge size="sm" tone={ACTION_TONE[p.required_action] ?? { fg: "var(--ink-600)", bg: "var(--ink-100)", label: p.required_action }} />
        ) : (
          <span className="text-xs text-content-faint">no approval needed</span>
        ),
    },
    { id: "severity", header: "Severity", cell: (p) => <SeverityBadge value={p.severity} size="sm" />, hideBelow: "lg" },
    { id: "priority", header: "Priority", align: "right", sortValue: (p) => p.priority, cell: (p) => <span className="num text-content-muted">{p.priority}</span>, hideBelow: "xl" },
    {
      id: "active",
      header: "State",
      cell: (p) => (p.is_active ? <Badge size="sm" tone={{ fg: "var(--policy-passed)", bg: "var(--policy-passed-bg)", label: "Active" }} /> : <Badge size="sm" tone={{ fg: "var(--ink-500)", bg: "var(--ink-100)", label: "Off" }} />),
    },
    ...(can.administer
      ? [{ id: "edit", header: "", align: "right" as const, cell: (p: PolicyRead) => <Button size="xs" variant="ghost" onClick={() => setEditing(p)}>Edit</Button> }]
      : []),
  ];

  return (
    <Page
      title="Discount rules and approval chains"
      subtitle="One rule set. A policy's threshold is the discount ceiling; its required action is the approval chain."
      actions={can.administer ? <Button variant="primary" icon={<Plus className="size-3.5" />} onClick={() => setEditing("new")}>New policy</Button> : null}
    >
      <GovNote className="mb-3" title="How a quotation is routed">
        Each line is checked against the most specific ceiling that matches its category and the customer&rsquo;s
        tier. Every breach contributes points to the blended risk score, and the highest{" "}
        <span className="font-semibold">required action</span> across all breaches decides who must approve.
        A quote mixing categories with different ceilings therefore routes to the strictest level any one line
        demands.
      </GovNote>

      <div className="space-y-3">
        <Panel>
          <PanelHead icon={<Scale className="size-4" />} title="Category discount ceilings" subtitle={`${ceilings.length} rules`} />
          <Async query={query} isEmpty={() => ceilings.length === 0} empty={<EmptyState title="No ceilings configured" compact />}>
            {() => <DataTable rows={ceilings} columns={columns} caption="Discount ceilings" getKey={(p) => p.id} rail={(p) => (p.is_active ? SEVERITY[p.severity].fg : "var(--ink-200)")} />}
          </Async>
        </Panel>

        <Panel>
          <PanelHead title="Margin, authority and terms" subtitle={`${others.length} rules`} />
          <Async query={query} isEmpty={() => others.length === 0} empty={<EmptyState title="No other rules configured" compact />}>
            {() => <DataTable rows={others} columns={columns} caption="Other policies" getKey={(p) => p.id} rail={(p) => (p.is_active ? SEVERITY[p.severity].fg : "var(--ink-200)")} />}
          </Async>
        </Panel>
      </div>

      {editing ? (
        <PolicyDialog
          policy={editing === "new" ? null : editing}
          saving={updatePolicy.isPending || createPolicy.isPending}
          onClose={() => setEditing(null)}
          onSave={(body, id) =>
            id
              ? updatePolicy.mutate({ id, body }, { onSuccess: () => { toast.success("Policy updated", "Routing recalculates on the next evaluation."); setEditing(null); }, onError: toast.fromError })
              : createPolicy.mutate(body as never, { onSuccess: () => { toast.success("Policy created"); setEditing(null); }, onError: toast.fromError })
          }
        />
      ) : null}
    </Page>
  );
}

function PolicyDialog({
  policy, onClose, onSave, saving,
}: {
  policy: PolicyRead | null;
  onClose: () => void;
  onSave: (body: Record<string, unknown>, id?: string) => void;
  saving: boolean;
}) {
  const [name, setName] = React.useState(policy?.name ?? "");
  const [description, setDescription] = React.useState(policy?.description ?? "");
  const [threshold, setThreshold] = React.useState(dec(policy?.threshold_value ?? "0").toString());
  const [action, setAction] = React.useState(policy?.required_action ?? "");
  const [priority, setPriority] = React.useState(String(policy?.priority ?? 10));
  const [active, setActive] = React.useState(policy?.is_active ?? true);

  return (
    <Dialog
      open
      onOpenChange={(v) => !v && onClose()}
      title={policy ? `Edit ${policy.code}` : "New policy"}
      description={policy ? TYPE_LABEL[policy.policy_type] : "Define a governance rule"}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary" loading={saving} disabled={!name.trim()}
            onClick={() =>
              onSave(
                {
                  name,
                  description: description || null,
                  threshold_value: threshold,
                  required_action: action || null,
                  priority: Number(priority),
                  is_active: active,
                },
                policy?.id,
              )
            }
          >
            {policy ? "Save" : "Create"}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <FormField label="Name" required>{(p) => <Input {...p} value={name} onChange={(e) => setName(e.target.value)} />}</FormField>
        <FormField label="Description">{(p) => <Textarea {...p} value={description} onChange={(e) => setDescription(e.target.value)} />}</FormField>
        <div className="grid gap-3 sm:grid-cols-3">
          <FormField label="Threshold" required hint={policy?.unit === "PERCENT" ? "percent" : policy?.unit === "DAYS" ? "days" : "amount"}>
            {(p) => <NumericInput id={p.id} value={threshold} onValueChange={setThreshold} />}
          </FormField>
          <FormField label="Breach routes to">
            {(p) => (
              <Select
                id={p.id} value={action} onValueChange={setAction} placeholder="No approval"
                options={[
                  { value: "", label: "No approval needed" },
                  { value: "SALES_MANAGER", label: "Sales manager" },
                  { value: "FINANCE", label: "Finance" },
                  { value: "EXECUTIVE", label: "Executive" },
                ]}
              />
            )}
          </FormField>
          <FormField label="Priority" hint="Most specific wins">
            {(p) => <NumericInput id={p.id} value={priority} onValueChange={setPriority} />}
          </FormField>
        </div>
        <SectionLabel>State</SectionLabel>
        <Select
          value={active ? "on" : "off"}
          onValueChange={(v) => setActive(v === "on")}
          ariaLabel="Policy state"
          className="w-40"
          options={[{ value: "on", label: "Active" }, { value: "off", label: "Disabled" }]}
        />
        <GovNote tone="neutral" title="Effect of changing this">
          Existing approvals are not retroactively re-evaluated. The new threshold applies the next time a
          version is calculated or submitted.
        </GovNote>
      </div>
    </Dialog>
  );
}

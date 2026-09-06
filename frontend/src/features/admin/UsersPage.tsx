import { Plus, UserRound } from "lucide-react";
import * as React from "react";
import { formatRelative } from "@/api/money";
import { useAdminMutations, useUsers } from "@/api/queries";
import type { RoleCode, UserRead } from "@/api/types";
import { Page } from "@/app/shells/InternalShell";
import {
  Async, Badge, Button, type Column, DataTable, Dialog, EmptyState, FormField, GovNote,
  Input, Panel, Select, toast,
} from "@/design-system";

const ROLES: RoleCode[] = ["SALES", "MANAGER", "FINANCE", "OPS", "ADMIN"];

const ROLE_TONE: Record<string, { fg: string; bg: string; label: string }> = {
  SALES: { fg: "var(--accent-600)", bg: "var(--accent-100)", label: "Sales" },
  MANAGER: { fg: "var(--gov-600)", bg: "var(--gov-100)", label: "Manager" },
  FINANCE: { fg: "var(--risk-high)", bg: "var(--risk-high-bg)", label: "Finance" },
  OPS: { fg: "var(--state-negotiating)", bg: "var(--state-negotiating-bg)", label: "Ops" },
  ADMIN: { fg: "var(--risk-critical)", bg: "var(--risk-critical-bg)", label: "Admin" },
  CUSTOMER: { fg: "var(--ink-500)", bg: "var(--ink-100)", label: "Customer" },
};

export function UsersPage() {
  const query = useUsers();
  const { createUser } = useAdminMutations();
  const [creating, setCreating] = React.useState(false);
  const [email, setEmail] = React.useState("");
  const [fullName, setFullName] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [role, setRole] = React.useState<RoleCode>("SALES");

  const columns: Column<UserRead>[] = [
    {
      id: "user",
      header: "User",
      sortValue: (u) => u.full_name,
      cell: (u) => (
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-ink-100 font-ui text-2xs font-semibold text-content-secondary">
            {u.full_name.split(" ").map((s) => s[0]).slice(0, 2).join("")}
          </span>
          <div className="min-w-0">
            <div className="truncate font-medium text-content">{u.full_name}</div>
            <div className="truncate text-2xs text-content-faint">{u.email}</div>
          </div>
        </div>
      ),
    },
    { id: "role", header: "Role", sortValue: (u) => u.role, cell: (u) => <Badge size="sm" tone={ROLE_TONE[u.role]} /> },
    {
      id: "active",
      header: "State",
      cell: (u) => (u.is_active ? <Badge size="sm" tone={{ fg: "var(--policy-passed)", bg: "var(--policy-passed-bg)", label: "Active" }} /> : <Badge size="sm" tone={{ fg: "var(--ink-500)", bg: "var(--ink-100)", label: "Disabled" }} />),
    },
    { id: "last", header: "Last sign-in", align: "right", sortValue: (u) => u.last_login_at ?? "", cell: (u) => <span className="whitespace-nowrap text-xs text-content-muted">{u.last_login_at ? formatRelative(u.last_login_at) : "never"}</span> },
  ];

  return (
    <Page
      title="Users"
      subtitle="Who can sign in, and what the server will let them do."
      actions={<Button variant="primary" icon={<Plus className="size-3.5" />} onClick={() => setCreating(true)}>New user</Button>}
    >
      <GovNote className="mb-3" title="Roles are enforced by the backend">
        Hiding a button is a convenience, not a control. Every request is authorised server-side against the
        user record, which is re-read on each call — so a role change takes effect immediately rather than when
        a token happens to expire.
      </GovNote>

      <Panel>
        <Async
          query={query}
          isEmpty={(d) => d.length === 0}
          empty={<EmptyState icon={<UserRound className="size-5" />} title="No users" />}
        >
          {(rows) => <DataTable rows={rows} columns={columns} caption="Users" getKey={(u) => u.id} rail={(u) => ROLE_TONE[u.role]?.fg} />}
        </Async>
      </Panel>

      <Dialog
        open={creating}
        onOpenChange={setCreating}
        title="New user"
        description="Creates a user inside your organisation."
        footer={
          <>
            <Button onClick={() => setCreating(false)}>Cancel</Button>
            <Button
              variant="primary" loading={createUser.isPending}
              disabled={!email.trim() || !fullName.trim() || password.length < 8}
              onClick={() =>
                createUser.mutate(
                  { email: email.trim(), full_name: fullName.trim(), password, role },
                  {
                    onSuccess: () => {
                      setCreating(false);
                      setEmail(""); setFullName(""); setPassword("");
                      toast.success("User created");
                    },
                    onError: toast.fromError,
                  },
                )
              }
            >
              Create user
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <FormField label="Full name" required>{(p) => <Input {...p} value={fullName} onChange={(e) => setFullName(e.target.value)} />}</FormField>
          <FormField label="Email" required>{(p) => <Input {...p} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />}</FormField>
          <FormField label="Password" required hint="At least 8 characters, mixing letters with something else.">
            {(p) => <Input {...p} type="password" value={password} onChange={(e) => setPassword(e.target.value)} />}
          </FormField>
          <FormField label="Role">
            {(p) => <Select id={p.id} value={role} onValueChange={(v) => setRole(v as RoleCode)} options={ROLES.map((r) => ({ value: r, label: ROLE_TONE[r].label }))} />}
          </FormField>
        </div>
      </Dialog>
    </Page>
  );
}

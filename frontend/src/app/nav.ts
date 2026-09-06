/**
 * Navigation model.
 *
 * The wireframe uses a flat top tab bar; the brief asks for grouped workflow
 * sections. Both are satisfied by a top bar of modules plus a contextual
 * subnav — which is also the Drill-Down Analytics pattern (breadcrumbs,
 * context preservation) from styles.csv.
 *
 * Every entry below maps to an endpoint verified in Phase 0. There are no
 * routes for capabilities the backend does not have.
 */
import type { RoleCode } from "@/api/types";

export interface NavItem {
  to: string;
  label: string;
  /** Roles for which this is worth showing. Omitted = everyone internal. */
  roles?: RoleCode[];
  end?: boolean;
}

export interface NavModule {
  id: string;
  label: string;
  to: string;
  roles?: RoleCode[];
  children?: NavItem[];
}

export const MODULES: NavModule[] = [
  { id: "command", label: "Command", to: "/", },
  {
    id: "sales",
    label: "Sales",
    to: "/quotes",
    children: [
      { to: "/quotes", label: "Quotations", end: true },
      { to: "/pipeline", label: "Pipeline" },
      { to: "/deals", label: "Deals" },
      { to: "/customers", label: "Customers" },
    ],
  },
  {
    id: "approvals",
    label: "Approvals",
    to: "/approvals",
    children: [{ to: "/approvals", label: "Inbox", end: true }],
  },
  {
    id: "operations",
    label: "Operations",
    to: "/orders",
    children: [
      { to: "/orders", label: "Orders", end: true },
      { to: "/inventory", label: "Inventory" },
      { to: "/warehouses", label: "Warehouses" },
    ],
  },
  {
    id: "billing",
    label: "Billing",
    to: "/billing",
    children: [
      { to: "/billing", label: "Schedules", end: true },
      { to: "/billing/subscriptions", label: "Subscriptions" },
      { to: "/billing/invoices", label: "Invoices" },
      { to: "/billing/credit-notes", label: "Credit notes" },
    ],
  },
  {
    id: "intelligence",
    label: "Intelligence",
    to: "/deal-health",
    children: [
      { to: "/deal-health", label: "Deal health", end: true },
      { to: "/attention", label: "Attention" },
      { to: "/anomalies", label: "Anomalies" },
      { to: "/activity", label: "Activity" },
    ],
  },
  {
    id: "reports",
    label: "Reports",
    to: "/reports",
    children: [{ to: "/reports", label: "Reports", end: true }],
  },
  {
    id: "admin",
    label: "Admin",
    to: "/admin/products",
    roles: ["ADMIN"],
    children: [
      { to: "/admin/products", label: "Products" },
      { to: "/admin/price-lists", label: "Price lists" },
      { to: "/admin/policies", label: "Discount & approval rules" },
      { to: "/admin/warehouses", label: "Warehouses" },
      { to: "/admin/settings", label: "Governance" },
      { to: "/admin/teams", label: "Sales teams" },
      { to: "/admin/users", label: "Users" },
    ],
  },
];

/** The module whose subnav should show for a given pathname. */
export const moduleForPath = (pathname: string): NavModule | undefined => {
  if (pathname === "/") return MODULES[0];
  const match = MODULES.filter((m) => m.id !== "command").find((m) => {
    if (pathname.startsWith(m.to) && m.to !== "/") return true;
    return m.children?.some((c) => pathname.startsWith(c.to) && c.to !== "/");
  });
  return match;
};

export const visibleModules = (role: RoleCode | undefined): NavModule[] =>
  MODULES.filter((m) => !m.roles || (role && m.roles.includes(role)));

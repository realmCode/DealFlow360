import {
  Activity, BadgeDollarSign, Boxes, Briefcase, Building2, ClipboardCheck, FileSpreadsheet,
  FileText, Gauge, LayoutGrid, Package, Receipt, Repeat, ScrollText, SlidersHorizontal,
  TrendingUp, Users2, UserRound, Warehouse, Bell, ReceiptText,
} from "lucide-react";
import type * as React from "react";
import type { RoleCode } from "@/api/types";

/**
 * Navigation model.
 *
 * Grouped by the workflow a person is in rather than by the entity a route
 * happens to read, so the sidebar reads as the shape of the business: sell,
 * approve, fulfil, bill, understand, configure.
 *
 * Every entry maps to an endpoint verified during the backend audit. There are
 * no routes here for capabilities the API does not have.
 */
export interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  end?: boolean;
  /** Which live counter, if any, belongs on this item. */
  badge?: "attention" | "approvals";
}

export interface NavGroup {
  id: string;
  label: string;
  roles?: RoleCode[];
  items: NavItem[];
}

export const NAV: NavGroup[] = [
  {
    id: "command",
    label: "Command",
    items: [{ to: "/", label: "Command Center", icon: LayoutGrid, end: true, badge: "attention" }],
  },
  {
    id: "sales",
    label: "Sales",
    items: [
      { to: "/quotes", label: "Quotations", icon: FileText, end: true },
      { to: "/pipeline", label: "Pipeline", icon: TrendingUp },
      { to: "/deals", label: "Deals", icon: Briefcase },
      { to: "/customers", label: "Customers", icon: Building2 },
    ],
  },
  {
    id: "operations",
    label: "Operations",
    items: [
      { to: "/approvals", label: "Approvals", icon: ClipboardCheck, end: true, badge: "approvals" },
      { to: "/orders", label: "Orders", icon: Package, end: true },
      { to: "/inventory", label: "Inventory", icon: Boxes },
      { to: "/warehouses", label: "Warehouses", icon: Warehouse },
    ],
  },
  {
    id: "billing",
    label: "Billing",
    items: [
      { to: "/billing", label: "Schedules", icon: Receipt, end: true },
      { to: "/billing/subscriptions", label: "Subscriptions", icon: Repeat },
      { to: "/billing/invoices", label: "Invoices", icon: BadgeDollarSign },
      { to: "/billing/credit-notes", label: "Credit notes", icon: ReceiptText },
    ],
  },
  {
    id: "intelligence",
    label: "Intelligence",
    items: [
      { to: "/deal-health", label: "Deal health", icon: Gauge, end: true },
      { to: "/attention", label: "Attention", icon: Bell },
      { to: "/anomalies", label: "Anomalies", icon: Activity },
      { to: "/activity", label: "Activity", icon: ScrollText },
    ],
  },
  {
    id: "reports",
    label: "Reports",
    items: [{ to: "/reports", label: "Reports", icon: FileSpreadsheet, end: true }],
  },
  {
    id: "admin",
    label: "Administration",
    roles: ["ADMIN"],
    items: [
      { to: "/admin/products", label: "Products", icon: Package },
      { to: "/admin/price-lists", label: "Price lists", icon: FileSpreadsheet },
      { to: "/admin/policies", label: "Rules & chains", icon: ScrollText },
      { to: "/admin/warehouses", label: "Warehouses", icon: Warehouse },
      { to: "/admin/settings", label: "Governance", icon: SlidersHorizontal },
      { to: "/admin/teams", label: "Sales teams", icon: Users2 },
      { to: "/admin/users", label: "Users", icon: UserRound },
    ],
  },
];

export const visibleGroups = (role: RoleCode | undefined): NavGroup[] =>
  NAV.filter((g) => !g.roles || (role && g.roles.includes(role)));

/** Human trail for the top bar, derived from the path. */
const CRUMB: Record<string, string> = {
  "": "Command Center",
  quotes: "Quotations",
  pipeline: "Pipeline",
  deals: "Deals",
  customers: "Customers",
  approvals: "Approvals",
  orders: "Orders",
  inventory: "Inventory",
  warehouses: "Warehouses",
  billing: "Billing",
  subscriptions: "Subscriptions",
  invoices: "Invoices",
  "credit-notes": "Credit notes",
  "deal-health": "Deal health",
  attention: "Attention",
  anomalies: "Anomalies",
  activity: "Activity",
  reports: "Reports",
  admin: "Administration",
  products: "Products",
  "price-lists": "Price lists",
  policies: "Rules & chains",
  settings: "Governance",
  teams: "Sales teams",
  users: "Users",
  build: "Builder",
  impact: "Impact",
};

const isId = (s: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(s);
/** Path segments that exist for routing, not for reading. */
const SILENT = new Set(["versions"]);

export function breadcrumbs(pathname: string): { label: string; to?: string }[] {
  const parts = pathname.split("/").filter(Boolean);
  if (parts.length === 0) return [{ label: "Command Center" }];

  const trail: { label: string; to?: string }[] = [];
  let acc = "";
  parts.forEach((part, i) => {
    acc += `/${part}`;
    if (isId(part) || SILENT.has(part)) return; // routing detail, not navigation
    const label = CRUMB[part] ?? part.replace(/-/g, " ").replace(/^./, (c) => c.toUpperCase());
    trail.push({ label, to: i === parts.length - 1 ? undefined : acc });
  });
  return trail.length ? trail : [{ label: "Command Center" }];
}

/** The group a path belongs to — used to keep its section open and marked. */
export const groupForPath = (pathname: string): NavGroup | undefined =>
  NAV.find((g) =>
    g.items.some((i) => (i.end ? pathname === i.to : pathname.startsWith(i.to)) || pathname.startsWith(`${i.to}/`)),
  );

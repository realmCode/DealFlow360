/**
 * The seeded demo tenant.
 *
 * These are the SIX real users `scripts/seed.py` creates, verified against the
 * `users` table. Nothing here is a shortcut: selecting an account fills the
 * normal login form and posts to `POST /auth/login` like any other sign-in.
 * The backend issues a real JWT, re-reads the user row on every request, and
 * enforces every role check server-side exactly as it would in production.
 *
 * What makes this safe rather than a bypass:
 *   - no token is minted client-side
 *   - no authorisation check is skipped
 *   - the credentials only work because this database was seeded with them;
 *     against a real tenant they authenticate as nothing
 *   - the whole surface is behind `isDemoMode()` and can be compiled out
 */
import type { RoleCode } from "@/api/types";

export interface DemoAccount {
  role: RoleCode;
  /** Verified against the seeded `users` table. */
  email: string;
  name: string;
  /** Short label for the role's job. */
  title: string;
  /** What this person is responsible for. */
  blurb: string;
  /** What a presenter should show while signed in as them. */
  demo: string;
  /** Capability chips — mirrors the backend dependency guards. */
  scope: string[];
  /** Where signing in as this role lands, so the demo starts on the point. */
  landing: string;
  /** Accent used for the card rail and icon. */
  tone: string;
  internal: boolean;
}

/** The seed script sets every demo user to this password. */
export const DEMO_PASSWORD =
  (import.meta.env.VITE_DEMO_PASSWORD as string | undefined) ?? "Password123!";

/**
 * Demo access is on in development and can be switched on for a hosted demo
 * build with VITE_DEMO_MODE=true. Setting it to anything else in a production
 * build removes the panel entirely.
 */
export const isDemoMode = (): boolean => {
  const flag = import.meta.env.VITE_DEMO_MODE as string | undefined;
  if (flag !== undefined) return flag === "true";
  return import.meta.env.DEV;
};

export const DEMO_ACCOUNTS: DemoAccount[] = [
  {
    role: "SALES",
    email: "sales@techsupply.com",
    name: "Sam Rivera",
    title: "Sales",
    blurb: "Builds quotations and negotiates terms with the customer.",
    demo: "Build a quote, watch margin and risk move, submit for approval.",
    scope: ["Quotes", "Deals", "Customers", "Negotiation"],
    landing: "/",
    tone: "var(--accent-500)",
    internal: true,
  },
  {
    role: "MANAGER",
    email: "manager@techsupply.com",
    name: "Morgan Chen",
    title: "Sales Manager",
    blurb: "First approval step when a discount breaches its ceiling.",
    demo: "Open the inbox, read why it was flagged, approve step one.",
    scope: ["Approvals", "Quotes", "Reports"],
    landing: "/approvals",
    tone: "var(--gov-500)",
    internal: true,
  },
  {
    role: "FINANCE",
    email: "finance@techsupply.com",
    name: "Fran Delgado",
    title: "Finance",
    blurb: "Second approval step, and owns invoicing and subscriptions.",
    demo: "Approve step two, then issue an invoice and record a payment.",
    scope: ["Approvals", "Invoices", "Subscriptions", "Credit notes"],
    landing: "/approvals",
    tone: "var(--risk-high)",
    internal: true,
  },
  {
    role: "OPS",
    email: "ops@techsupply.com",
    name: "Omar Petrov",
    title: "Operations",
    blurb: "Allocates stock across warehouses and ships the order.",
    demo: "Allocate the order and show the 60/40 multi-warehouse split.",
    scope: ["Orders", "Allocation", "Fulfilment", "Inventory"],
    landing: "/orders",
    tone: "var(--state-negotiating)",
    internal: true,
  },
  {
    role: "ADMIN",
    email: "admin@techsupply.com",
    name: "Avery Stone",
    title: "Administrator",
    blurb: "Owns the governance rules that decide how anything routes.",
    demo: "Show the discount ceilings and risk weights that drive routing.",
    scope: ["Everything", "Policies", "Governance", "Users"],
    landing: "/",
    tone: "var(--risk-critical)",
    internal: true,
  },
  {
    role: "CUSTOMER",
    email: "customer@acme.com",
    name: "Casey Nolan",
    title: "Customer",
    blurb: "Acme Corporation — the buyer, outside the seller's tenant.",
    demo: "Review the proposal, counter on price, then confirm the order.",
    scope: ["Own proposals", "Messages", "Confirmation"],
    landing: "/portal",
    tone: "var(--policy-passed)",
    internal: false,
  },
];

export const accountFor = (role: RoleCode | undefined) =>
  DEMO_ACCOUNTS.find((a) => a.role === role);

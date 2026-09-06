import * as React from "react";
import { createBrowserRouter, Navigate, Outlet, useLocation } from "react-router-dom";
import { clearIntendedLanding, peekIntendedLanding, useAuth } from "@/app/auth";
import { InternalShell } from "@/app/shells/InternalShell";
import { PortalShell } from "@/app/shells/PortalShell";
import { LoginPage } from "@/features/auth/LoginPage";
import { EmptyState, PermissionState, SkeletonTable } from "@/design-system";
import type { RoleCode } from "@/api/types";

/* Route-level code splitting — charts and the heavier detail screens stay out
   of the initial bundle (react-best-practices bundle-* rules). */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const lazy = <M extends Record<string, any>>(loader: () => Promise<M>, key: keyof M) =>
  React.lazy(async () => ({ default: (await loader())[key] as React.ComponentType }));

const CommandCenter = lazy(() => import("@/features/command/CommandCenter"), "CommandCenter");
const QuotesPage = lazy(() => import("@/features/quotes/QuotesPage"), "QuotesPage");
const PipelinePage = lazy(() => import("@/features/quotes/PipelinePage"), "PipelinePage");
const QuoteDetailPage = lazy(() => import("@/features/quotes/QuoteDetailPage"), "QuoteDetailPage");
const QuoteBuilderPage = lazy(() => import("@/features/builder/QuoteBuilderPage"), "QuoteBuilderPage");
const ImpactPage = lazy(() => import("@/features/impact/ImpactPage"), "ImpactPage");
const DealsPage = lazy(() => import("@/features/deals/DealsPage"), "DealsPage");
const CustomersPage = lazy(() => import("@/features/customers/CustomersPage"), "CustomersPage");
const ApprovalsPage = lazy(() => import("@/features/approvals/ApprovalsPage"), "ApprovalsPage");
const ApprovalDetailPage = lazy(() => import("@/features/approvals/ApprovalDetailPage"), "ApprovalDetailPage");
const OrdersPage = lazy(() => import("@/features/orders/OrdersPage"), "OrdersPage");
const OrderDetailPage = lazy(() => import("@/features/orders/OrderDetailPage"), "OrderDetailPage");
const InventoryPage = lazy(() => import("@/features/orders/InventoryPage"), "InventoryPage");
const WarehousesPage = lazy(() => import("@/features/orders/WarehousesPage"), "WarehousesPage");
const BillingPage = lazy(() => import("@/features/billing/BillingPage"), "BillingPage");
const SubscriptionsPage = lazy(() => import("@/features/billing/SubscriptionsPage"), "SubscriptionsPage");
const InvoicesPage = lazy(() => import("@/features/billing/InvoicesPage"), "InvoicesPage");
const CreditNotesPage = lazy(() => import("@/features/billing/CreditNotesPage"), "CreditNotesPage");
const DealHealthPage = lazy(() => import("@/features/intelligence/DealHealthPage"), "DealHealthPage");
const AttentionPage = lazy(() => import("@/features/intelligence/AttentionPage"), "AttentionPage");
const AnomaliesPage = lazy(() => import("@/features/intelligence/AnomaliesPage"), "AnomaliesPage");
const ActivityPage = lazy(() => import("@/features/intelligence/ActivityPage"), "ActivityPage");
const ReportsPage = lazy(() => import("@/features/reports/ReportsPage"), "ReportsPage");
const ProductsPage = lazy(() => import("@/features/admin/ProductsPage"), "ProductsPage");
const PriceListsPage = lazy(() => import("@/features/admin/PriceListsPage"), "PriceListsPage");
const PoliciesPage = lazy(() => import("@/features/admin/PoliciesPage"), "PoliciesPage");
const SettingsPage = lazy(() => import("@/features/admin/SettingsPage"), "SettingsPage");
const TeamsPage = lazy(() => import("@/features/admin/TeamsPage"), "TeamsPage");
const UsersPage = lazy(() => import("@/features/admin/UsersPage"), "UsersPage");
const PortalQuotesPage = lazy(() => import("@/features/portal/PortalQuotesPage"), "PortalQuotesPage");
const PortalQuotePage = lazy(() => import("@/features/portal/PortalQuotePage"), "PortalQuotePage");
const PortalMessagesPage = lazy(() => import("@/features/portal/PortalMessagesPage"), "PortalMessagesPage");
const PortalProfilePage = lazy(() => import("@/features/portal/PortalProfilePage"), "PortalProfilePage");

/**
 * Retires a landing intent once the app has arrived at it. Doing this in an
 * effect rather than during a guard's render keeps render pure and makes the
 * intent survive StrictMode's double invocation.
 */
function LandingIntent() {
  const { pathname } = useLocation();
  React.useEffect(() => {
    if (peekIntendedLanding() === pathname) clearIntendedLanding();
  }, [pathname]);
  return null;
}

function RootLayout() {
  return (
    <>
      <LandingIntent />
      <Outlet />
    </>
  );
}

function Booting() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas">
      <div className="w-full max-w-md space-y-3 px-6">
        <div className="shimmer h-2 w-24 rounded-pill" />
        <div className="shimmer h-8 w-full rounded-md" />
        <div className="shimmer h-8 w-4/5 rounded-md" />
      </div>
    </div>
  );
}

function Suspended() {
  return (
    <React.Suspense
      fallback={
        <div className="mx-auto w-full max-w-[1600px] px-4 py-6">
          <div className="shimmer mb-4 h-7 w-56 rounded-md" />
          <div className="panel"><SkeletonTable /></div>
        </div>
      }
    >
      <Outlet />
    </React.Suspense>
  );
}

/** Requires a session, and the right side of the internal/portal split. */
function Guard({ side, roles }: { side: "internal" | "portal"; roles?: RoleCode[] }) {
  const { user, status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <Booting />;
  if (status === "anonymous") return <Navigate to="/login" replace state={{ from: location.pathname }} />;

  // The signed-in user is on the wrong side of the internal/portal split.
  // If a switch asked for a specific destination, honour it — otherwise fall
  // back to that side's home.
  if (side === "internal" && !user!.is_internal) {
    return <Navigate to={peekIntendedLanding() ?? "/portal"} replace />;
  }
  if (side === "portal" && user!.is_internal) {
    return <Navigate to={peekIntendedLanding() ?? "/"} replace />;
  }

  if (roles && !roles.includes(user!.role)) return <PermissionState need={roles.join(", ")} />;

  return <Outlet />;
}

const adminOnly: RoleCode[] = ["ADMIN"];

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
  { path: "/login", element: <LoginPage /> },
  {
    element: <Guard side="internal" />,
    children: [
      {
        element: <InternalShell />,
        children: [
          {
            element: <Suspended />,
            children: [
              { index: true, element: <CommandCenter /> },

              { path: "quotes", element: <QuotesPage /> },
              { path: "quotes/:quoteId", element: <QuoteDetailPage /> },
              { path: "quotes/:quoteId/versions/:versionId/build", element: <QuoteBuilderPage /> },
              { path: "quotes/:quoteId/versions/:versionId/impact", element: <ImpactPage /> },
              { path: "pipeline", element: <PipelinePage /> },
              { path: "deals", element: <DealsPage /> },
              { path: "customers", element: <CustomersPage /> },

              { path: "approvals", element: <ApprovalsPage /> },
              { path: "approvals/:requestId", element: <ApprovalDetailPage /> },

              { path: "orders", element: <OrdersPage /> },
              { path: "orders/:orderId", element: <OrderDetailPage /> },
              { path: "inventory", element: <InventoryPage /> },
              { path: "warehouses", element: <WarehousesPage /> },

              { path: "billing", element: <BillingPage /> },
              { path: "billing/subscriptions", element: <SubscriptionsPage /> },
              { path: "billing/invoices", element: <InvoicesPage /> },
              { path: "billing/credit-notes", element: <CreditNotesPage /> },

              { path: "deal-health", element: <DealHealthPage /> },
              { path: "attention", element: <AttentionPage /> },
              { path: "anomalies", element: <AnomaliesPage /> },
              { path: "activity", element: <ActivityPage /> },

              { path: "reports", element: <ReportsPage /> },

              {
                element: <Guard side="internal" roles={adminOnly} />,
                children: [
                  { path: "admin/products", element: <ProductsPage /> },
                  { path: "admin/price-lists", element: <PriceListsPage /> },
                  { path: "admin/policies", element: <PoliciesPage /> },
                  { path: "admin/warehouses", element: <WarehousesPage /> },
                  { path: "admin/settings", element: <SettingsPage /> },
                  { path: "admin/teams", element: <TeamsPage /> },
                  { path: "admin/users", element: <UsersPage /> },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
  {
    element: <Guard side="portal" />,
    children: [
      {
        element: <PortalShell />,
        children: [
          {
            element: <Suspended />,
            children: [
              { path: "portal", element: <PortalQuotesPage /> },
              { path: "portal/quotes/:quoteId", element: <PortalQuotePage /> },
              { path: "portal/messages", element: <PortalMessagesPage /> },
              { path: "portal/profile", element: <PortalProfilePage /> },
            ],
          },
        ],
      },
    ],
  },
  {
    path: "*",
    element: (
      <div className="flex min-h-screen items-center justify-center bg-canvas">
        <EmptyState title="Page not found" body="That route does not exist in DealFlow360." />
      </div>
    ),
  },
    ],
  },
]);

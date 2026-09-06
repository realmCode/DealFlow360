import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, ChevronRight, LogOut, Menu } from "lucide-react";
import * as React from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/app/auth";
import { breadcrumbs } from "@/app/nav";
import { isDemoMode } from "@/demo/accounts";
import { RoleSwitcher } from "@/demo/RoleSwitcher";
import { cn } from "@/lib/cn";
import { Sidebar } from "./Sidebar";

const SIDEBAR_KEY = "df360.sidebar.collapsed";

const ROLE_TONE: Record<string, string> = {
  SALES: "var(--accent-600)",
  MANAGER: "var(--gov-600)",
  FINANCE: "var(--risk-high)",
  OPS: "var(--state-negotiating)",
  ADMIN: "var(--risk-critical)",
};

function Avatar({ name, role }: { name: string; role: string }) {
  const initials = name.split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
  return (
    <span
      className="flex size-[26px] shrink-0 items-center justify-center rounded-full font-ui text-[10px] font-semibold text-white"
      style={{ background: ROLE_TONE[role] ?? "var(--ink-500)" }}
    >
      {initials}
    </span>
  );
}

export function InternalShell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [collapsed, setCollapsed] = React.useState(
    () => localStorage.getItem(SIDEBAR_KEY) === "1",
  );
  const [mobileOpen, setMobileOpen] = React.useState(false);

  const toggle = () =>
    setCollapsed((c) => {
      localStorage.setItem(SIDEBAR_KEY, c ? "0" : "1");
      return !c;
    });

  React.useEffect(() => setMobileOpen(false), [location.pathname]);

  const trail = breadcrumbs(location.pathname);

  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[200] focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:shadow-overlay"
      >
        Skip to content
      </a>

      {/* -- sidebar: persistent on desktop, overlay on small screens ------- */}
      <aside className="hidden shrink-0 lg:block">
        <Sidebar collapsed={collapsed} onToggle={toggle} />
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            aria-label="Close menu"
            className="absolute inset-0 bg-ink-950/40 backdrop-blur-[2px]"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 animate-slide-in-left shadow-overlay">
            <Sidebar collapsed={false} onToggle={() => setMobileOpen(false)} onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      {/* -- main column ----------------------------------------------------- */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[var(--topbar-h)] shrink-0 items-center gap-2 border-b border-line bg-surface px-3 lg:px-5">
          <button
            type="button"
            aria-label="Open menu"
            onClick={() => setMobileOpen(true)}
            className="inline-flex size-8 cursor-pointer items-center justify-center rounded-md text-content-secondary transition-colors hover:bg-ink-100 lg:hidden"
          >
            <Menu className="size-4" />
          </button>

          {/* Tenant, then the trail. The page's own <h1> carries the title, so
              a single-level crumb stays muted rather than repeating it loudly. */}
          <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
            <ol className="flex items-center gap-1 overflow-hidden">
              <li className="hidden min-w-0 items-center gap-1 sm:flex">
                <span className="truncate font-ui text-[13px] text-content-faint">
                  {user?.organization_name}
                </span>
              </li>
              {trail.map((c, i) => (
                <li key={`${c.label}-${i}`} className="flex min-w-0 items-center gap-1">
                  <ChevronRight aria-hidden className="hidden size-3 shrink-0 text-content-faint sm:block" />
                  {c.to ? (
                    <Link
                      to={c.to}
                      className="truncate font-ui text-[13px] text-content-muted transition-colors hover:text-content"
                    >
                      {c.label}
                    </Link>
                  ) : (
                    <span
                      aria-current="page"
                      className={cn(
                        "truncate font-ui text-[13px]",
                        trail.length > 1 ? "font-semibold text-content" : "text-content-muted",
                      )}
                    >
                      {c.label}
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </nav>

          {isDemoMode() ? <RoleSwitcher /> : null}

          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-md pl-1 pr-1.5 transition-colors hover:bg-ink-100">
                <Avatar name={user?.full_name ?? "?"} role={user?.role ?? ""} />
                <span className="hidden min-w-0 text-left md:block">
                  <span className="block max-w-[140px] truncate font-ui text-[13px] font-medium leading-[15px] text-content">
                    {user?.full_name}
                  </span>
                  <span className="block font-ui text-[10px] font-semibold uppercase tracking-wider text-content-faint">
                    {user?.role}
                  </span>
                </span>
                <ChevronDown className="size-3.5 shrink-0 text-content-faint" />
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                align="end" sideOffset={6}
                className="z-50 w-64 rounded-lg border border-line bg-white p-1 shadow-overlay animate-slide-up"
              >
                <div className="flex items-center gap-2.5 px-2 py-2.5">
                  <Avatar name={user?.full_name ?? "?"} role={user?.role ?? ""} />
                  <div className="min-w-0">
                    <p className="truncate font-ui text-[13px] font-semibold text-content">{user?.full_name}</p>
                    <p className="truncate text-xs text-content-muted">{user?.email}</p>
                  </div>
                </div>
                <div className="mx-2 mb-1 rounded-md bg-ink-50 px-2 py-1.5">
                  <p className="text-[11px] text-content-muted">{user?.organization_name}</p>
                </div>
                <DropdownMenu.Separator className="my-1 h-px bg-line" />
                <DropdownMenu.Item
                  onSelect={logout}
                  className="flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-[13px] text-content outline-none data-[highlighted]:bg-ink-100"
                >
                  <LogOut className="size-3.5" /> Sign out
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </header>

        <main id="main" className="min-h-0 min-w-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

/**
 * Standard page frame.
 *
 * One gutter, one title treatment, one optional aside — so moving between
 * screens never shifts the furniture.
 */
export function Page({
  title, subtitle, actions, children, aside, wide, toolbar,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  aside?: React.ReactNode;
  wide?: boolean;
  /** Filters or segmented controls that belong with the title, not the body. */
  toolbar?: React.ReactNode;
}) {
  return (
    <div className={cn("mx-auto w-full px-4 py-5 lg:px-6 lg:py-6", wide ? "max-w-none" : "max-w-[1680px]")}>
      <div className="mb-5">
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
          <div className="min-w-0">
            <h1 className="font-ui text-[26px] font-semibold leading-[32px] tracking-[-0.022em] text-content">
              {title}
            </h1>
            {subtitle ? (
              <p className="mt-1 max-w-3xl text-[14px] leading-[20px] text-content-muted">{subtitle}</p>
            ) : null}
          </div>
          {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
        {toolbar ? <div className="mt-4 flex flex-wrap items-center gap-2">{toolbar}</div> : null}
      </div>

      {aside ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_352px]">
          <div className="min-w-0">{children}</div>
          <div className="min-w-0">{aside}</div>
        </div>
      ) : (
        children
      )}
    </div>
  );
}

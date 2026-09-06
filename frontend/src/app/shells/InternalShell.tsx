import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, LogOut, Menu, X } from "lucide-react";
import * as React from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useApprovalInbox, useControlTower } from "@/api/queries";
import { useAuth, useCan } from "@/app/auth";
import { moduleForPath, visibleModules } from "@/app/nav";
import { isDemoMode } from "@/demo/accounts";
import { RoleSwitcher } from "@/demo/RoleSwitcher";
import { cn } from "@/lib/cn";

/** The wordmark. A 360-degree arc closing on a rising bar — deals, cycled. */
function Mark() {
  return (
    <span className="flex items-center gap-2">
      <svg viewBox="0 0 24 24" className="size-[22px] shrink-0" aria-hidden fill="none">
        <path
          d="M12 3.2a8.8 8.8 0 1 0 8.62 10.5"
          stroke="var(--accent-400)" strokeWidth="2.4" strokeLinecap="round"
        />
        <path d="M8.6 14.6V11m3.4 3.6V8.4m3.4 6.2v-2.1" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
      </svg>
      <span className="font-ui text-md font-semibold tracking-tight text-white">
        DealFlow<span className="text-accent-400">360</span>
      </span>
    </span>
  );
}

function RoleChip({ role }: { role: string }) {
  return (
    <span className="hidden rounded-sm border border-chrome-line bg-chrome-hi px-1.5 py-0.5 font-ui text-2xs font-semibold uppercase tracking-wider text-chrome-dim sm:inline">
      {role}
    </span>
  );
}

export function InternalShell() {
  const { user, logout } = useAuth();
  const can = useCan();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = React.useState(false);

  const modules = visibleModules(user?.role);
  const active = moduleForPath(location.pathname);
  const subnav = active?.children && active.children.length > 1 ? active.children : null;

  const tower = useControlTower();
  const inbox = useApprovalInbox(can.approve);

  const counts: Record<string, number | undefined> = {
    command: tower.data?.counts?.total_open || undefined,
    approvals: inbox.data?.length || undefined,
  };

  React.useEffect(() => setMobileOpen(false), [location.pathname]);

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[200] focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:shadow-overlay"
      >
        Skip to content
      </a>

      {/* -- chrome ------------------------------------------------------- */}
      <header className="sticky top-0 z-30 bg-chrome">
        <div className="flex h-header items-center gap-2 px-3 lg:px-4">
          <NavLink to="/" className="mr-1 shrink-0 rounded-sm focus-visible:outline-accent-400" aria-label="DealFlow360 home">
            <Mark />
          </NavLink>

          <span aria-hidden className="mx-1 hidden h-5 w-px bg-chrome-line lg:block" />

          {/* module tabs */}
          <nav aria-label="Modules" className="hidden min-w-0 flex-1 items-center gap-0.5 lg:flex">
            {modules.map((m) => {
              const isActive = active?.id === m.id;
              const count = counts[m.id];
              return (
                <NavLink
                  key={m.id}
                  to={m.to}
                  className={cn(
                    "relative inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 font-ui text-sm font-medium",
                    "transition-colors duration-fast",
                    isActive
                      ? "bg-chrome-hi text-white"
                      : "text-chrome-text hover:bg-chrome-hi/60 hover:text-white",
                  )}
                >
                  {m.label}
                  {count ? (
                    <span
                      className={cn(
                        "num rounded-pill px-1.5 text-2xs font-semibold leading-[15px]",
                        m.id === "command" ? "bg-[var(--risk-critical)] text-white" : "bg-accent-500 text-white",
                      )}
                    >
                      {count}
                    </span>
                  ) : null}
                </NavLink>
              );
            })}
          </nav>

          <div className="flex-1 lg:hidden" />

          {isDemoMode() ? <RoleSwitcher /> : null}

          <RoleChip role={user?.role ?? ""} />

          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md px-2 text-chrome-text transition-colors hover:bg-chrome-hi hover:text-white">
                <span className="flex size-6 items-center justify-center rounded-full bg-accent-600 font-ui text-2xs font-semibold text-white">
                  {(user?.full_name ?? "?").split(" ").map((s) => s[0]).slice(0, 2).join("")}
                </span>
                <span className="hidden max-w-[130px] truncate font-ui text-sm md:inline">{user?.full_name}</span>
                <ChevronDown className="size-3.5 opacity-70" />
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                align="end" sideOffset={6}
                className="z-50 w-60 rounded-lg border border-line bg-white p-1 shadow-overlay animate-slide-up"
              >
                <div className="px-2 py-2">
                  <p className="truncate font-ui text-sm font-semibold text-content">{user?.full_name}</p>
                  <p className="truncate text-xs text-content-muted">{user?.email}</p>
                  <p className="mt-1.5 truncate text-xs text-content-muted">
                    {user?.organization_name}
                  </p>
                </div>
                <DropdownMenu.Separator className="my-1 h-px bg-line" />
                <DropdownMenu.Item
                  onSelect={logout}
                  className="flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-base text-content outline-none data-[highlighted]:bg-ink-100"
                >
                  <LogOut className="size-3.5" /> Sign out
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>

          <button
            type="button"
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen((v) => !v)}
            className="inline-flex size-8 cursor-pointer items-center justify-center rounded-md text-chrome-text hover:bg-chrome-hi hover:text-white lg:hidden"
          >
            {mobileOpen ? <X className="size-4" /> : <Menu className="size-4" />}
          </button>
        </div>

        {mobileOpen ? (
          <nav aria-label="Modules" className="border-t border-chrome-line px-2 py-2 lg:hidden">
            <div className="grid grid-cols-2 gap-1 sm:grid-cols-3">
              {modules.map((m) => (
                <NavLink
                  key={m.id}
                  to={m.to}
                  className={({ isActive }) =>
                    cn(
                      "rounded-md px-2.5 py-2 font-ui text-sm font-medium transition-colors",
                      isActive || active?.id === m.id ? "bg-chrome-hi text-white" : "text-chrome-text hover:bg-chrome-hi/60",
                    )
                  }
                >
                  {m.label}
                </NavLink>
              ))}
            </div>
          </nav>
        ) : null}
      </header>

      {/* -- contextual subnav -------------------------------------------- */}
      {subnav ? (
        <div className="sticky top-header z-20 border-b border-line bg-surface/95 backdrop-blur">
          <nav aria-label={`${active?.label} sections`} className="scrollbar-none flex h-subnav items-center gap-0.5 overflow-x-auto px-3 lg:px-4">
            {subnav.map((c) => (
              <NavLink
                key={c.to}
                to={c.to}
                end={c.end}
                className={({ isActive }) =>
                  cn(
                    "relative inline-flex h-full shrink-0 items-center px-2.5 font-ui text-sm font-medium transition-colors duration-fast",
                    "after:absolute after:inset-x-1.5 after:bottom-0 after:h-[2px] after:rounded-t-full",
                    isActive
                      ? "text-content after:bg-accent-600"
                      : "text-content-muted hover:text-content after:bg-transparent",
                  )
                }
              >
                {c.label}
              </NavLink>
            ))}
          </nav>
        </div>
      ) : null}

      <main id="main" className="min-w-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}

/** Standard page frame: title block + body, consistent gutters everywhere. */
export function Page({
  title, subtitle, actions, children, aside, wide,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  aside?: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <div className={cn("mx-auto w-full px-3 py-4 lg:px-4 lg:py-5", wide ? "max-w-none" : "max-w-[1600px]")}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="font-ui text-2xl font-semibold tracking-tight text-content">{title}</h1>
          {subtitle ? <p className="mt-0.5 text-md text-content-muted">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {aside ? (
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0">{children}</div>
          <div className="min-w-0">{aside}</div>
        </div>
      ) : (
        children
      )}
    </div>
  );
}

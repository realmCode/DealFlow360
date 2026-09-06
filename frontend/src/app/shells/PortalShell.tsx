import { LogOut } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/app/auth";
import { Button } from "@/design-system";
import { isDemoMode } from "@/demo/accounts";
import { RoleSwitcher } from "@/demo/RoleSwitcher";
import { cn } from "@/lib/cn";

/**
 * The customer portal is a different product, not a theme of the internal one.
 *
 * Lower density, wider measure, larger type, no module bar, no sidebar — it
 * should read as a proposal you review, not a console you operate. Three tabs,
 * exactly as the wireframe's navigation key specifies.
 *
 * Isolation is structural, not conditional: the portal only ever renders data
 * from `/portal/*`, whose response schemas have no cost, margin or risk field.
 */
const TABS = [
  { to: "/portal", label: "My quotations", end: true },
  { to: "/portal/messages", label: "Messages" },
  { to: "/portal/profile", label: "Profile" },
];

export function PortalShell() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-[#fbfaf8]">
      <header className="border-b border-[#e8e4dd] bg-white/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-4 px-5">
          <div className="flex items-center gap-2.5">
            <svg viewBox="0 0 24 24" className="size-6" aria-hidden fill="none">
              <path d="M12 3.2a8.8 8.8 0 1 0 8.62 10.5" stroke="var(--accent-600)" strokeWidth="2.4" strokeLinecap="round" />
              <path d="M8.6 14.6V11m3.4 3.6V8.4m3.4 6.2v-2.1" stroke="var(--ink-800)" strokeWidth="2.2" strokeLinecap="round" />
            </svg>
            <span className="font-ui text-md font-semibold tracking-tight text-ink-900">
              DealFlow<span className="text-accent-600">360</span>
            </span>
            <span className="ml-1 hidden text-sm text-content-muted sm:inline">
              for {user?.organization_name}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {isDemoMode() ? <RoleSwitcher variant="light" /> : null}
            <Button size="sm" variant="ghost" onClick={logout} icon={<LogOut className="size-3.5" />}>
              Sign out
            </Button>
          </div>
        </div>

        <nav aria-label="Portal sections" className="mx-auto max-w-5xl px-5">
          <div className="flex items-center gap-1">
            {TABS.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                end={t.end}
                className={({ isActive }) =>
                  cn(
                    "relative inline-flex h-10 items-center px-3 font-ui text-md font-medium transition-colors",
                    "after:absolute after:inset-x-2 after:bottom-0 after:h-[2px] after:rounded-t-full",
                    isActive
                      ? "text-ink-900 after:bg-accent-600"
                      : "text-content-muted hover:text-ink-900 after:bg-transparent",
                  )
                }
              >
                {t.label}
              </NavLink>
            ))}
          </div>
        </nav>
      </header>

      <main className="mx-auto max-w-5xl px-5 py-8">
        <Outlet />
      </main>

      <footer className="mx-auto max-w-5xl px-5 pb-10 pt-4">
        <p className="text-sm text-content-faint">
          Questions about this proposal? Reply in the negotiation thread and your account team will respond.
        </p>
      </footer>
    </div>
  );
}

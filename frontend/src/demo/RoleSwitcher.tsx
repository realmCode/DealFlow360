import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Check, Loader2, Repeat2 } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { setIntendedLanding, useAuth } from "@/app/auth";
import { toast } from "@/design-system";
import { cn } from "@/lib/cn";
import { DEMO_ACCOUNTS, DEMO_PASSWORD, type DemoAccount } from "./accounts";

/**
 * Switch seeded role without leaving the app — the demo runs through six
 * personas and a full sign-out round trip each time would break the narrative.
 *
 * It is still a genuine re-authentication: the current session is discarded
 * and `POST /auth/login` is called with the next account's real credentials.
 * The only thing saved is typing.
 */
export function RoleSwitcher({ variant = "chrome" }: { variant?: "chrome" | "light" }) {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const [busy, setBusy] = React.useState<string | null>(null);

  const switchTo = async (account: DemoAccount) => {
    if (account.role === user?.role) return;
    setBusy(account.role);
    try {
      // Real re-authentication against the seeded account. `login` swaps the
      // session in one update, so the app never dips through an anonymous
      // state and no guard can bounce us to /login mid-switch.
      const next = await login(account.email, DEMO_PASSWORD);
      const target = next.is_internal ? account.landing : "/portal";

      // Declare the destination before navigating. If crossing between the
      // internal and portal shells makes the current route illegal, the guard
      // that redirects will land on this same target rather than its own home.
      setIntendedLanding(target);
      nav(target, { replace: true });

      toast.success(`Signed in as ${account.title}`, `${next.full_name} \u00b7 ${next.email}`);
    } catch (e) {
      setIntendedLanding(null);
      toast.fromError(e);
    } finally {
      setBusy(null);
    }
  };

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          aria-label="Switch demo role"
          className={cn(
            "inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md px-2 font-ui text-sm font-medium transition-colors",
            variant === "chrome"
              ? "text-chrome-text hover:bg-chrome-hi hover:text-white"
              : "border border-line text-content-secondary hover:bg-ink-50 hover:text-content",
          )}
        >
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Repeat2 className="size-3.5" />}
          <span className="hidden sm:inline">Switch role</span>
        </button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          className="z-50 w-[292px] rounded-lg border border-line bg-white p-1 shadow-overlay animate-slide-up"
        >
          <div className="px-2 py-1.5">
            <p className="micro">Demo roles</p>
            <p className="mt-0.5 text-xs text-content-muted">Re-authenticates as the seeded account.</p>
          </div>
          <DropdownMenu.Separator className="my-1 h-px bg-line" />

          {DEMO_ACCOUNTS.map((a) => {
            const current = a.role === user?.role;
            return (
              <DropdownMenu.Item
                key={a.role}
                disabled={busy !== null}
                // Let Radix close the menu on select; the switch continues
                // asynchronously and reports through the trigger's spinner.
                onSelect={() => void switchTo(a)}
                className={cn(
                  "flex cursor-pointer items-center gap-2.5 rounded-sm px-2 py-1.5 outline-none",
                  "data-[highlighted]:bg-accent-50",
                  current && "bg-ink-50",
                )}
              >
                <span aria-hidden className="size-1.5 shrink-0 rounded-full" style={{ background: a.tone }} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-ui text-sm font-medium text-content">{a.title}</span>
                  <span className="block truncate text-2xs text-content-faint">{a.email}</span>
                </span>
                {busy === a.role ? (
                  <Loader2 className="size-3.5 shrink-0 animate-spin text-content-muted" />
                ) : current ? (
                  <Check className="size-3.5 shrink-0 text-accent-600" />
                ) : null}
              </DropdownMenu.Item>
            );
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

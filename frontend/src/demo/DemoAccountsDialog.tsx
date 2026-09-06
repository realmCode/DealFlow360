import { KeyRound, ShieldCheck } from "lucide-react";
import * as React from "react";
import { errorHint, errorTitle } from "@/api/errors";
import { setIntendedLanding, useAuth } from "@/app/auth";
import { Dialog, GovNote, Panel } from "@/design-system";
import { DEMO_ACCOUNTS, DEMO_PASSWORD, type DemoAccount } from "./accounts";
import { RoleCard } from "./RoleCard";

/**
 * The demo account picker.
 *
 * Selecting a role runs the ordinary sign-in: `useAuth().login` posts the real
 * credentials to `POST /auth/login`. There is no alternate code path — if the
 * backend rejected them, this would fail exactly like a mistyped password.
 */
export function DemoAccountsDialog({
  open, onOpenChange,
}: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const { login } = useAuth();
  const [busy, setBusy] = React.useState<string | null>(null);
  const [error, setError] = React.useState<unknown>(null);

  const enter = async (account: DemoAccount) => {
    setBusy(account.role);
    setError(null);
    try {
      // Declare where this role should start, then sign in for real. The login
      // page reads the intent and redirects once the session exists, so there
      // is a single authority for the destination.
      setIntendedLanding(account.internal ? account.landing : "/portal");
      await login(account.email, DEMO_PASSWORD);
    } catch (e) {
      setIntendedLanding(null);
      setError(e);
      setBusy(null);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      width="xl"
      title="Demo access"
      description="Six seeded accounts, one per role. Each signs in through the real authentication flow."
    >
      <div className="space-y-4">
        {error ? (
          <Panel rail="var(--policy-violated)" className="px-3 py-2.5">
            <p role="alert" className="font-ui text-sm font-semibold text-content">{errorTitle(error)}</p>
            <p className="mt-0.5 text-xs text-content-muted">
              {errorHint(error) ??
                "Check that the API is running and the demo tenant has been seeded (POST /admin/seed)."}
            </p>
          </Panel>
        ) : null}

        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {DEMO_ACCOUNTS.map((a) => (
            <RoleCard key={a.role} account={a} busy={busy === a.role} disabled={busy !== null} onSelect={enter} />
          ))}
        </div>

        <p className="text-xs leading-[17px] text-content-muted">
          The first five work inside TechSupply Solutions. The customer belongs to Acme Corporation and lands
          in a different application entirely — no cost, margin, risk or approval chain exists in the payloads
          it receives.
        </p>

        <GovNote title="This is the real login, not a shortcut" icon={<ShieldCheck className="size-3.5" />}>
          Every card posts the seeded credentials to <span className="num">POST /auth/login</span> and receives a
          normal JWT. No token is minted in the browser and no authorisation check is skipped — the server
          re-reads the user on every request and enforces each role itself. These credentials work only because
          this database was seeded with them.
        </GovNote>

        <p className="flex items-center gap-1.5 text-xs text-content-faint">
          <KeyRound className="size-3" />
          Shared seeded password <span className="num text-content-muted">{DEMO_PASSWORD}</span>
        </p>
      </div>
    </Dialog>
  );
}

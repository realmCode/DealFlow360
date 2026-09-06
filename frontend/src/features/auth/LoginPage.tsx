import { ArrowRight, ShieldCheck, Users } from "lucide-react";
import * as React from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { errorHint, errorTitle } from "@/api/errors";
import { peekIntendedLanding, useAuth } from "@/app/auth";
import { Button, FormField, Input, Panel } from "@/design-system";
import { isDemoMode } from "@/demo/accounts";
import { DemoAccountsDialog } from "@/demo/DemoAccountsDialog";

const PROOF = [
  "Every total, margin and risk score is computed server-side",
  "Approval routing derives from policy, never from a hardcoded chain",
  "A material change after approval blocks confirmation until re-approval",
];

export function LoginPage() {
  const { login, status, user } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<unknown>(null);
  const [demoOpen, setDemoOpen] = React.useState(false);
  const demo = isDemoMode();

  // One authority for where a fresh session lands: an explicit intent from the
  // demo picker, else wherever the visitor was heading, else the home of
  // whichever application this user belongs to.
  if (status === "authenticated") {
    const to =
      peekIntendedLanding() ??
      (location.state as { from?: string } | null)?.from ??
      (user?.is_internal === false ? "/portal" : "/");
    return <Navigate to={to} replace />;
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const signedIn = await login(email.trim(), password);
      nav(signedIn.is_internal ? "/" : "/portal", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_minmax(420px,44%)]">
      {/* -- narrative side: dark console, hairline grid ------------------- */}
      <aside className="grid-field relative hidden flex-col justify-between overflow-hidden bg-chrome p-10 lg:flex">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-40 -top-40 size-[560px] rounded-full opacity-[0.22]"
          style={{ background: "radial-gradient(circle, var(--accent-500) 0%, transparent 62%)" }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-56 -left-24 size-[520px] rounded-full opacity-[0.14]"
          style={{ background: "radial-gradient(circle, var(--gov-500) 0%, transparent 62%)" }}
        />

        <div className="relative flex items-center gap-2.5">
          <svg viewBox="0 0 24 24" className="size-7" aria-hidden fill="none">
            <path d="M12 3.2a8.8 8.8 0 1 0 8.62 10.5" stroke="var(--accent-400)" strokeWidth="2.4" strokeLinecap="round" />
            <path d="M8.6 14.6V11m3.4 3.6V8.4m3.4 6.2v-2.1" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
          </svg>
          <span className="font-ui text-lg font-semibold tracking-tight text-white">
            DealFlow<span className="text-accent-400">360</span>
          </span>
        </div>

        <div className="relative max-w-lg">
          <p className="micro mb-3 text-accent-400">Commercial operations</p>
          <h1 className="font-ui text-4xl font-semibold leading-[1.12] tracking-tight text-white">
            Every discount, margin and approval — governed by policy, not by memory.
          </h1>
          <p className="mt-4 text-md leading-relaxed text-chrome-text">
            DealFlow360 prices the deal, scores its risk, routes it to the right approver, and
            invalidates that approval the moment the terms move.
          </p>

          <ul className="mt-8 space-y-2.5">
            {PROOF.map((p) => (
              <li key={p} className="flex items-start gap-2.5 text-sm text-chrome-text">
                <ShieldCheck aria-hidden className="mt-px size-4 shrink-0 text-accent-400" />
                {p}
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-chrome-dim">
          The backend is the source of truth. This interface renders what it computes.
        </p>
      </aside>

      {/* -- form side ------------------------------------------------------ */}
      <main className="flex items-center justify-center bg-canvas px-4 py-10">
        <div className="w-full max-w-sm">
          <div className="mb-6 lg:hidden">
            <span className="font-ui text-xl font-semibold tracking-tight text-content">
              DealFlow<span className="text-accent-600">360</span>
            </span>
          </div>

          <h2 className="font-ui text-2xl font-semibold tracking-tight text-content">Sign in</h2>
          <p className="mt-1 text-md text-content-muted">Use your DealFlow360 credentials.</p>

          <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
            <FormField label="Email">
              {(p) => (
                <Input
                  {...p} type="email" autoComplete="username" required autoFocus
                  value={email} onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com" className="h-9"
                />
              )}
            </FormField>

            <FormField label="Password">
              {(p) => (
                <Input
                  {...p} type="password" autoComplete="current-password" required
                  value={password} onChange={(e) => setPassword(e.target.value)}
                  placeholder="\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022" className="h-9"
                />
              )}
            </FormField>

            {error ? (
              <Panel rail="var(--policy-violated)" className="px-3 py-2.5">
                <p role="alert" className="font-ui text-sm font-semibold text-content">{errorTitle(error)}</p>
                {errorHint(error) ? (
                  <p className="mt-0.5 text-xs text-content-muted">{errorHint(error)}</p>
                ) : null}
              </Panel>
            ) : null}

            <Button
              type="submit" variant="primary" size="lg" loading={busy}
              className="w-full" icon={!busy ? <ArrowRight className="size-4" /> : undefined}
            >
              Sign in
            </Button>
          </form>

          {demo ? (
            <>
              <div className="my-6 flex items-center gap-3" role="separator">
                <span className="h-px flex-1 bg-line" />
                <span className="micro">or explore the seeded tenant</span>
                <span className="h-px flex-1 bg-line" />
              </div>

              <button
                type="button"
                onClick={() => setDemoOpen(true)}
                className="group w-full overflow-hidden rounded-lg border border-line bg-surface p-3.5 text-left transition-all duration-fast hover:border-accent-400 hover:shadow-pop"
              >
                <span aria-hidden className="absolute" />
                <span className="flex items-center gap-3">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-md border border-accent-200 bg-accent-50 text-accent-600">
                    <Users className="size-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-ui text-md font-semibold text-content">Demo accounts</span>
                    <span className="block text-sm text-content-muted">
                      Six roles, from sales through to the customer
                    </span>
                  </span>
                  <span className="flex -space-x-1.5">
                    {["var(--accent-500)","var(--gov-500)","var(--risk-high)","var(--state-negotiating)","var(--risk-critical)","var(--policy-passed)"].map((c) => (
                      <span key={c} aria-hidden className="size-2.5 rounded-full ring-2 ring-white" style={{ background: c }} />
                    ))}
                  </span>
                  <ArrowRight className="size-4 shrink-0 text-content-faint transition-transform duration-fast group-hover:translate-x-0.5 group-hover:text-accent-600" />
                </span>
              </button>

              <p className="mt-2.5 text-xs leading-[17px] text-content-faint">
                Each one signs in through the real authentication flow against a seeded account &mdash; no
                credentials are bypassed.
              </p>
            </>
          ) : null}
        </div>
      </main>
      {demo ? <DemoAccountsDialog open={demoOpen} onOpenChange={setDemoOpen} /> : null}
    </div>
  );
}

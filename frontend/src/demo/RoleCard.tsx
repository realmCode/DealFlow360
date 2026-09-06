import {
  ArrowRight, Briefcase, Building2, Landmark, ShieldCheck, SlidersHorizontal, Truck,
} from "lucide-react";
import * as React from "react";
import type { RoleCode } from "@/api/types";
import { Button } from "@/design-system";
import { cn } from "@/lib/cn";
import type { DemoAccount } from "./accounts";

const ICON: Record<RoleCode, React.ReactNode> = {
  SALES: <Briefcase className="size-4" />,
  MANAGER: <ShieldCheck className="size-4" />,
  FINANCE: <Landmark className="size-4" />,
  OPS: <Truck className="size-4" />,
  ADMIN: <SlidersHorizontal className="size-4" />,
  CUSTOMER: <Building2 className="size-4" />,
};

/**
 * One seeded role, presented as a decision rather than a credential pair.
 * The email is shown because a presenter narrating the demo should be able to
 * say which real account they are using.
 */
export function RoleCard({
  account, busy, disabled, onSelect,
}: {
  account: DemoAccount;
  busy?: boolean;
  disabled?: boolean;
  onSelect: (a: DemoAccount) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(account)}
      disabled={disabled}
      aria-label={`Enter as ${account.title} — ${account.email}`}
      className={cn(
        "group relative w-full overflow-hidden rounded-lg border border-line bg-surface p-3.5 text-left",
        "transition-all duration-fast ease-smooth",
        "hover:border-accent-400 hover:shadow-pop focus-visible:border-accent-500",
        "disabled:pointer-events-none disabled:opacity-50",
        !account.internal && "bg-[#fcfbf9]",
      )}
    >
      <span aria-hidden className="absolute inset-y-0 left-0 w-[3px]" style={{ background: account.tone }} />

      <div className="flex items-start gap-2.5">
        <span
          className="flex size-8 shrink-0 items-center justify-center rounded-md border"
          style={{ color: account.tone, borderColor: `${account.tone}33`, background: `${account.tone}12` }}
        >
          {ICON[account.role]}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="font-ui text-md font-semibold text-content">{account.title}</span>
            <span
              className="rounded-sm px-1.5 py-0.5 font-ui text-2xs font-semibold uppercase tracking-wider"
              style={{ color: account.tone, background: `${account.tone}14` }}
            >
              {account.role}
            </span>
            {!account.internal ? (
              <span className="ml-auto shrink-0 rounded-sm border border-line px-1.5 py-0.5 text-2xs uppercase tracking-wide text-content-muted">
                External
              </span>
            ) : null}
          </div>

          <p className="mt-0.5 truncate font-ui text-xs text-content-muted">
            {account.name} &middot; <span className="num">{account.email}</span>
          </p>

          <p className="mt-1.5 text-sm leading-[18px] text-content-secondary">{account.blurb}</p>

          <div className="mt-2 flex flex-wrap gap-1">
            {account.scope.map((s) => (
              <span key={s} className="rounded-sm bg-ink-100 px-1.5 py-0.5 text-2xs text-content-muted">
                {s}
              </span>
            ))}
          </div>

          <div className="mt-2.5 border-t border-line/70 pt-2">
            <p className="text-2xs leading-[15px] text-content-faint">{account.demo}</p>
            <Button
              asChild
              size="xs"
              variant="secondary"
              loading={busy}
              className="pointer-events-none mt-2 w-full justify-center group-hover:border-accent-400 group-hover:bg-accent-50 group-hover:text-accent-700"
              icon={!busy ? <ArrowRight className="size-3" /> : undefined}
            >
              <span>Enter as {account.title}</span>
            </Button>
          </div>
        </div>
      </div>
    </button>
  );
}

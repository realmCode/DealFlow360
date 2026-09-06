/**
 * Loading, empty, error and permission states.
 *
 * Every list and detail view in the product renders one of these rather than a
 * blank region — §25 treats error states as part of the product, and the
 * backend's error codes carry enough detail to say something specific.
 */
import { AlertTriangle, Ban, Inbox, RefreshCw, ShieldAlert, WifiOff } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/cn";
import { errorHint, errorTitle, isDealFlowError } from "@/api/errors";
import { Button } from "./Button";

/* -- skeletons ------------------------------------------------------------ */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("shimmer rounded-sm", className)} />;
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={cn("h-3", i === lines - 1 ? "w-2/5" : "w-full")} />
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div role="status" aria-label="Loading" className="w-full">
      <div className="flex h-9 items-center gap-4 border-b border-line px-3">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-2.5 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex h-9 items-center gap-4 border-b border-line/60 px-3">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className="h-3 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonMetrics({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${count}, minmax(0,1fr))` }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-lg border border-line bg-surface p-3">
          <Skeleton className="h-2.5 w-20" />
          <Skeleton className="mt-2 h-6 w-28" />
        </div>
      ))}
    </div>
  );
}

/* -- shells --------------------------------------------------------------- */
function Shell({
  icon, title, body, action, tone = "neutral", compact,
}: {
  icon: React.ReactNode;
  title: React.ReactNode;
  body?: React.ReactNode;
  action?: React.ReactNode;
  tone?: "neutral" | "warn" | "danger";
  compact?: boolean;
}) {
  const color = {
    neutral: "var(--ink-400)", warn: "var(--gov-500)", danger: "var(--risk-critical)",
  }[tone];
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        compact ? "gap-2 px-4 py-8" : "gap-3 px-6 py-14",
      )}
    >
      <div
        className="flex size-10 items-center justify-center rounded-lg border"
        style={{ color, borderColor: `${color}33`, background: `${color}0f` }}
      >
        {icon}
      </div>
      <div className="max-w-md">
        <p className="font-ui text-md font-semibold text-content">{title}</p>
        {body ? <p className="mt-1 text-sm leading-[19px] text-content-muted">{body}</p> : null}
      </div>
      {action ? <div className="mt-1 flex items-center gap-2">{action}</div> : null}
    </div>
  );
}

export function EmptyState({
  title, body, action, icon, compact,
}: {
  title: React.ReactNode; body?: React.ReactNode; action?: React.ReactNode;
  icon?: React.ReactNode; compact?: boolean;
}) {
  return <Shell icon={icon ?? <Inbox className="size-5" />} title={title} body={body} action={action} compact={compact} />;
}

export function ErrorState({
  error, onRetry, compact,
}: { error: unknown; onRetry?: () => void; compact?: boolean }) {
  const df = isDealFlowError(error) ? error : null;

  if (df?.code === "NETWORK_ERROR") {
    return (
      <Shell
        tone="danger" compact={compact}
        icon={<WifiOff className="size-5" />}
        title="Cannot reach DealFlow360"
        body="The API is not responding. Check that the backend is running, then retry."
        action={onRetry && <Button size="sm" icon={<RefreshCw className="size-3.5" />} onClick={onRetry}>Retry</Button>}
      />
    );
  }

  if (df?.status === 403) {
    return (
      <Shell
        tone="warn" compact={compact}
        icon={<ShieldAlert className="size-5" />}
        title={errorTitle(error)}
        body={
          df.allowedRoles
            ? `Your role is ${df.yourRole ?? "unknown"}. This action needs ${df.allowedRoles.join(" or ")}.`
            : errorHint(error)
        }
      />
    );
  }

  if (df?.status === 404) {
    return <Shell compact={compact} icon={<Ban className="size-5" />} title="Not found" body={df.message} />;
  }

  return (
    <Shell
      tone="danger" compact={compact}
      icon={<AlertTriangle className="size-5" />}
      title={errorTitle(error)}
      body={errorHint(error)}
      action={onRetry && <Button size="sm" icon={<RefreshCw className="size-3.5" />} onClick={onRetry}>Retry</Button>}
    />
  );
}

export function PermissionState({ need }: { need: string }) {
  return (
    <Shell
      tone="warn"
      icon={<ShieldAlert className="size-5" />}
      title="You do not have access to this area"
      body={`This section is available to ${need}. Your role does not include it — the server enforces this regardless of what the interface shows.`}
    />
  );
}

/**
 * One helper the pages use instead of repeating the loading/error/empty ladder.
 */
export function Async<T>({
  query, children, empty, skeleton, isEmpty,
}: {
  query: { data: T | undefined; isPending: boolean; isError: boolean; error: unknown; refetch: () => void };
  children: (data: T) => React.ReactNode;
  empty?: React.ReactNode;
  skeleton?: React.ReactNode;
  isEmpty?: (data: T) => boolean;
}) {
  if (query.isPending) return <>{skeleton ?? <SkeletonTable />}</>;
  if (query.isError) return <ErrorState error={query.error} onRetry={query.refetch} />;
  if (query.data === undefined) return <>{empty ?? <EmptyState title="Nothing here yet" />}</>;
  if (isEmpty?.(query.data)) return <>{empty ?? <EmptyState title="Nothing here yet" />}</>;
  return <>{children(query.data)}</>;
}

/**
 * Minimal toast. Deliberately small: business-significant errors get a
 * designed surface on the page (see §25 / errors.ts NARRATIVE_CODES), so a
 * toast is only for transient confirmations and incidental failures.
 */
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/cn";
import { errorHint, errorTitle } from "@/api/errors";

type Kind = "success" | "error" | "info";
interface Toast { id: number; kind: Kind; title: string; body?: string }

const listeners = new Set<(t: Toast[]) => void>();
let items: Toast[] = [];
let seq = 0;

const emit = () => listeners.forEach((l) => l([...items]));

const push = (kind: Kind, title: string, body?: string) => {
  const id = ++seq;
  items = [...items, { id, kind, title, body }];
  emit();
  setTimeout(() => {
    items = items.filter((t) => t.id !== id);
    emit();
  }, kind === "error" ? 7000 : 4000);
};

export const toast = {
  success: (title: string, body?: string) => push("success", title, body),
  info: (title: string, body?: string) => push("info", title, body),
  error: (title: string, body?: string) => push("error", title, body),
  /** Normalise a thrown DealFlowError into a toast. */
  fromError: (e: unknown) => push("error", errorTitle(e), errorHint(e)),
};

const STYLE: Record<Kind, { icon: React.ReactNode; rail: string }> = {
  success: { icon: <CheckCircle2 className="size-4" />, rail: "var(--policy-passed)" },
  error: { icon: <AlertTriangle className="size-4" />, rail: "var(--policy-violated)" },
  info: { icon: <Info className="size-4" />, rail: "var(--accent-500)" },
};

export function Toaster() {
  const [list, setList] = React.useState<Toast[]>([]);
  React.useEffect(() => {
    listeners.add(setList);
    return () => void listeners.delete(setList);
  }, []);

  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[340px] max-w-[calc(100vw-2rem)] flex-col gap-2"
    >
      {list.map((t) => (
        <div
          key={t.id}
          role={t.kind === "error" ? "alert" : "status"}
          className={cn(
            "pointer-events-auto relative overflow-hidden rounded-lg border border-line bg-surface pl-4 pr-2 py-2.5 shadow-overlay animate-slide-up",
          )}
        >
          <span aria-hidden className="absolute inset-y-0 left-0 w-[3px]" style={{ background: STYLE[t.kind].rail }} />
          <div className="flex items-start gap-2.5">
            <span className="mt-px shrink-0" style={{ color: STYLE[t.kind].rail }}>{STYLE[t.kind].icon}</span>
            <div className="min-w-0 flex-1">
              <p className="font-ui text-sm font-semibold text-content">{t.title}</p>
              {t.body ? <p className="mt-0.5 text-xs leading-[17px] text-content-muted">{t.body}</p> : null}
            </div>
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => {
                items = items.filter((x) => x.id !== t.id);
                emit();
              }}
              className="shrink-0 cursor-pointer rounded-sm p-0.5 text-content-faint transition-colors hover:bg-ink-100 hover:text-content"
            >
              <X className="size-3.5" />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

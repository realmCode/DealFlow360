/**
 * Dialog, Drawer, Tooltip, Tabs.
 *
 * All Radix-backed: focus trapping, escape handling and aria wiring come from
 * the library rather than being reimplemented (shadcn stack CSV: "let
 * components manage focus", Severity High).
 */
import * as DialogPrim from "@radix-ui/react-dialog";
import * as TabsPrim from "@radix-ui/react-tabs";
import * as TooltipPrim from "@radix-ui/react-tooltip";
import { X } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/cn";
import { IconButton } from "./Button";

export const TooltipProvider = TooltipPrim.Provider;

export function Tooltip({
  content, children, side = "top", delay = 200,
}: { content: React.ReactNode; children: React.ReactNode; side?: "top" | "right" | "bottom" | "left"; delay?: number }) {
  if (!content) return <>{children}</>;
  return (
    <TooltipPrim.Root delayDuration={delay}>
      <TooltipPrim.Trigger asChild>{children}</TooltipPrim.Trigger>
      <TooltipPrim.Portal>
        <TooltipPrim.Content
          side={side}
          sideOffset={6}
          collisionPadding={8}
          className="z-50 max-w-xs rounded-md bg-ink-900 px-2.5 py-1.5 text-xs leading-[17px] text-white shadow-overlay animate-fade-in"
        >
          {content}
          <TooltipPrim.Arrow className="fill-ink-900" />
        </TooltipPrim.Content>
      </TooltipPrim.Portal>
    </TooltipPrim.Root>
  );
}

/* -- Dialog: confirmations and short forms -------------------------------- */
export function Dialog({
  open, onOpenChange, title, description, children, footer, width = "md",
}: {
  open: boolean; onOpenChange: (v: boolean) => void;
  title: React.ReactNode; description?: React.ReactNode;
  children?: React.ReactNode; footer?: React.ReactNode;
  width?: "sm" | "md" | "lg";
}) {
  const w = { sm: "max-w-sm", md: "max-w-lg", lg: "max-w-2xl" }[width];
  return (
    <DialogPrim.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrim.Portal>
        <DialogPrim.Overlay className="fixed inset-0 z-40 bg-ink-950/45 backdrop-blur-[2px] animate-fade-in" />
        <DialogPrim.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2",
            "rounded-xl border border-line bg-surface shadow-overlay animate-slide-up", w,
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-4 py-3">
            <div className="min-w-0">
              <DialogPrim.Title className="font-ui text-lg font-semibold text-content">{title}</DialogPrim.Title>
              {description ? (
                <DialogPrim.Description className="mt-0.5 text-sm text-content-muted">{description}</DialogPrim.Description>
              ) : null}
            </div>
            <DialogPrim.Close asChild>
              <IconButton label="Close" size="sm"><X className="size-4" /></IconButton>
            </DialogPrim.Close>
          </div>
          {children ? <div className="max-h-[65vh] overflow-y-auto px-4 py-4">{children}</div> : null}
          {footer ? (
            <div className="flex items-center justify-end gap-2 border-t border-line bg-surface-sunken px-4 py-3">{footer}</div>
          ) : null}
        </DialogPrim.Content>
      </DialogPrim.Portal>
    </DialogPrim.Root>
  );
}

/* -- Drawer: side panel for detail without losing the list ---------------- */
export function Drawer({
  open, onOpenChange, title, description, children, footer, width = "lg",
}: {
  open: boolean; onOpenChange: (v: boolean) => void;
  title: React.ReactNode; description?: React.ReactNode;
  children: React.ReactNode; footer?: React.ReactNode;
  width?: "md" | "lg" | "xl";
}) {
  const w = { md: "max-w-md", lg: "max-w-xl", xl: "max-w-3xl" }[width];
  return (
    <DialogPrim.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrim.Portal>
        <DialogPrim.Overlay className="fixed inset-0 z-40 bg-ink-950/40 backdrop-blur-[2px] animate-fade-in" />
        <DialogPrim.Content
          className={cn(
            "fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-line bg-surface shadow-overlay",
            "animate-slide-in-right", w,
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-4 py-3">
            <div className="min-w-0">
              <DialogPrim.Title className="truncate font-ui text-lg font-semibold text-content">{title}</DialogPrim.Title>
              {description ? (
                <DialogPrim.Description className="mt-0.5 text-sm text-content-muted">{description}</DialogPrim.Description>
              ) : null}
            </div>
            <DialogPrim.Close asChild>
              <IconButton label="Close" size="sm"><X className="size-4" /></IconButton>
            </DialogPrim.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
          {footer ? (
            <div className="flex items-center justify-end gap-2 border-t border-line bg-surface-sunken px-4 py-3">{footer}</div>
          ) : null}
        </DialogPrim.Content>
      </DialogPrim.Portal>
    </DialogPrim.Root>
  );
}

/* -- Tabs: underline, fade not slide (react-view-transitions guidance) ---- */
export function Tabs({
  value, onValueChange, tabs, children, className,
}: {
  value: string; onValueChange: (v: string) => void;
  tabs: { value: string; label: React.ReactNode; count?: number; disabled?: boolean }[];
  children?: React.ReactNode; className?: string;
}) {
  return (
    <TabsPrim.Root value={value} onValueChange={onValueChange} className={className}>
      <TabsPrim.List className="flex items-center gap-0.5 border-b border-line">
        {tabs.map((t) => (
          <TabsPrim.Trigger
            key={t.value}
            value={t.value}
            disabled={t.disabled}
            className={cn(
              "relative inline-flex h-9 cursor-pointer items-center gap-1.5 px-3 font-ui text-base font-medium",
              "text-content-muted transition-colors duration-fast hover:text-content",
              "disabled:cursor-not-allowed disabled:opacity-40",
              "data-[state=active]:text-content",
              "after:absolute after:inset-x-2 after:bottom-[-1px] after:h-[2px] after:rounded-full after:bg-transparent",
              "data-[state=active]:after:bg-accent-600",
            )}
          >
            {t.label}
            {t.count !== undefined ? (
              <span className="num rounded-sm bg-ink-100 px-1 text-2xs text-content-muted">{t.count}</span>
            ) : null}
          </TabsPrim.Trigger>
        ))}
      </TabsPrim.List>
      {children}
    </TabsPrim.Root>
  );
}

export const TabPanel = TabsPrim.Content;

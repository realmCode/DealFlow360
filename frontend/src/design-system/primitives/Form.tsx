/**
 * Inputs.
 *
 * Every control has a real <label for>, errors render below the field with
 * role="alert", and numeric inputs use tabular numerals — all three are
 * "Severity: High" rows in ux-guidelines.csv.
 */
import * as SelectPrim from "@radix-ui/react-select";
import { Check, ChevronDown, Search } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/cn";

const FIELD =
  "w-full rounded-md border border-line-strong bg-white px-2.5 text-[13px] text-content shadow-xs " +
  "placeholder:text-content-faint transition-[border-color,box-shadow] duration-fast " +
  "hover:border-ink-300 focus:border-accent-500 focus:outline-none focus:ring-[3px] focus:ring-accent-500/18 " +
  "disabled:cursor-not-allowed disabled:bg-ink-50 disabled:text-content-muted disabled:shadow-none";

let uid = 0;
const useId = (given?: string) => React.useMemo(() => given ?? `f${++uid}`, [given]);

export function FormField({
  label, hint, error, required, children, id, className, inline,
}: {
  label?: React.ReactNode; hint?: React.ReactNode; error?: string | null;
  required?: boolean; children: (props: { id: string; "aria-invalid": boolean; "aria-describedby"?: string }) => React.ReactNode;
  id?: string; className?: string; inline?: boolean;
}) {
  const fieldId = useId(id);
  const describedBy = error ? `${fieldId}-err` : hint ? `${fieldId}-hint` : undefined;
  return (
    <div className={cn(inline ? "flex items-center gap-3" : "space-y-1", className)}>
      {label ? (
        <label
          htmlFor={fieldId}
          className={cn("block font-ui text-[12px] font-medium text-content-secondary", inline && "shrink-0")}
        >
          {label}
          {required ? <span className="ml-0.5 text-[var(--policy-violated)]">*</span> : null}
        </label>
      ) : null}
      <div className={cn(inline && "min-w-0 flex-1")}>
        {children({ id: fieldId, "aria-invalid": Boolean(error), "aria-describedby": describedBy })}
        {error ? (
          <p id={`${fieldId}-err`} role="alert" className="mt-1 text-xs font-medium text-[var(--policy-violated)]">
            {error}
          </p>
        ) : hint ? (
          <p id={`${fieldId}-hint`} className="mt-1 text-xs text-content-muted">{hint}</p>
        ) : null}
      </div>
    </div>
  );
}

export const Input = React.forwardRef<HTMLInputElement, Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> & { size?: "sm" | "md" }>(
  function Input({ className, size = "md", ...props }, ref) {
    return (
      <input
        ref={ref}
        className={cn(FIELD, size === "sm" ? "h-[30px]" : "h-[34px]", props.type === "number" && "num", className)}
        {...props}
      />
    );
  },
);

/** Decimal input for money/percent. Keeps the value a string end to end. */
export const NumericInput = React.forwardRef<
  HTMLInputElement,
  Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange" | "value" | "size"> & {
    value: string;
    onValueChange: (v: string) => void;
    suffix?: string;
    size?: "sm" | "md";
  }
>(function NumericInput({ className, value, onValueChange, suffix, size = "md", ...props }, ref) {
  return (
    <div className="relative">
      <input
        ref={ref}
        inputMode="decimal"
        autoComplete="off"
        value={value}
        onChange={(e) => {
          const next = e.target.value;
          // Permit only a well-formed decimal so nothing invalid reaches the API.
          if (next === "" || /^\d*\.?\d*$/.test(next)) onValueChange(next);
        }}
        className={cn(FIELD, "num text-right", size === "sm" ? "h-[30px]" : "h-[34px]", suffix && "pr-7", className)}
        {...props}
      />
      {suffix ? (
        <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-xs text-content-faint">
          {suffix}
        </span>
      ) : null}
    </div>
  );
});

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return <textarea ref={ref} className={cn(FIELD, "min-h-[76px] resize-y py-2 leading-[19px]", className)} {...props} />;
  },
);

export function SearchInput({
  value, onValueChange, placeholder = "Search", className,
}: { value: string; onValueChange: (v: string) => void; placeholder?: string; className?: string }) {
  return (
    <div className={cn("relative", className)}>
      <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-content-faint" />
      <input
        type="search"
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className={cn(FIELD, "h-[34px] pl-8")}
      />
    </div>
  );
}

/* -- Select (Radix, so keyboard + focus management come free) ------------- */
export interface Option { value: string; label: string; hint?: string }

export function Select({
  value, onValueChange, options, placeholder = "Select", id, disabled, className, size = "md", ariaLabel,
}: {
  value?: string; onValueChange: (v: string) => void; options: Option[];
  placeholder?: string; id?: string; disabled?: boolean; className?: string;
  size?: "sm" | "md"; ariaLabel?: string;
}) {
  return (
    <SelectPrim.Root value={value} onValueChange={onValueChange} disabled={disabled}>
      <SelectPrim.Trigger
        id={id}
        aria-label={ariaLabel}
        className={cn(
          FIELD, "flex items-center justify-between gap-2 text-left cursor-pointer",
          size === "sm" ? "h-[30px]" : "h-[34px]",
          className,
        )}
      >
        <SelectPrim.Value placeholder={<span className="text-content-faint">{placeholder}</span>} />
        <SelectPrim.Icon><ChevronDown className="size-3.5 text-content-faint" /></SelectPrim.Icon>
      </SelectPrim.Trigger>
      <SelectPrim.Portal>
        <SelectPrim.Content
          position="popper"
          sideOffset={4}
          className="z-50 max-h-72 min-w-[--radix-select-trigger-width] overflow-hidden rounded-md border border-line bg-white shadow-overlay animate-slide-up"
        >
          <SelectPrim.Viewport className="p-1">
            {options.map((o) => (
              <SelectPrim.Item
                key={o.value}
                value={o.value}
                className="relative flex cursor-pointer select-none items-center gap-2 rounded-sm py-1.5 pl-7 pr-2 text-base text-content outline-none data-[highlighted]:bg-accent-50 data-[highlighted]:text-accent-700"
              >
                <SelectPrim.ItemIndicator className="absolute left-2">
                  <Check className="size-3.5" />
                </SelectPrim.ItemIndicator>
                <SelectPrim.ItemText>{o.label}</SelectPrim.ItemText>
                {o.hint ? <span className="ml-auto text-xs text-content-faint">{o.hint}</span> : null}
              </SelectPrim.Item>
            ))}
          </SelectPrim.Viewport>
        </SelectPrim.Content>
      </SelectPrim.Portal>
    </SelectPrim.Root>
  );
}

/** Segmented control — for 2–5 mutually exclusive views. */
export function Segmented<V extends string>({
  value, onValueChange, options, className, ariaLabel,
}: {
  value: V; onValueChange: (v: V) => void;
  options: { value: V; label: React.ReactNode; count?: number }[];
  className?: string; ariaLabel: string;
}) {
  return (
    <div role="tablist" aria-label={ariaLabel} className={cn("inline-flex items-center gap-0.5 rounded-md border border-line bg-ink-100 p-[3px] shadow-xs", className)}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            role="tab"
            aria-selected={active}
            type="button"
            onClick={() => onValueChange(o.value)}
            className={cn(
              "inline-flex h-[26px] cursor-pointer items-center gap-1.5 rounded-[5px] px-2.5 font-ui text-[12px] font-medium transition-all duration-fast",
              active ? "bg-white text-content shadow-sm" : "text-content-muted hover:text-content",
            )}
          >
            {o.label}
            {o.count !== undefined ? (
              <span className={cn("num text-2xs", active ? "text-content-muted" : "text-content-faint")}>{o.count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export function Checkbox({
  checked, onCheckedChange, label, id, disabled,
}: { checked: boolean; onCheckedChange: (v: boolean) => void; label: React.ReactNode; id?: string; disabled?: boolean }) {
  const fieldId = useId(id);
  return (
    <div className="flex items-center gap-2">
      <input
        id={fieldId}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onCheckedChange(e.target.checked)}
        className="size-3.5 cursor-pointer rounded-xs border-line-strong accent-[var(--accent-600)]"
      />
      <label htmlFor={fieldId} className="cursor-pointer select-none text-sm text-content">{label}</label>
    </div>
  );
}

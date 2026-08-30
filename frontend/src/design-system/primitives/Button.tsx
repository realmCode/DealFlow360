import { Slot, Slottable } from "@radix-ui/react-slot";
import { Loader2 } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "approve" | "governance" | "link";
type Size = "xs" | "sm" | "md" | "lg";

const VARIANT: Record<Variant, string> = {
  primary:
    "bg-accent-600 text-white border border-accent-700 hover:bg-accent-700 active:bg-accent-800 shadow-[inset_0_1px_0_0_rgb(255_255_255/0.12)]",
  secondary:
    "bg-white text-content border border-line-strong hover:bg-ink-50 active:bg-ink-100",
  ghost: "bg-transparent text-content-secondary border border-transparent hover:bg-ink-100 hover:text-content",
  danger:
    "bg-[var(--policy-violated)] text-white border border-[var(--policy-violated)] hover:brightness-95 active:brightness-90",
  approve:
    "bg-[var(--policy-passed)] text-white border border-[var(--policy-passed)] hover:brightness-95 active:brightness-90",
  governance:
    "bg-gov-500 text-white border border-gov-600 hover:bg-gov-600 active:bg-gov-700",
  link: "bg-transparent border-none text-accent-600 hover:text-accent-700 hover:underline underline-offset-2 px-0",
};

const SIZE: Record<Size, string> = {
  xs: "h-6 px-2 text-xs gap-1 rounded-sm",
  sm: "h-7 px-2.5 text-sm gap-1.5 rounded-sm",
  md: "h-8 px-3 text-base gap-1.5 rounded-md",
  lg: "h-10 px-4 text-md gap-2 rounded-md",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  asChild?: boolean;
  icon?: React.ReactNode;
}

export function Button({
  className, variant = "secondary", size = "md", loading, asChild, icon, children, disabled, ...props
}: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      className={cn(
        "inline-flex select-none items-center justify-center whitespace-nowrap font-ui font-medium",
        "transition-colors duration-fast ease-smooth cursor-pointer",
        "disabled:pointer-events-none disabled:opacity-45",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500",
        VARIANT[variant], SIZE[size], className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Loader2 aria-hidden className="size-3.5 animate-spin" /> : icon}
      {/* Slottable marks the real child so `asChild` can merge props onto it
          while still rendering the icon inside — without it, Slot receives
          multiple children and throws. */}
      <Slottable>{children}</Slottable>
    </Comp>
  );
}

/** Square icon-only button. Always needs an accessible label. */
export function IconButton({
  className, variant = "ghost", size = "md", label, children, ...props
}: Omit<ButtonProps, "icon" | "asChild"> & { label: string }) {
  const box = size === "xs" ? "size-6" : size === "sm" ? "size-7" : size === "lg" ? "size-10" : "size-8";
  return (
    <button
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex items-center justify-center rounded-md cursor-pointer",
        "transition-colors duration-fast ease-smooth",
        "disabled:pointer-events-none disabled:opacity-45",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500",
        VARIANT[variant], box, className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

/**
 * The data table.
 *
 * Density from the ui-ux-pro-max Data-Dense Dashboard row: 36px rows, 12px
 * text, sticky header, row highlight on hover. Semantic <table> markup so
 * screen readers get real row/column relationships (shadcn stack CSV marks
 * this Severity: High).
 *
 * Long bodies get `content-visibility: auto` per react-best-practices.
 */
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/cn";

export interface Column<R> {
  id: string;
  header: React.ReactNode;
  /** Right-align numerics. */
  align?: "left" | "right" | "center";
  width?: string;
  cell: (row: R) => React.ReactNode;
  sortValue?: (row: R) => string | number;
  /** Hide below this breakpoint to keep narrow viewports readable. */
  hideBelow?: "sm" | "md" | "lg" | "xl";
  className?: string;
}

const HIDE: Record<string, string> = {
  sm: "hidden sm:table-cell",
  md: "hidden md:table-cell",
  lg: "hidden lg:table-cell",
  xl: "hidden xl:table-cell",
};

export function DataTable<R>({
  rows, columns, getKey, onRowClick, rail, empty, caption, dense, stickyHeader = true, className,
}: {
  rows: R[];
  columns: Column<R>[];
  getKey: (row: R) => string;
  onRowClick?: (row: R) => void;
  /** Per-row semantic rail colour — state readable before any text. */
  rail?: (row: R) => string | undefined | null;
  empty?: React.ReactNode;
  caption?: string;
  dense?: boolean;
  stickyHeader?: boolean;
  className?: string;
}) {
  const [sort, setSort] = React.useState<{ id: string; dir: "asc" | "desc" } | null>(null);

  const sorted = React.useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.id === sort.id);
    if (!col?.sortValue) return rows;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = col.sortValue!(a);
      const bv = col.sortValue!(b);
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv), undefined, { numeric: true }) * dir;
    });
  }, [rows, sort, columns]);

  const toggle = (id: string) =>
    setSort((s) => (s?.id !== id ? { id, dir: "asc" } : s.dir === "asc" ? { id, dir: "desc" } : null));

  if (rows.length === 0 && empty) return <>{empty}</>;

  const h = dense ? "h-[34px]" : "h-[38px]";

  return (
    <div className={cn("w-full overflow-x-auto", className)}>
      <table className="w-full border-collapse text-left">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead className={cn(stickyHeader && "sticky top-0 z-10")}>
          <tr className="border-b border-line bg-surface-sunken/80 backdrop-blur-[2px]">
            {rail ? <th className="w-[3px] p-0" aria-hidden /> : null}
            {columns.map((c) => {
              const active = sort?.id === c.id;
              const sortable = Boolean(c.sortValue);
              return (
                <th
                  key={c.id}
                  scope="col"
                  style={c.width ? { width: c.width } : undefined}
                  aria-sort={active ? (sort!.dir === "asc" ? "ascending" : "descending") : sortable ? "none" : undefined}
                  className={cn(
                    "h-[34px] whitespace-nowrap px-3 font-ui text-[10px] font-semibold uppercase tracking-[0.075em] text-content-faint",
                    c.align === "right" && "text-right",
                    c.align === "center" && "text-center",
                    c.hideBelow && HIDE[c.hideBelow],
                  )}
                >
                  {sortable ? (
                    <button
                      type="button"
                      onClick={() => toggle(c.id)}
                      className={cn(
                        "inline-flex cursor-pointer items-center gap-1 rounded-xs uppercase tracking-wider transition-colors hover:text-content",
                        active && "text-accent-600",
                        c.align === "right" && "flex-row-reverse",
                      )}
                    >
                      {c.header}
                      {active ? (
                        sort!.dir === "asc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />
                      ) : (
                        <ChevronsUpDown className="size-3 opacity-40" />
                      )}
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody style={{ contentVisibility: "auto" } as React.CSSProperties}>
          {sorted.map((row) => {
            const railColor = rail?.(row);
            return (
              <tr
                key={getKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={
                  onRowClick
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onRowClick(row);
                        }
                      }
                    : undefined
                }
                tabIndex={onRowClick ? 0 : undefined}
                role={onRowClick ? "button" : undefined}
                className={cn(
                  "border-b border-line-soft transition-colors duration-fast last:border-b-0",
                  onRowClick &&
                    "cursor-pointer hover:bg-accent-50/70 focus-visible:bg-accent-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-500",
                )}
              >
                {rail ? (
                  <td className="w-[3px] p-0">
                    <span aria-hidden className="block h-[38px] w-[3px]" style={{ background: railColor ?? "transparent" }} />
                  </td>
                ) : null}
                {columns.map((c) => (
                  <td
                    key={c.id}
                    className={cn(
                      h, "px-3 text-[13px] text-content align-middle",
                      c.align === "right" && "text-right",
                      c.align === "center" && "text-center",
                      c.hideBelow && HIDE[c.hideBelow],
                      c.className,
                    )}
                  >
                    {c.cell(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Primary cell content: a strong label with an optional dim second line. */
export function CellStack({ top, bottom }: { top: React.ReactNode; bottom?: React.ReactNode }) {
  return (
    <div className="min-w-0 leading-tight">
      <div className="truncate font-medium text-content">{top}</div>
      {bottom ? <div className="truncate text-xs text-content-muted">{bottom}</div> : null}
    </div>
  );
}

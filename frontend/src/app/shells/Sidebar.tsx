import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { NavLink } from "react-router-dom";
import { useApprovalInbox, useControlTower } from "@/api/queries";
import { useAuth, useCan } from "@/app/auth";
import { visibleGroups, type NavItem } from "@/app/nav";
import { Tooltip } from "@/design-system";
import { cn } from "@/lib/cn";

/** A 360° arc closing on a rising bar — deals, cycled. */
export function Wordmark({ collapsed }: { collapsed?: boolean }) {
  return (
    <span className="flex items-center gap-2.5 overflow-hidden">
      <svg viewBox="0 0 24 24" className="size-[22px] shrink-0" aria-hidden fill="none">
        <path
          d="M12 3.2a8.8 8.8 0 1 0 8.62 10.5"
          stroke="var(--accent-600)" strokeWidth="2.4" strokeLinecap="round"
        />
        <path d="M8.6 14.6V11m3.4 3.6V8.4m3.4 6.2v-2.1" stroke="var(--ink-900)" strokeWidth="2.2" strokeLinecap="round" />
      </svg>
      {!collapsed ? (
        <span className="whitespace-nowrap font-ui text-[15px] font-semibold tracking-[-0.02em] text-ink-900">
          DealFlow<span className="text-accent-600">360</span>
        </span>
      ) : null}
    </span>
  );
}

function Item({
  item, collapsed, count,
}: { item: NavItem; collapsed: boolean; count?: number }) {
  const Icon = item.icon;

  const link = (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) =>
        cn(
          "group relative flex h-8 items-center gap-2.5 rounded-md px-2 font-ui text-[13px] font-medium",
          "transition-colors duration-fast ease-smooth",
          collapsed && "justify-center px-0",
          isActive
            ? "bg-accent-100 text-accent-800"
            : "text-content-secondary hover:bg-ink-100 hover:text-content",
        )
      }
    >
      {({ isActive }) => (
        <>
          {/* active indicator sits outside the padding so labels stay aligned */}
          <span
            aria-hidden
            className={cn(
              "absolute left-[-8px] top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r-full transition-all duration-base",
              isActive ? "bg-accent-600 opacity-100" : "opacity-0",
            )}
          />
          <Icon className={cn("size-[15px] shrink-0", isActive ? "text-accent-700" : "text-content-faint group-hover:text-content-secondary")} />
          {!collapsed ? <span className="min-w-0 flex-1 truncate">{item.label}</span> : null}
          {!collapsed && count ? (
            <span
              className={cn(
                "num shrink-0 rounded-pill px-1.5 text-[10px] font-semibold leading-[16px]",
                item.badge === "attention" ? "bg-[var(--risk-critical)] text-white" : "bg-accent-600 text-white",
              )}
            >
              {count}
            </span>
          ) : null}
          {collapsed && count ? (
            <span
              aria-hidden
              className={cn(
                "absolute right-1.5 top-1.5 size-1.5 rounded-full",
                item.badge === "attention" ? "bg-[var(--risk-critical)]" : "bg-accent-600",
              )}
            />
          ) : null}
        </>
      )}
    </NavLink>
  );

  if (!collapsed) return link;
  return (
    <Tooltip side="right" content={count ? `${item.label} · ${count}` : item.label}>
      {link}
    </Tooltip>
  );
}

export function Sidebar({
  collapsed, onToggle, onNavigate,
}: { collapsed: boolean; onToggle: () => void; onNavigate?: () => void }) {
  const { user } = useAuth();
  const can = useCan();
  const groups = visibleGroups(user?.role);

  const tower = useControlTower();
  const inbox = useApprovalInbox(can.approve);
  const counts = {
    attention: tower.data?.counts?.critical || undefined,
    approvals: inbox.data?.length || undefined,
  };

  return (
    <div
      className={cn(
        "flex h-full flex-col border-r border-line bg-[var(--rail)] transition-[width] duration-base ease-smooth",
        collapsed ? "w-[var(--sidebar-w-collapsed)]" : "w-[var(--sidebar-w)]",
      )}
      onClick={onNavigate}
    >
      <div className={cn("flex h-[var(--topbar-h)] shrink-0 items-center border-b border-line", collapsed ? "justify-center px-2" : "px-3.5")}>
        <NavLink to="/" className="rounded-sm" aria-label="DealFlow360 home">
          <Wordmark collapsed={collapsed} />
        </NavLink>
      </div>

      <nav
        aria-label="Modules"
        className="scrollbar-none min-h-0 flex-1 overflow-y-auto px-2 py-3"
      >
        {groups.map((group, gi) => (
          <div key={group.id} className={cn(gi > 0 && "mt-4")}>
            {!collapsed ? (
              <p className="mb-1 px-2 font-ui text-[10px] font-semibold uppercase tracking-[0.09em] text-content-faint">
                {group.label}
              </p>
            ) : gi > 0 ? (
              <div aria-hidden className="mx-auto mb-3 h-px w-6 bg-line" />
            ) : null}
            <div className="space-y-px">
              {group.items.map((item) => (
                <Item
                  key={item.to}
                  item={item}
                  collapsed={collapsed}
                  count={item.badge ? counts[item.badge] : undefined}
                />
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className={cn("shrink-0 border-t border-line p-2", collapsed && "flex justify-center")}>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onToggle();
          }}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "flex h-8 cursor-pointer items-center gap-2.5 rounded-md text-content-faint transition-colors hover:bg-ink-100 hover:text-content-secondary",
            collapsed ? "w-8 justify-center" : "w-full px-2",
          )}
        >
          {collapsed ? <PanelLeftOpen className="size-[15px]" /> : <PanelLeftClose className="size-[15px]" />}
          {!collapsed ? <span className="font-ui text-[13px] font-medium">Collapse</span> : null}
        </button>
      </div>
    </div>
  );
}

import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "@/context/useAuth";
import { Icon, type IconName } from "@/components/Icon";
import { cn } from "@/lib/cn";

const NAV: Array<{ to: string; label: string; icon: IconName; end?: boolean }> = [
  { to: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { to: "/recommendations", label: "Recommendations", icon: "list" },
  { to: "/analysis", label: "Analyze & Approve", icon: "science" },
];

export function AuthenticatedLayout({ children }: { children: ReactNode }) {
  const { displayName, logout, status } = useAuth();
  const [expanded, setExpanded] = useState(true);

  const gmailEmail = status?.gmail_connection?.email;

  return (
    <div className="flex min-h-screen bg-obsidian">
      {/* Side nav rail */}
      <aside
        className={cn(
          "sticky top-0 flex h-screen shrink-0 flex-col border-r border-panel-border bg-surface-lowest transition-[width] duration-200",
          expanded ? "w-60" : "w-[76px]"
        )}
        aria-label="Primary"
      >
        <div className="flex items-center justify-between px-4 py-5">
          <div className="flex items-center gap-2 overflow-hidden">
            <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-data-blue" aria-hidden="true" />
            <span className={cn("font-display text-base font-semibold text-white", !expanded && "hidden")}>
              MailSweep
            </span>
          </div>
          <button
            type="button"
            className="hidden items-center gap-1 rounded-sm p-1 text-neutral-grey-60 transition-colors hover:text-white md:flex"
            onClick={() => setExpanded((e) => !e)}
            aria-label={expanded ? "Collapse navigation" : "Expand navigation"}
          >
            <Icon name={expanded ? "menu" : "menu"} className="text-[1.4rem]" />
          </button>
        </div>

        <nav className="flex flex-1 flex-col gap-1 px-2 py-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-sm px-3 py-2.5 text-body-md transition-colors",
                  expanded ? "justify-start" : "justify-center",
                  isActive
                    ? "bg-data-blue/10 text-data-blue"
                    : "text-neutral-grey-60 hover:bg-surface-low hover:text-white"
                )
              }
            >
              <Icon name={item.icon} className="shrink-0 text-[1.3rem]" />
              {expanded && <span className="truncate">{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-panel-border p-3">
          <div className={cn("flex items-center gap-3", !expanded && "justify-center")}>
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-data-blue/40 bg-surface font-display text-sm font-semibold text-data-blue">
              {(displayName ?? "?").charAt(0).toUpperCase()}
            </div>
            {expanded && (
              <div className="min-w-0 flex-1">
                <p className="truncate text-body-sm text-white">{displayName ?? "User"}</p>
                {gmailEmail && <p className="truncate text-[0.7rem] text-neutral-grey-60">{gmailEmail}</p>}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => void logout()}
            className={cn(
              "mt-3 flex w-full items-center gap-3 rounded-sm px-3 py-2 text-body-sm text-neutral-grey-60 transition-colors hover:bg-surface-low hover:text-white",
              !expanded && "justify-center"
            )}
          >
            <Icon name="logout" className="shrink-0" />
            {expanded && <span>Sign out</span>}
          </button>
        </div>
      </aside>

      {/* Content */}
      <main className="min-w-0 flex-1 px-gutter py-6 md:px-8 md:py-8">{children}</main>
    </div>
  );
}
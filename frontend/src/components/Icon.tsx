import { cn } from "@/lib/cn";

/** Material Symbols Outlined glyphs (font loaded in index.html). */
export type IconName =
  | "dashboard"
  | "list"
  | "science"
  | "radio_button_checked"
  | "check_circle"
  | "logout"
  | "delete"
  | "refresh"
  | "scan"
  | "archive"
  | "rocket_launch"
  | "priority_high"
  | "shield"
  | "menu"
  | "close";

const MAP: Record<IconName, string> = {
  dashboard: "dashboard",
  list: "format_list_bulleted",
  science: "science",
  radio_button_checked: "radio_button_checked",
  check_circle: "check_circle",
  logout: "logout",
  delete: "delete",
  refresh: "refresh",
  scan: "radar",
  archive: "archive",
  rocket_launch: "rocket_launch",
  priority_high: "priority_high",
  shield: "shield",
  menu: "menu",
  close: "close",
};

export function Icon({
  name,
  className,
  filled,
}: {
  name: IconName;
  className?: string;
  filled?: boolean;
}) {
  // font-variation-settings backgrounds `wght`/`FILL` per-instance.
  return (
    <span
      aria-hidden="true"
      className={cn(
        "material-symbols-outlined select-none align-middle text-[1.2em] leading-none",
        className
      )}
      style={{
        fontVariationSettings: `'FILL' ${filled ? 1 : 0}, 'wght' 400`,
      }}
    >
      {MAP[name]}
    </span>
  );
}
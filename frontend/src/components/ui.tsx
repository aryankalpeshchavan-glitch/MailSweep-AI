import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/** Accessible loading spinner. */
export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block h-5 w-5 animate-spin rounded-full border-2 border-data-blue-dim/30 border-t-data-blue",
        className
      )}
      role="status"
      aria-label="Loading"
    />
  );
}

/** Centered, labelled loading block. */
export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center gap-stack-sm py-stack-lg text-center">
      <Spinner />
      <p className="data-label">{label}</p>
    </div>
  );
}

/** Generic empty state (used across dashboard / lists). */
export function EmptyState({
  title = "Nothing here yet",
  body,
  action,
}: {
  title?: string;
  body?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="panel flex flex-col items-center gap-stack-md px-6 py-stack-lg text-center">
      <p className="data-label data-label-accent">NO DATA</p>
      <h3 className="text-headline-md">{title}</h3>
      {body && <p className="max-w-md text-body-md text-neutral-grey-60">{body}</p>}
      {action}
    </div>
  );
}

/** Error state with an explicit retry. */
export function ErrorState({
  message = "Something went wrong while loading this data.",
  onRetry,
  detail,
}: {
  message?: string;
  detail?: ReactNode;
  onRetry?: () => void;
}) {
  return (
    <div className="panel flex flex-col items-center gap-stack-md border-violet px-6 py-stack-lg text-center">
      <p className="data-label data-label-warn">SYSTEM ERROR</p>
      <h3 className="text-headline-md text-neutral-white">Unable to load</h3>
      <p className="max-w-md text-body-md text-neutral-grey-60">{message}</p>
      {detail && <div className="w-full text-left text-body-sm text-neutral-grey-60">{detail}</div>}
      {onRetry && (
        <button className="btn btn-secondary" type="button" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

/** Precision-outline data panel with an optional mono header label. */
export function DataPanel({
  label,
  children,
  className,
  accent,
}: {
  label?: string;
  children: ReactNode;
  className?: string;
  accent?: "blue" | "violet";
}) {
  return (
    <section
      className={cn("panel overflow-hidden", accent === "violet" && "panel-ai", className)}
    >
      {label && (
        <div className="flex items-center justify-between border-b border-panel-border px-5 py-3">
          <span className={cn("data-label", accent === "blue" && "data-label-accent")}>{label}</span>
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

/** Big histogram-style stat shown on the dashboard. */
export function StatCard({
  label,
  value,
  accent,
  suffix,
}: {
  label: string;
  value: ReactNode;
  accent?: "blue" | "amber" | "violet" | "default";
  suffix?: string;
}) {
  const accentCls = {
    blue: "text-data-blue",
    amber: "text-safety-amber",
    violet: "text-neural-violet-container",
    default: "text-neutral-white",
  }[accent ?? "default"];
  return (
    <div className="panel p-5">
      <p className="data-label">{label}</p>
      <div className="mt-3 flex items-baseline gap-2">
        <span className={cn("font-display text-headline-lg font-semibold", accentCls)}>{value}</span>
        {suffix && <span className="text-body-sm text-neutral-grey-60">{suffix}</span>}
      </div>
    </div>
  );
}

/** Thin cinematic progress bar. */
export function ProgressBar({
  value,
  max = 100,
  label,
}: {
  value: number;
  max?: number;
  label?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="w-full">
      <div className="mb-1 flex items-center justify-between">
        {label && <span className="data-label">{label}</span>}
        <span className="data-label data-label-accent">{Math.round(pct)}%</span>
      </div>
      <div
        className="h-1 w-full overflow-hidden rounded-full bg-neutral-grey-40/30"
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-full bg-data-blue transition-[width] duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/** Simple pulsing placeholder grid for skeleton screens. */
export function SkeletonBlock({ lines = 4, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-3", className)} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-4 animate-pulse rounded-sm bg-neutral-grey-40/20"
          style={{ width: `${100 - (i % 3) * 20}%` }}
        />
      ))}
    </div>
  );
}
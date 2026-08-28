import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { startAnalysis } from "@/api/endpoints";
import { useAnalysisJobPoll, useMailboxSummary } from "@/api/queries";
import { useAuth } from "@/context/useAuth";
import { ApiError } from "@/lib/apiClient";
import { formatDate, formatNumber, humanize } from "@/lib/format";
import { DataPanel, EmptyState, ErrorState, ProgressBar, Spinner, StatCard } from "@/components/ui";
import type { MailboxSummary } from "@/types/api";

/** Dashboard (Phase 8) — real data from /api/mailbox/summary (Phase 8). */
export function DashboardPage() {
  const { status } = useAuth();
  const summary = useMailboxSummary();
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const poll = useAnalysisJobPoll(jobId, Boolean(jobId));

  const start = useMutation({
    mutationFn: startAnalysis,
    onSuccess: (res) => setJobId(res.job_id),
  });

    useEffect(() => {
    if (poll.data && (poll.data.status === "COMPLETED" || poll.data.status === "FAILED")) {
      void queryClient.invalidateQueries({ queryKey: ["mailbox", "summary"] });
    }
  }, [poll.data, queryClient]);

  const s = summary.data;
  const startError = start.error ? (start.error as ApiError).message : null;
  const analyzing = start.isPending || Boolean(poll.data);
  const canAnalyze = Boolean(status?.gmail_connection?.connected);

  return (
    <div className="mx-auto max-w-container space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="data-label data-label-accent mb-1">DASHBOARD</p>
          <h1 className="text-headline-lg text-white">Inbox health</h1>
          <p className="mt-1 text-body-sm text-neutral-grey-60">
            {canAnalyze ? "Gmail connected" : "Gmail not connected"} ·{" "}
            {status?.gmail_connection?.email ?? "—"}
          </p>
        </div>
        <button
          className="btn btn-primary"
          type="button"
          onClick={() => start.mutate()}
          disabled={analyzing || !canAnalyze}
          aria-busy={analyzing}
        >
          {analyzing ? <Spinner className="h-4 w-4" /> : null}
          {analyzing ? "Analyzing…" : "Run analysis"}
        </button>
      </div>

      {startError && (
        <div className="panel panel-strong p-4 text-body-sm text-safety-amber" role="alert">
          {startError}
        </div>
      )}

      {/* Live analysis progress (real backend data). */}
      {poll.data ? (
        <DataPanel label="Analysis in progress" accent="blue">
          <div className="mb-2 flex items-center justify-between">
            <span className="data-label">{humanize(poll.data.status)}</span>
            <span className="data-label data-label-accent">
              {formatNumber(poll.data.messages_processed)} / {formatNumber(poll.data.messages_total)}
            </span>
          </div>
          <ProgressBar value={poll.data.progress_percent ?? 0} label="Progress" />
                              {poll.data.error_message && (
            <p className="mt-3 text-xs text-neutral-grey-60">{poll.data.error_message}</p>
          )}
        </DataPanel>
      ) : null}

      {summary.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="panel h-24 animate-pulse p-5" />
          ))}
        </div>
      ) : summary.isError ? (
        <ErrorState message="Could not load your mailbox summary." onRetry={() => void summary.refetch()} />
      ) : !s || !s.analyzed ? (
        <EmptyState
          title="No analysis yet"
          body={
            <>
              A first analysis populates your dashboard. Nothing is modified on
              Gmail — this only reads metadata.
            </>
          }
          action={
            <button
              className="btn btn-primary"
              type="button"
              onClick={() => start.mutate()}
              disabled={analyzing || !canAnalyze}
            >
                            Start analysis
            </button>
          }
        />
      ) : (
        <DashboardStats summary={s} />
      )}
    </div>
  );
}

/** Real stat grid + risk breakdown + top groups (Phase 8). */
function DashboardStats({ summary }: { summary: MailboxSummary }) {
  const rec = summary.recommendations;
  const mb = summary.mailbox;
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Messages cached" value={formatNumber(mb?.total_messages_cached)} />
        <StatCard label="Move to trash" value={formatNumber(rec?.move_to_trash)} accent="blue" />
        <StatCard label="Review" value={formatNumber(rec?.review)} accent="violet" />
        <StatCard label="Keep" value={formatNumber(rec?.keep)} />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <DataPanel label="Trash candidates by risk" accent="blue">
          <RiskBar label="Low" value={rec?.trash_by_risk.low ?? 0} tone="blue" />
          <RiskBar label="Medium" value={rec?.trash_by_risk.medium ?? 0} tone="violet" />
          <RiskBar label="High" value={rec?.trash_by_risk.high ?? 0} tone="amber" />
        </DataPanel>

        <DataPanel label="Top groups" className="lg:col-span-2">
          {summary.top_groups && summary.top_groups.length > 0 ? (
            <ul className="divide-y divide-panel-border">
              {summary.top_groups.map((g) => (
                <li key={g.id} className="flex items-center justify-between gap-3 py-2.5">
                  <div className="min-w-0">
                    <p className="truncate text-body-md text-white">{g.display_name}</p>
                    <p className="data-label mt-0.5">{g.category ?? "uncategorised"}</p>
                  </div>
                  <span className="shrink-0 font-mono text-body-sm text-data-blue">
                    {formatNumber(g.message_count)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-body-sm text-neutral-grey-60">No groups yet.</p>
          )}
        </DataPanel>
      </div>

      {mb?.last_analysis_at && (
        <p className="text-xs text-neutral-grey-60">Last analysis: {formatDate(mb.last_analysis_at)}</p>
      )}
    </>
  );
}

/** Slim horizontal risk metre. */
function RiskBar({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "blue" | "violet" | "amber";
}) {
  const max = 1000; // visual scale for the metre
  const pct = Math.min(100, (value / max) * 100);
  const color =
    tone === "amber"
      ? "var(--safety-amber)"
      : tone === "violet"
        ? "var(--neural-violet-container)"
        : "var(--data-blue)";
  return (
    <div className="mb-4">
      <div className="mb-1 flex items-center justify-between">
        <span className="data-label">{label}</span>
        <span className="font-mono text-body-sm text-white">{value}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-low">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

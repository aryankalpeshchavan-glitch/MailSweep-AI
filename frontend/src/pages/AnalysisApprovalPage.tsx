import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { startAnalysis, cancelPlan } from "@/api/endpoints";
import { useAnalysisJobPoll, usePlans } from "@/api/queries";
import type { ApiError } from "@/lib/apiClient";
import { formatNumber, formatDate, humanize } from "@/lib/format";
import { cn } from "@/lib/cn";
import {
  DataPanel,
  ErrorState,
  LoadingBlock,
  ProgressBar,
  StatCard,
  Spinner,
  EmptyState,
} from "@/components/ui";
import type { AnalysisJob, CleanupPlan } from "@/types/api";

/**
 * Phase 10 — Analysis / Approval three-stage experience.
 *
 * STAGE 1 (Scanning): Kick off a backend analysis job; poll progress live.
 * STAGE 2 (Review): List cleanup plans produced by analysis; show status.
 * STAGE 3 (Success): Plan dispatched / completed — show results, allow retry.
 *
 * The browser NEVER deletes mail. Cleanup flows through backend plan
 * preview → approve → dispatch (see RecommendationsPage for the full
 * approve flow). This page orchestrates the analysis → plan lifecycle.
 */
export function AnalysisApprovalPage() {
  const [jobId, setJobId] = useState<string | null>(null);

  const start = useMutation({
    mutationFn: startAnalysis,
    onSuccess: (res) => {
      setJobId(res.job_id);
    },
  });

  const poll = useAnalysisJobPoll(jobId, Boolean(jobId));
  const plansQuery = usePlans("APPROVED"); // plans awaiting execution or done

  // Invalidate plans when an analysis job completes
  useEffect(() => {
    if (poll.data?.status === "COMPLETED" || poll.data?.status === "FAILED") {
      void plansQuery.refetch();
    }
  }, [poll.data?.status, plansQuery]);

  const handleStart = () => start.mutate();

  const startError = start.error ? (start.error as ApiError).message : null;
  const jobError = poll.error ? (poll.error as ApiError).message : null;

  const stage = (() => {
    if (!jobId) return "idle" as const;
    if (poll.data && (poll.data.status === "COMPLETED" || poll.data.status === "FAILED")) {
      return "complete" as const;
    }
    return "scanning" as const;
  })();

  return (
    <div className="mx-auto max-w-container space-y-6">
      {/* Header */}
      <div>
        <p className="data-label data-label-accent mb-1">ANALYSIS &amp; APPROVAL</p>
        <h1 className="text-headline-lg text-white">Cleanup pipeline</h1>
        <p className="mt-1 text-body-sm text-neutral-grey-60">
          Run an analysis to discover cleanup opportunities, then review the
          resulting plans before approving any action.
        </p>
      </div>

      {/* Stage: Idle / Start */}
      {stage === "idle" && (
        <DataPanel label="Ready to scan" accent="blue">
          <p className="text-body-sm text-neutral-grey-60 mb-4">
            {startError ? (
              <span className="text-safety-amber">{startError}</span>
            ) : (
              "Click below to kick off a fresh mailbox analysis. This only reads metadata."
            )}
          </p>
          <button
            className="btn btn-primary"
            onClick={handleStart}
            disabled={start.isPending}
            aria-busy={start.isPending}
          >
            {start.isPending ? <Spinner className="h-4 w-4" /> : null}
            {start.isPending ? "Starting scan…" : "Run analysis"}
          </button>
        </DataPanel>
      )}

      {/* Stage: Scanning */}
      {stage === "scanning" && poll.data && (
        <ScanningStage job={poll.data} isPolling={poll.isFetching} error={jobError} />
      )}

      {/* Stage: Complete — show plans */}
      {stage === "complete" && poll.data && (
        <CompleteStage
          job={poll.data}
          plansQuery={plansQuery}
          plansError={plansQuery.error ? (plansQuery.error as ApiError).message : null}
        />
      )}
    </div>
  );
}

interface ScanningStageProps {
  job: AnalysisJob;
  isPolling: boolean;
  error: string | null;
}

function ScanningStage({ job, isPolling, error }: ScanningStageProps) {
  return (
    <DataPanel
      label="Scanning mailbox"
      accent="blue"
      className="space-y-4"
    >
      <div className="flex items-center justify-between">
        <span className="data-label">{humanize(job.status)}</span>
        {isPolling && <Spinner className="h-4 w-4 animate-spin text-data-blue" />}
      </div>

      <ProgressBar
        value={job.progress_percent ?? 0}
        label="Progress"
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          label="Processed"
          value={formatNumber(job.messages_processed ?? 0)}
        />
        <StatCard
          label="Total"
          value={formatNumber(job.messages_total ?? 0)}
        />
        <StatCard
          label="Rate"
          value={
            job.messages_processed && job.started_at
              ? `${formatNumber(job.messages_processed)} msg`
              : "—"
          }
        />
        <StatCard
          label="ETA"
          value="—"
        />
      </div>

      {startedAtDisplay(job)}
      {error && (
        <p className="text-body-sm text-safety-amber">{error}</p>
      )}
      {job.error_message && (
        <p className="text-body-sm text-safety-amber">{job.error_message}</p>
      )}
    </DataPanel>
  );
}

function startedAtDisplay(job: AnalysisJob) {
  if (!job.started_at) return null;
  return (
    <p className="text-body-xs text-neutral-grey-60">
      Started {formatDate(job.started_at)}
    </p>
  );
}


interface CompleteStageProps {
  job: AnalysisJob;
  plansQuery: {
    data: CleanupPlan[] | undefined;
    isLoading: boolean;
    isError: boolean;
    refetch: () => void;
  };
  plansError: string | null;
}

function CompleteStage({ job, plansQuery, plansError }: CompleteStageProps) {
  const { data: plans, isLoading, isError, refetch } = plansQuery;
  const isFailed = job.status === "FAILED";

  return (
    <div className="space-y-6">
      {/* Job result summary */}
      <DataPanel
        label={isFailed ? "Analysis failed" : "Analysis complete"}
        accent={isFailed ? undefined : "blue"}
      >
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard
            label="Messages scanned"
            value={formatNumber(job.messages_processed ?? 0)}
          />
          <StatCard
            label="Total"
            value={formatNumber(job.messages_total ?? 0)}
            accent={job.progress_percent === 100 ? "blue" : "amber"}
          />
          <StatCard label="Completed" value={formatDate(job.completed_at)} />
          <StatCard
            label="Recommendations"
            value={formatNumber(plans?.length ?? 0)}
          />
        </div>
        {job.error_message && isFailed && (
          <p className="mt-3 text-body-sm text-safety-amber">{job.error_message}</p>
        )}
      </DataPanel>

      {/* Plans list */}
      <div>
        <h2 className="text-headline-md text-white mb-3">Cleanup plans</h2>
        {isLoading ? (
          <LoadingBlock label="Loading plans…" />
        ) : isError ? (
          <ErrorState
            message={plansError ?? "Could not load cleanup plans."}
            onRetry={() => void refetch()}
          />
        ) : !plans || plans.length === 0 ? (
          <EmptyState
            title="No plans yet"
            body={
              isFailed
                ? "The last analysis run failed. Please try again."
                : "No cleanup plans are currently available. Run a new analysis to generate them."
            }
          />
        ) : (
          <div className="space-y-3">
            {plans.map((plan) => (
              <PlanCard key={plan.id} plan={plan} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

interface PlanCardProps {
  plan: CleanupPlan;
}

function PlanCard({ plan }: PlanCardProps) {
  const [canceling, setCanceling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const handleCancel = async () => {
    setCanceling(true);
    setCancelError(null);
    try {
      await cancelPlan(plan.id);
    } catch (e) {
      setCancelError(e instanceof Error ? e.message : "Failed to cancel plan");
    } finally {
      setCanceling(false);
    }
  };

  const statusTone =
    plan.status === "COMPLETED"
      ? "text-data-blue"
      : plan.status === "FAILED" || plan.status === "CANCELED"
        ? "text-safety-amber"
        : "text-neutral-white";

  return (
    <div className="panel p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-body-md text-white">
            {humanize(plan.status)} plan
          </p>
          <p className="data-label mt-1">ID {plan.id}</p>
        </div>
        <div className="shrink-0 text-right">
          <span className={cn("font-mono text-body-md", statusTone)}>
            {formatNumber(plan.message_count)} messages
          </span>
          <p className="data-label">{humanize(plan.status)}</p>
        </div>
      </div>

      {(plan.approved_at || plan.created_at) && (
        <div className="mt-3 flex flex-wrap gap-4 text-body-xs text-neutral-grey-60">
          {plan.created_at && <span>Created {formatDate(plan.created_at)}</span>}
          {plan.approved_at && <span>Approved {formatDate(plan.approved_at)}</span>}
          {plan.completed_at && <span>Completed {formatDate(plan.completed_at)}</span>}
        </div>
      )}

      {/* Items preview (if present) */}
      {plan.items && plan.items.length > 0 && (
        <ul className="mt-3 max-h-48 divide-y divide-panel-border overflow-y-auto">
          {plan.items.slice(0, 20).map((item) => (
            <li key={item.message_id} className="flex items-center justify-between gap-3 py-2">
              <span className="truncate text-body-sm text-neutral-grey-60">
                {item.subject_snapshot ?? "(no subject)"}
              </span>
              <span className="shrink-0 data-label">{humanize(item.item_status)}</span>
            </li>
          ))}
        </ul>
      )}

      {/* Failure summary */}
      {plan.failure_summary && (
        <div className="mt-3">
          {Object.entries(plan.failure_summary).map(([k, v]) => (
            <p key={k} className="text-body-xs text-safety-amber">
              {humanize(k)}: {String(v)}
            </p>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="mt-4 flex items-center gap-3">
        {plan.status === "APPROVED" || plan.status === "EXECUTING" ? (
          <button
            className="btn btn-amber"
            onClick={handleCancel}
            disabled={canceling}
          >
            {canceling ? "Cancelling…" : "Cancel plan"}
          </button>
        ) : null}
        {cancelError && (
          <span className="text-body-sm text-safety-amber">{cancelError}</span>
        )}
        {plan.status === "COMPLETED" && (
          <span className="text-body-sm text-data-blue">Cleanup complete.</span>
        )}
        {plan.status === "FAILED" && (
          <span className="text-body-sm text-safety-amber">
            This plan failed and may need to be re-created.
          </span>
        )}
      </div>
    </div>
  );
}

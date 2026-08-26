import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createPlanPreview, approvePlan } from "@/api/endpoints";
import { useRecommendations } from "@/api/queries";
import type { ApiError } from "@/lib/apiClient";
import { formatNumber, formatPercent, humanize, riskLabel } from "@/lib/format";
import { cn } from "@/lib/cn";
import {
  EmptyState,
  ErrorState,
  StatCard,
  SkeletonBlock,
} from "@/components/ui";
import type { RecommendationListItem, RiskLevel } from "@/types/api";

export function RecommendationsPage() {
  const [action, setAction] = useState<string | undefined>();
  const [risk, setRisk] = useState<string | undefined>();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const queryClient = useQueryClient();

  const { data, isLoading, isError, refetch } = useRecommendations({
    action,
    risk,
    page: 1,
    page_size: 100,
  });

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const preview = useMutation({
    mutationFn: createPlanPreview,
    onError: () => setSelected(new Set()),
  });

  const approve = useMutation({
    mutationFn: (planId: string) => approvePlan(planId),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["recommendations"] }),
  });

    const error = (preview.error ?? approve.error) as ApiError | null;
  const items = useMemo(() => data?.items ?? [], [data?.items]);
  const byCategory = useMemo(() => groupByCategory(items), [items]);
  const selectedItems = useMemo(
    () => items.filter((i) => selected.has(i.id)),
    [items, selected]
  );
  const selectedCount = selected.size;
  const totalCount = data?.total ?? 0;

  const handleApprove = async () => {
    if (!selectedCount) return;
    const plan = await preview.mutateAsync({
      recommendation_ids: Array.from(selected),
      idempotency_key: crypto.randomUUID(),
    });
    await approve.mutateAsync(plan.id);
    setSelected(new Set());
  };

  const handleClear = () => setSelected(new Set());




  return (
    <div className="mx-auto max-w-container space-y-6">
      {/* Page header */}
      <header>
        <p className="data-label data-label-accent mb-1">RECOMMENDATIONS</p>
        <h1 className="text-headline-lg text-white">Suggested cleanup</h1>
        <p className="mt-1 max-w-2xl text-body-sm text-neutral-grey-60">
          MailSweep analyzes and recommends. Approving below moves mail only to
          Gmail&apos;s Trash through the backend — nothing destructive happens
          in the browser. You decide.
        </p>
      </header>

      {/* Summary stats */}
      {data && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Total recommendations"
            value={formatNumber(data.total)}
            accent="blue"
          />
          <StatCard
            label="Move to trash"
            value={formatNumber(
              countBy(items, (i) => i.action === "MOVE_TO_TRASH")
            )}
            accent="amber"
          />
          <StatCard
            label="Needs review"
            value={formatNumber(
              countBy(items, (i) => i.action === "REVIEW")
            )}
            accent="violet"
          />
          <StatCard
            label="Keep"
            value={formatNumber(countBy(items, (i) => i.action === "KEEP"))}
            accent="default"
          />
        </div>
      )}

      {/* Category counts */}
      {data && data.items.length > 0 && (
        <CategoryCounts byCategory={byCategory} />
      )}

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3">
        <Select
          label="Action"
          value={action}
          onChange={setAction}
          options={["", "MOVE_TO_TRASH", "REVIEW", "KEEP"]}
        />
        <Select
          label="Risk"
          value={risk}
          onChange={setRisk}
          options={["", "LOW", "MEDIUM", "HIGH"]}
        />
        <span className="ml-auto self-center text-sm text-neutral-grey-60">
          {formatNumber(totalCount)} pending · {selectedCount} selected
        </span>
      </div>

      {/* Main content */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonBlock key={i} lines={4} className="panel" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          message="Could not load recommendations."
          onRetry={() => void refetch()}
        />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="Nothing to act on"
          body="Run a fresh analysis to surface new cleanup recommendations."
        />
      ) : (
        <div className="space-y-4">
          {selectedCount > 0 && (
            <ApprovalBar
              selectedCount={selectedCount}
              selectedItems={selectedItems}
              previewPending={preview.isPending}
              approvePending={approve.isPending}
              error={error}
              onApprove={handleApprove}
              onClear={handleClear}
              totalCount={totalCount}
            />
          )}
          <div className="space-y-3">
            {items.map((item) => (
                            <RecommendationRow
                key={item.id}
                item={item}
                selected={selected.has(item.id)}
                onSelect={toggle}
              />
            ))}
          </div>
          <div className="flex justify-between text-body-sm text-neutral-grey-60">
            <span>
              Showing {formatNumber(items.length)} of {formatNumber(totalCount)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

function countBy(
  items: RecommendationListItem[],
  match: (i: RecommendationListItem) => boolean
): number {
  let n = 0;
  for (const i of items) if (match(i)) n++;
  return n;
}

function groupByCategory(
  items: RecommendationListItem[]
): Array<[string, RecommendationListItem[]]> {
  const map = new Map<string, RecommendationListItem[]>();
  for (const item of items) {
    const cat = item.category ?? "uncategorised";
    const arr = map.get(cat) ?? [];
    arr.push(item);
    map.set(cat, arr);
  }
  return Array.from(map.entries());
}

interface SelectProps {
  label: string;
  value?: string;
  onChange: (v?: string) => void;
  options: string[];
}

function Select({ label, value, onChange, options }: SelectProps) {
  return (
    <label className="flex items-center gap-2">
      <span className="data-label">{label}</span>
      <select
        className="input w-auto"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || undefined)}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o ? humanize(o) : "All"}
          </option>
        ))}
      </select>
    </label>
  );
}

function CategoryCounts({
  byCategory,
}: {
  byCategory: Array<[string, RecommendationListItem[]]>;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {byCategory.map(([cat, list]) => (
        <StatCard
          key={cat}
          label={humanize(cat)}
          value={formatNumber(list.length)}
          accent="default"
        />
      ))}
    </div>
  );
}

function ApprovalBar({
  selectedCount,
  selectedItems,
  previewPending,
  approvePending,
  error,
  onApprove,
  onClear,
  totalCount,
}: {
  selectedCount: number;
  selectedItems: RecommendationListItem[];
  previewPending: boolean;
  approvePending: boolean;
  error: ApiError | null;
  onApprove: () => void;
  onClear: () => void;
  totalCount: number;
}) {
  const progress = totalCount > 0 ? (selectedCount / totalCount) * 100 : 0;
  const isProcessing = previewPending || approvePending;
  const lowRisk = selectedItems.filter((i) => i.risk === "LOW").length;
  const medRisk = selectedItems.filter((i) => i.risk === "MEDIUM").length;
  const highRisk = selectedItems.filter((i) => i.risk === "HIGH").length;

  return (
    <div className="panel space-y-4 p-5">
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <span className="text-body-sm text-data-blue">{lowRisk}</span>
          <p className="data-label">Low risk</p>
        </div>
        <div>
          <span className="text-body-sm text-safety-amber">{medRisk}</span>
          <p className="data-label">Medium risk</p>
        </div>
        <div>
          <span className="text-body-sm text-neutral-white">{highRisk}</span>
          <p className="data-label">High risk</p>
        </div>
      </div>
      <div className="mb-1 flex items-center justify-between">
        <span className="data-label">{selectedCount} of {totalCount} selected</span>
        <span className="data-label data-label-accent">{Math.round(progress)}%</span>
      </div>
      <div
        className="h-1 w-full overflow-hidden rounded-full bg-neutral-grey-40/30"
        role="progressbar"
        aria-valuenow={Math.round(progress)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-full bg-data-blue transition-[width] duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>
      <div className="flex items-center gap-3">
        <button
          className="btn btn-amber"
          disabled={isProcessing || !selectedCount}
          onClick={onApprove}
        >
          {isProcessing
            ? approvePending
              ? "Dispatching..."
              : "Creating preview..."
            : "Approve cleanup"}
        </button>
        <button
          className="btn btn-secondary"
          disabled={isProcessing}
          onClick={onClear}
        >
          Clear selection
        </button>
        {error && (
          <span className="text-body-sm text-safety-amber">
            {error.message ?? "Action failed"}
          </span>
        )}
      </div>
      <p className="text-body-xs text-neutral-grey-60">
        <span className="text-safety-amber">Reminder:</span> Approval sends
                        this batch to the backend as a Trash-moving plan. You can cancel any
        plan before its worker dispatches it. The browser never touches Gmail
        directly.
      </p>
    </div>
  );
}

function RecommendationRow({
  item,
  selected,
  onSelect,
}: {
  item: RecommendationListItem;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <article
      className={cn(
        "panel group p-4 cursor-pointer transition-colors",
        selected && "ring-1 ring-data-blue"
      )}
      onClick={() => onSelect(item.id)}
    >
      <div className="flex items-start gap-4">
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onSelect(item.id)}
          className="mt-0.5 h-4 w-4 cursor-pointer rounded border-panel-border bg-neutral-grey-40/20"
          aria-label={`Select ${item.subject ?? "(no subject)"}`}
          onClick={(e) => e.stopPropagation()}
        />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <p className="text-body-md text-neutral-white">
                {item.subject ?? "(no subject)"}
              </p>
              {item.sender_domain && (
                <p className="data-label">{item.sender_domain}</p>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <RiskPill level={item.risk} />
              <span className="font-mono text-body-md text-data-blue">
                {formatPercent(item.confidence)}
              </span>
            </div>
          </div>
          {item.reasons && item.reasons.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {item.reasons.slice(0, 3).map((r, i) => (
                <span key={i} className="chip chip-sm" title={r}>
                  {r}
                </span>
              ))}
            </div>
          )}
          <div className="flex items-center gap-4">
            <span
              className={cn(
                "chip",
                item.action === "MOVE_TO_TRASH" && "chip-amber",
                item.action === "REVIEW" && "chip-violet",
                item.action === "KEEP" && "chip-blue"
              )}
            >
              {humanize(item.action)}
            </span>
            {item.category && (
              <span className="chip">{humanize(item.category)}</span>
            )}
            {item.is_starred && <span className="chip chip-amber">Starred</span>}
            {item.has_attachments && <span className="chip">Attachments</span>}
          </div>
          <p className="data-label">
            confidence {formatPercent(item.confidence)} · {humanize(item.action)}
          </p>
        </div>
      </div>
    </article>
  );
}

function RiskPill({ level }: { level: RiskLevel }) {
  return (
    <span
      className={cn(
        "chip",
        level === "LOW" && "chip-blue",
        level === "MEDIUM" && "chip-violet",
        level === "HIGH" && "chip-amber"
      )}
    >
      {riskLabel(level)}
    </span>
    );
}


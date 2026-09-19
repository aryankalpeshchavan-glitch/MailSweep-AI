import { useQuery } from "@tanstack/react-query";
import {
  getActiveAnalysis,
  getAnalysisJob,
  getAuthStatus,
  getGroup,
  getMailboxSummary,
  getPlan,
  getRecommendation,
  listAudit,
  listGroups,
  listPlans,
  listRecommendations,
  listRules,
  type RecommendationListParams,
  type GroupListParams,
} from "./endpoints";

/** TanStack Query hook definitions — one stable key + fetcher per resource. */

export const authKeys = { all: ["auth"] as const };
export function useAuthStatus() {
  return useQuery({ queryKey: authKeys.all, queryFn: getAuthStatus });
}

export const summaryKeys = { all: ["mailbox", "summary"] as const };
export function useMailboxSummary() {
  return useQuery({ queryKey: summaryKeys.all, queryFn: getMailboxSummary });
}

export const recKeys = {
  list: (p: RecommendationListParams) => ["recommendations", "list", p] as const,
  detail: (id: string) => ["recommendations", "detail", id] as const,
};
export function useRecommendations(params: RecommendationListParams) {
  return useQuery({
    queryKey: recKeys.list(params),
    queryFn: () => listRecommendations(params),
    placeholderData: (prev) => prev,
  });
}
export function useRecommendation(id: string) {
  return useQuery({
    queryKey: recKeys.detail(id),
    queryFn: () => getRecommendation(id),
    enabled: Boolean(id),
  });
}

export const groupKeys = { all: (p: GroupListParams) => ["groups", "list", p] as const };
export function useGroups(params: GroupListParams) {
  return useQuery({
    queryKey: groupKeys.all(params),
    queryFn: () => listGroups(params),
    placeholderData: (prev) => prev,
  });
}
export function useGroup(id: string) {
  return useQuery({
    queryKey: ["groups", "detail", id] as const,
    queryFn: () => getGroup(id),
    enabled: Boolean(id),
  });
}

export const planKeys = { all: ["plans"] as const, detail: (id: string) => ["plans", id] as const };
export function usePlans(status?: string) {
  return useQuery({ queryKey: ["plans", status ?? "all"] as const, queryFn: () => listPlans(status) });
}
export function usePlan(id: string) {
  return useQuery({ queryKey: planKeys.detail(id), queryFn: () => getPlan(id), enabled: Boolean(id) });
}

export const ruleKeys = { all: ["rules"] as const };
export function useRules() {
  return useQuery({ queryKey: ruleKeys.all, queryFn: listRules });
}

export function useAudit(page = 1, pageSize = 50, eventType?: string) {
  return useQuery({
    queryKey: ["audit", page, pageSize, eventType ?? "all"] as const,
    queryFn: () => listAudit({ page, page_size: pageSize, event_type: eventType }),
  });
}

export function useAnalysisJobPoll(jobId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: analysisKeys.job(jobId),
    queryFn: () => getAnalysisJob(jobId as string),
    enabled: Boolean(jobId) && enabled,
    refetchInterval: (query) => jobPollInterval(query.state.data?.status),
  });
}

/**
 * Poll cadence for an analysis job. Terminal statuses stop polling; every
 * non-terminal status (QUEUED, RUNNING, CLASSIFYING, GROUPING,
 * BUILDING_RECOMMENDATIONS) keeps polling so progress keeps updating.
 */
export function jobPollInterval(status: string | undefined): number | false {
  if (status === "COMPLETED" || status === "FAILED" || status === "CANCELLED") {
    return false;
  }
  return 2000;
}

/** Keys for backend-derived analysis state (source of truth). */
export const analysisKeys = {
  active: ["analysis", "active"] as const,
  job: (id: string | null) => ["analysis", "job", id] as const,
};

/** Latest non-terminal analysis job for the signed-in user (or none). */
export function useActiveAnalysis() {
  return useQuery({
    queryKey: analysisKeys.active,
    queryFn: getActiveAnalysis,
  });
}
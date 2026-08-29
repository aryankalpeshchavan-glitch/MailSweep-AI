import { API_BASE, apiFetch, qs } from "@/lib/apiClient";
import type {
  AnalysisJob,
  AnalysisStartResponse,
  ApprovePlanResponse,
  AuditListResponse,
  AuthStatus,
  CleanupPlan,
  GroupDetail,
  GroupListResponse,
  HealthStatus,
  MailboxSummary,
  PlanPreviewRequest,
  RecommendationDetail,
  RecommendationListResponse,
  Rule,
  RuleCreateRequest,
  RuleUpdateRequest,
} from "@/types/api";

/**
 * Typed, endpoint-aligned API layer.
 * Every function mirrors one backend route. Components consume these via
 * TanStack Query hooks (src/api/queries.ts). Destructive Gmail actions only
 * ever happen through these backend endpoints — never from the browser.
 */

// ---------------------------------------------------------------- system
export const getHealth = () => apiFetch<HealthStatus>("/api/health");

// ---------------------------------------------------------------- auth
export const getAuthStatus = () => apiFetch<AuthStatus>("/api/auth/status");
export const postLogout = () => apiFetch<void>("/api/auth/logout", { method: "POST" });
export const postGoogleDisconnect = () =>
  apiFetch<void>("/api/auth/google/disconnect", { method: "POST" });

/**
 * Full-page navigation to start Google OAuth. Not a fetch — the browser
 * follows a redirect that eventually lands back on the frontend.
 */
export const buildGoogleLoginUrl = (redirectTo = "/") =>
  `${API_BASE}/api/auth/google/login?redirect_to=${encodeURIComponent(redirectTo)}`;

// ---------------------------------------------------------------- analysis
export const startAnalysis = () =>
  apiFetch<AnalysisStartResponse>("/api/analysis/start", { method: "POST" });

export const getAnalysisJob = (jobId: string) =>
  apiFetch<AnalysisJob>(`/api/analysis/jobs/${jobId}`);

// ---------------------------------------------------------------- mailbox
export const getMailboxSummary = () => apiFetch<MailboxSummary>("/api/mailbox/summary");

// ---------------------------------------------------------------- recommendations
export interface RecommendationListParams {
  action?: string;
  risk?: string;
  category?: string;
  page?: number;
  page_size?: number;
}
export const listRecommendations = (params: RecommendationListParams) =>
  apiFetch<RecommendationListResponse>(
    `/api/recommendations${qs({ ...params })}`
  );

export const getRecommendation = (recId: string) =>
  apiFetch<RecommendationDetail>(`/api/recommendations/${recId}`);

// ---------------------------------------------------------------- groups
export interface GroupListParams {
  page?: number;
  page_size?: number;
  category?: string;
}
export const listGroups = (params: GroupListParams) =>
  apiFetch<GroupListResponse>(`/api/groups${qs({ ...params })}`);
export const getGroup = (groupId: string) => apiFetch<GroupDetail>(`/api/groups/${groupId}`);

// ---------------------------------------------------------------- cleanup
export const createPlanPreview = (payload: PlanPreviewRequest) =>
  apiFetch<CleanupPlan>("/api/cleanup/preview", { method: "POST", body: payload });
export const listPlans = (status?: string) =>
  apiFetch<CleanupPlan[]>(`/api/cleanup/plans${qs({ status })}`);
export const getPlan = (planId: string) =>
  apiFetch<CleanupPlan>(`/api/cleanup/plans/${planId}`);
export const approvePlan = (planId: string) =>
  apiFetch<ApprovePlanResponse>(`/api/cleanup/plans/${planId}/approve`, { method: "POST" });
export const cancelPlan = (planId: string) =>
  apiFetch<{ id: string; status: string }>(`/api/cleanup/plans/${planId}/cancel`, {
    method: "POST",
  });

// ---------------------------------------------------------------- rules
export const listRules = () => apiFetch<Rule[]>("/api/rules");
export const createRule = (payload: RuleCreateRequest) =>
  apiFetch<Rule>("/api/rules", { method: "POST", body: payload });
export const updateRule = (ruleId: string, payload: RuleUpdateRequest) =>
  apiFetch<Rule>(`/api/rules/${ruleId}`, { method: "PUT", body: payload });
export const deleteRule = (ruleId: string) =>
  apiFetch<void>(`/api/rules/${ruleId}`, { method: "DELETE" });

// ---------------------------------------------------------------- audit
export const listAudit = (params: { event_type?: string; page?: number; page_size?: number }) =>
  apiFetch<AuditListResponse>(`/api/audit${qs({ ...params })}`);
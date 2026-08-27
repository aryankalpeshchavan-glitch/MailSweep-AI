// ===========================================================================
// Typed API contract — mirrors backend Pydantic/response payloads exactly.
// Source of truth: backend/app/api/routes/*.py
// ===========================================================================

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
  request_id: string | null;
}

// ------------------------------------------------------------------- auth

export interface User {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
}

export interface GmailConnection {
  connected: boolean;
  email: string | null;
  status: string | null;
  connected_at: string | null;
  granted_scopes: string[];
}

export interface AuthStatus {
  authenticated: boolean;
  user?: User;
  gmail_connection?: GmailConnection;
}

// ------------------------------------------------------------------- health
export interface HealthComponent {
  status: string;
  driver?: string;
}
export interface HealthStatus {
  status: string;
  environment: string;
  components: Record<string, HealthComponent>;
}

// ------------------------------------------------------------------- analysis
export interface AnalysisStartResponse {
  job_id: string;
  status: string;
  dispatched_to: string;
  poll: string;
}

export interface AnalysisJob {
  job_id: string;
  status: string;
  messages_total: number | null;
  messages_processed: number | null;
  progress_percent: number | null;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

// ------------------------------------------------------------------- mailbox
export interface MailboxSummary {
  gmail_connection: { connected: boolean; email: string | null };
  analyzed: boolean;
  mailbox?: {
    email_address: string;
    total_messages_cached: number;
    last_analysis_at: string | null;
  };
  recommendations?: {
    move_to_trash: number;
    review: number;
    keep: number;
    trash_by_risk: { low: number; medium: number; high: number };
  };
  top_groups?: Array<{
    id: string;
    display_name: string;
    message_count: number;
    category: string | null;
  }>;
}
// ------------------------------------------------------------------- recommendations
export type RecommendationAction = "MOVE_TO_TRASH" | "REVIEW" | "KEEP";
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export interface RecommendationListItem {
  id: string;
  gmail_message_id: string;
  subject: string | null;
  sender_domain: string | null;
  received_at: string | null;
  action: RecommendationAction;
  confidence: number | null;
  risk: RiskLevel;
  reasons: string[] | null;
  category: string | null;
  is_starred: boolean;
  has_attachments: boolean;
}

export interface RecommendationListResponse {
  items: RecommendationListItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface RecommendationDetail {
  id: string;
  action: RecommendationAction;
  confidence: number | null;
  risk: RiskLevel;
  reasons: string[] | null;
  contributing_rule_ids: string[] | null;
  status: string;
  message: {
    gmail_message_id: string;
    subject: string | null;
    sender_name: string | null;
    sender_email: string | null;
    received_at: string | null;
    has_attachments: boolean;
  };
  classification: {
    category: string | null;
    source: string | null;
    ai_reasoning: string | null;
  };
}

// ------------------------------------------------------------------- groups
export interface EmailGroup {
  id: string;
  display_name: string;
  primary_sender_domain: string | null;
  category: string | null;
  message_count: number;
  first_message_at: string | null;
  last_message_at: string | null;
  sample_subjects: string[] | null;
}
export interface GroupListResponse {
  items: EmailGroup[];
  page: number;
  page_size: number;
  total: number;
}
export interface GroupMessage {
  id: string;
  subject: string | null;
  sender_email: string | null;
  received_at: string | null;
  is_starred: boolean;
  recommendation_action: string | null;
  recommendation_confidence: number | null;
  risk: string | null;
}
export interface GroupDetail {
  id: string;
  display_name: string;
  primary_sender_domain: string | null;
  category: string | null;
  message_count: number;
  messages: GroupMessage[];
}

// ------------------------------------------------------------------- cleanup
export type PlanStatus =
  | "PREVIEW"
  | "APPROVED"
  | "EXECUTING"
  | "COMPLETED"
  | "CANCELED"
  | "FAILED";

export interface CleanupPlanItem {
  message_id: string;
  gmail_message_id: string;
  subject_snapshot: string | null;
  sender_snapshot: string | null;
  item_status: string;
  failure_reason: string | null;
}

export interface CleanupPlan {
  id: string;
  status: PlanStatus;
  message_count: number;
  created_at: string | null;
  approved_at: string | null;
  completed_at: string | null;
  failure_summary: Record<string, unknown> | null;
  items?: CleanupPlanItem[];
}

export interface PlanPreviewRequest {
  recommendation_ids: string[];
  idempotency_key?: string;
}

export interface ApprovePlanResponse {
  id: string;
  status: string;
  dispatched_to: string;
  message_count: number;
}

// ------------------------------------------------------------------- rules
export type RuleKind = "PROTECT" | "CLEANUP";
export interface RuleCondition {
  field: string;
  op: string;
  value: string | number | boolean;
}
export interface Rule {
  id: string;
  name: string;
  kind: RuleKind;
  match_all: boolean;
  conditions: RuleCondition[];
  priority: number;
  enabled: boolean;
}
export interface RuleCreateRequest {
  name: string;
  kind: RuleKind;
  match_all: boolean;
  conditions: RuleCondition[];
  priority?: number;
}
export interface RuleUpdateRequest {
  name?: string;
  match_all?: boolean;
  conditions?: RuleCondition[];
  priority?: number;
  enabled?: boolean;
}

// ------------------------------------------------------------------- audit
export interface AuditEventItem {
  id: string;
  event_type: string;
  object_type: string | null;
  object_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}
export interface AuditListResponse {
  items: AuditEventItem[];
  page: number;
  page_size: number;
  total: number;
}
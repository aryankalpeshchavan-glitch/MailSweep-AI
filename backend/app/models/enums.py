"""Shared domain enums.

Storage strategy: DB columns are plain ``String`` and these are ``StrEnum``
subclasses, so instances compare equal to their stored string values
(``"PROMOTIONAL" == EmailCategory.PROMOTIONAL``). This keeps schemas portable
across SQLite (tests) and PostgreSQL (production) without native ENUM churn
in migrations.

Integrity is enforced at the boundary: every write path goes through Pydantic
schemas that validate against these enums, so invalid values cannot reach the
ORM from the API. (If a future audit requires DB-level CHECKs, switch columns
to ``sa.Enum(..., native_enum=False)`` - a mechanical change.)
"""

from __future__ import annotations

from enum import StrEnum


class OAuthStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    ERROR = "ERROR"


class EmailCategory(StrEnum):
    PROMOTIONAL = "PROMOTIONAL"
    NEWSLETTER = "NEWSLETTER"
    AUTOMATED_NOTIFICATION = "AUTOMATED_NOTIFICATION"
    SOCIAL_NOTIFICATION = "SOCIAL_NOTIFICATION"
    RECEIPT = "RECEIPT"
    INVOICE = "INVOICE"
    PERSONAL = "PERSONAL"
    PROFESSIONAL = "PROFESSIONAL"
    IMPORTANT = "IMPORTANT"
    OLD = "OLD"
    REDUNDANT = "REDUNDANT"
    UNCERTAIN = "UNCERTAIN"

    @classmethod
    def cleanup_candidates(cls) -> tuple[EmailCategory, ...]:
        """Categories eligible for trash recommendations when other signals agree."""
        return (
            cls.PROMOTIONAL,
            cls.NEWSLETTER,
            cls.AUTOMATED_NOTIFICATION,
            cls.SOCIAL_NOTIFICATION,
        )


class RecommendationAction(StrEnum):
    KEEP = "KEEP"
    MOVE_TO_TRASH = "MOVE_TO_TRASH"
    REVIEW = "REVIEW"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ClassificationSource(StrEnum):
    RULE = "RULE"
    AI = "AI"
    USER = "USER"


class AnalysisJobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CLASSIFYING = "CLASSIFYING"
    GROUPING = "GROUPING"
    BUILDING_RECOMMENDATIONS = "BUILDING_RECOMMENDATIONS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @classmethod
    def terminal(cls) -> frozenset[AnalysisJobStatus]:
        return frozenset({cls.COMPLETED, cls.FAILED, cls.CANCELLED})

    @classmethod
    def active_statuses(cls) -> list[str]:
        """Non-terminal statuses - at most one job per mailbox may hold any."""
        return [s.value for s in cls if s not in cls.terminal()]


class CleanupPlanStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_FAILURES = "COMPLETED_WITH_FAILURES"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CleanupPlanItemStatus(StrEnum):
    PENDING = "PENDING"
    TRASHED = "TRASHED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class UserDecisionChoice(StrEnum):
    KEEP = "KEEP"
    MOVE_TO_TRASH = "MOVE_TO_TRASH"


class RuleKind(StrEnum):
    PROTECT = "PROTECT"
    CLEANUP = "CLEANUP"


class AuditEvent(StrEnum):
    ACCOUNT_CONNECTED = "ACCOUNT_CONNECTED"
    ACCOUNT_DISCONNECTED = "ACCOUNT_DISCONNECTED"
    ANALYSIS_STARTED = "ANALYSIS_STARTED"
    ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    RECOMMENDATIONS_GENERATED = "RECOMMENDATIONS_GENERATED"
    CLEANUP_PREVIEW_CREATED = "CLEANUP_PREVIEW_CREATED"
    CLEANUP_APPROVED = "CLEANUP_APPROVED"
    CLEANUP_EXECUTION_STARTED = "CLEANUP_EXECUTION_STARTED"
    CLEANUP_COMPLETED = "CLEANUP_COMPLETED"
    CLEANUP_FAILED = "CLEANUP_FAILED"
    CLEANUP_CANCELLED = "CLEANUP_CANCELLED"
    RULE_CREATED = "RULE_CREATED"
    RULE_UPDATED = "RULE_UPDATED"
    RULE_DELETED = "RULE_DELETED"
    DATA_DELETE_REQUESTED = "DATA_DELETE_REQUESTED"

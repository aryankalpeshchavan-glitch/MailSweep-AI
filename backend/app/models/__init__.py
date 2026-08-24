"""All ORM models. Importing this package registers every mapper."""

from app.models.analysis import AnalysisJob, Classification, Recommendation
from app.models.audit import AuditLog
from app.models.cleanup import CleanupPlan, CleanupPlanItem
from app.models.mailbox import EmailGroup, EmailMessage, Mailbox
from app.models.rules import CleanupRule, UserDecision
from app.models.user import OAuthConnection, User, UserSession

__all__ = [
    "AnalysisJob",
    "AuditLog",
    "Classification",
    "CleanupPlan",
    "CleanupPlanItem",
    "CleanupRule",
    "EmailGroup",
    "EmailMessage",
    "Mailbox",
    "OAuthConnection",
    "Recommendation",
    "User",
    "UserDecision",
    "UserSession",
]

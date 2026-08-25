"""Explainable recommendation engine.

Confidence (how sure) and risk (damage if wrong) are computed separately.
Decision ladder, first match wins:

1. Protection rule matched              -> KEEP
2. Starred / Gmail-important flag       -> KEEP
3. Receipt/invoice category             -> KEEP
4. Cleanup category + old enough
   + confidence >= CONFIDENCE_FLOOR     -> MOVE_TO_TRASH
5. Uncertain or below floor             -> REVIEW
6. Otherwise                            -> KEEP

Age alone never triggers step 4 - category eligibility is structural.
Cleanup rules add +0.10 confidence and are cited; they cannot override 1-3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.gmail.models import age_in_days
from app.models.enums import EmailCategory, RecommendationAction, RiskLevel

#: Below this, uncertainty resolves to REVIEW rather than action.
CONFIDENCE_FLOOR = 0.60

BONUS_CLEANUP_RULE_MATCH = 0.10
BONUS_LIST_UNSUBSCRIBE = 0.05
BONUS_AGE_BEYOND_RETENTION = 0.05

_DAYS_PER_YEAR = 365.25

_CLEANUP_CATEGORIES = {c.value for c in EmailCategory.cleanup_candidates()}


@dataclass(slots=True)
class RecommendationOutcome:
    action: str
    confidence: float
    risk: str
    reasons: list[dict] = field(default_factory=list)
    contributing_rule_ids: list[str] = field(default_factory=list)

    def reason(self, code: str, detail: str) -> None:
        self.reasons.append({"code": code, "detail": detail})


def recommend(
    *,
    classification_category: str | None,
    classification_confidence: float | None,
    classification_risk: str | None,
    received_at: datetime | None,
    is_starred: bool,
    is_important: bool,
    has_attachments: bool,
    retention_years: int,
    protected_by_rule_id: str | None = None,
    protected_by_rule_name: str | None = None,
    matched_cleanup_rule_ids: list[str] | None = None,
    now: datetime | None = None,
) -> RecommendationOutcome:
    """Pure decision function - deterministic, no I/O, fully unit-testable."""
    current = now or datetime.now(UTC)
    age_days = age_in_days(received_at, now=current)
    rule_ids = list(matched_cleanup_rule_ids or [])

    outcome = RecommendationOutcome(
        action=RecommendationAction.KEEP.value,
        confidence=round(classification_confidence or 0.0, 2),
        risk=classification_risk or RiskLevel.MEDIUM.value,
        contributing_rule_ids=rule_ids,
    )

    # -- protective ladder --------------------------------------------------
    if protected_by_rule_id:
        outcome.reason("protection_rule", f"Protected by your rule '{protected_by_rule_name}'.")
        return _finalize(outcome)
    if is_starred:
        outcome.reason("starred", "You starred this message.")
        return _finalize(outcome)
    if is_important:
        outcome.reason("gmail_important", "Gmail marks this message as important.")
        return _finalize(outcome)
    if classification_category in (EmailCategory.RECEIPT.value, EmailCategory.INVOICE.value):
        outcome.reason("financial_document", "Looks like a receipt/invoice - kept by default.")
        return _finalize(outcome)

    # -- cleanup candidacy ---------------------------------------------------
    category_is_cleanable = classification_category in _CLEANUP_CATEGORIES
    retention_days = retention_years * _DAYS_PER_YEAR
    old_enough = age_days is not None and age_days >= retention_days

    if category_is_cleanable and old_enough:
        return _cleanup_branch(
            outcome, age_days, retention_days, retention_years,
            has_attachments, classification_category, classification_confidence,
            bool(rule_ids),
        )

    if classification_category == EmailCategory.UNCERTAIN.value or (
        classification_confidence is not None and classification_confidence < CONFIDENCE_FLOOR
    ):
        outcome.action = RecommendationAction.REVIEW.value
        outcome.reason("uncertain_classification", "Classifier could not resolve this confidently.")
        return _finalize(outcome)

    if category_is_cleanable and not old_enough:
        outcome.reason(
            "within_retention_window", f"Newer than your {retention_years}-year retention window."
        )
    outcome.reason("no_cleanup_signals", "No cleanup signals met their thresholds.")
    return _finalize(outcome)


def _cleanup_branch(
    outcome: RecommendationOutcome,
    age_days: float,
    retention_days: float,
    retention_years: int,
    has_attachments: bool,
    category: str | None,
    classifier_confidence: float | None,
    had_rule_match: bool,
) -> RecommendationOutcome:
    confidence = float(outcome.confidence)
    if had_rule_match:
        confidence += BONUS_CLEANUP_RULE_MATCH
        outcome.reason("cleanup_rule_match", "Matches one of your cleanup rules.")
    if age_days >= retention_days * 2:
        confidence += BONUS_AGE_BEYOND_RETENTION
        outcome.reason(
            "age_far_beyond_retention",
            f"Age {int(age_days)} days far exceeds your {retention_years}-year window.",
        )
    outcome.reason(
        "age_exceeds_retention",
        f"Received {int(age_days)} days ago (>= your {retention_years}-year setting).",
    )
    outcome.reason(
        "category_cleanable",
        f"{category} mail is eligible for cleanup when other signals agree.",
    )

    if confidence < CONFIDENCE_FLOOR:
        outcome.action = RecommendationAction.REVIEW.value
        outcome.confidence = round(confidence, 2)
        outcome.reason(
            "low_confidence_review",
            f"Confidence {confidence:.2f} below the {CONFIDENCE_FLOOR:.2f} action floor.",
        )
        return _finalize(outcome)

    outcome.action = RecommendationAction.MOVE_TO_TRASH.value
    outcome.risk = _trash_risk(has_attachments, category)
    outcome.confidence = round(min(confidence, 0.99), 2)
    return _finalize(outcome)


def _trash_risk(has_attachments: bool, category: str | None) -> str:
    base = {
        EmailCategory.PROMOTIONAL.value: RiskLevel.LOW.value,
        EmailCategory.NEWSLETTER.value: RiskLevel.LOW.value,
        EmailCategory.SOCIAL_NOTIFICATION.value: RiskLevel.LOW.value,
        EmailCategory.AUTOMATED_NOTIFICATION.value: RiskLevel.MEDIUM.value,
    }.get(category or "", RiskLevel.MEDIUM.value)
    if has_attachments and base == RiskLevel.LOW.value:
        return RiskLevel.MEDIUM.value
    return base


def _finalize(outcome: RecommendationOutcome) -> RecommendationOutcome:
    outcome.confidence = round(max(0.0, min(outcome.confidence, 0.99)), 2)
    return outcome

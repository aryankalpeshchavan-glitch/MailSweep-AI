"""Engine tests: the spec-mandated safety matrix lives here (spec §30).

  5-year-old promotional   -> MOVE_TO_TRASH candidate
  5-year-old receipt       -> KEEP
  starred message          -> KEEP
  protected domain rule    -> KEEP
  low-confidence           -> REVIEW
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.classifier.deterministic import classify
from app.gmail.models import GmailMessageMeta
from app.models.enums import EmailCategory
from app.recommendations.engine import (
    BONUS_CLEANUP_RULE_MATCH,
    CONFIDENCE_FLOOR,
    recommend,
)

_NOW = datetime(2026, 8, 25, tzinfo=UTC)


def _meta(**overrides) -> GmailMessageMeta:
    values = dict(
        gmail_id="gm-1",
        sender_email="news@bulkmail.example",
        sender_domain="bulkmail.example",
        subject="Weekly digest",
        received_at=_NOW - timedelta(days=6 * 365),
        label_ids=[],
        has_list_unsubscribe=True,
    )
    values.update(overrides)
    return GmailMessageMeta(**values)


def _recommend_for(meta: GmailMessageMeta, **kwargs):
    classification = classify(meta)
    outcome = recommend(
        classification_category=classification.category,
        classification_confidence=classification.confidence,
        classification_risk=classification.risk,
        received_at=meta.received_at,
        is_starred=meta.is_starred,
        is_important=meta.is_important,
        has_attachments=meta.has_attachments,
        retention_years=kwargs.pop("retention_years", 5),
        now=kwargs.pop("now", _NOW),
        **kwargs,
    )
    return outcome, classification


def test_gmail_promotions_label_drives_classification():
    result = classify(_meta(label_ids=["INBOX", "CATEGORY_PROMOTIONS"]))
    assert result.category == EmailCategory.PROMOTIONAL.value
    assert result.confidence >= 0.9
    assert any(r["code"] == "gmail_tab_category" for r in result.reasons)


def test_newsletter_subject_without_labels():
    result = classify(_meta(subject="Your weekly newsletter from Acme"))
    assert result.category == EmailCategory.NEWSLETTER.value


def test_personal_fallback_for_personal_category():
    result = classify(
        _meta(
            subject="Lunch tomorrow?", sender_email="friend@example.com",
            sender_domain="example.com", has_list_unsubscribe=False,
            label_ids=["CATEGORY_PERSONAL"],
        )
    )
    assert result.category == EmailCategory.PERSONAL.value


def test_financial_terms_produce_high_risk():
    result = classify(_meta(label_ids=[], subject="Your order confirmation and receipt"))
    assert result.risk == "HIGH"


# ---------------------------------------------------------------------------
# recommendation safety matrix


def test_old_promotional_mail_is_cleanup_candidate():
    outcome, _cls = _recommend_for(_meta(label_ids=["CATEGORY_PROMOTIONS"]))
    assert outcome.action == "MOVE_TO_TRASH"
    assert outcome.risk == "LOW"
    assert outcome.confidence >= CONFIDENCE_FLOOR
    assert any(r["code"] == "age_exceeds_retention" for r in outcome.reasons)


def test_old_receipt_is_kept():
    meta = _meta(
        subject="Your order confirmation & receipt",
        sender_email="orders@shop.example", sender_domain="shop.example",
        has_list_unsubscribe=False, label_ids=[],
    )
    outcome, _cls = _recommend_for(meta)
    assert outcome.action == "KEEP"
    assert outcome.risk == "HIGH"


def test_starred_message_is_always_kept():
    outcome, _ = _recommend_for(_meta(label_ids=["CATEGORY_PROMOTIONS"], is_starred=True))
    assert outcome.action == "KEEP"
    assert any(r["code"] == "starred" for r in outcome.reasons)


def test_important_flag_is_always_kept():
    outcome, _ = _recommend_for(_meta(label_ids=["CATEGORY_PROMOTIONS"], is_important=True))
    assert outcome.action == "KEEP"


def test_protected_rule_beats_cleanup_signals():
    outcome, _ = _recommend_for(
        _meta(),
        protected_by_rule_id="rule-1",
        protected_by_rule_name="Keep university mail",
    )
    assert outcome.action == "KEEP"
    assert any(r["code"] == "protection_rule" for r in outcome.reasons)


def test_young_bulk_mail_stays_within_retention_window():
    meta = _meta(label_ids=["CATEGORY_PROMOTIONS"], received_at=_NOW - timedelta(days=30))
    outcome, _cls = _recommend_for(meta)
    assert outcome.action == "KEEP"
    assert any(r["code"] == "within_retention_window" for r in outcome.reasons)


def test_low_confidence_resolves_to_review_not_deletion():
    meta = _meta(
        subject="Quick question", sender_email="a@b.example", sender_domain="b.example",
        has_list_unsubscribe=False, label_ids=[],
        received_at=_NOW - timedelta(days=7 * 365),
    )
    outcome, cls = _recommend_for(meta)
    assert outcome.action == "REVIEW"
    assert any(
        r["code"] in {"low_confidence_review", "uncertain_classification"}
        for r in outcome.reasons
    )


def test_uncertain_category_resolves_to_review():
    meta = _meta(subject=None, label_ids=[], has_list_unsubscribe=False,
                 sender_email="x@y.example", sender_domain="y.example")
    outcome, cls = _recommend_for(meta)
    assert cls.category == EmailCategory.UNCERTAIN.value
    assert outcome.action == "REVIEW"


def test_cleanup_rule_bonus_lifts_confidence_and_is_cited():
    meta = _meta(label_ids=[], subject="Special deals inside")  # promotional via subject
    no_rule, _ = _recommend_for(meta)
    with_rule, _ = _recommend_for(meta, matched_cleanup_rule_ids=["r-42"])

    assert with_rule.confidence >= no_rule.confidence
    assert BONUS_CLEANUP_RULE_MATCH == 0.10
    assert "r-42" in with_rule.contributing_rule_ids
    assert any(r["code"] == "cleanup_rule_match" for r in with_rule.reasons)


def test_attachments_raise_trash_risk_to_medium():
    meta = _meta(label_ids=["CATEGORY_SOCIAL"], has_attachments=True)
    outcome, _ = _recommend_for(meta)
    assert outcome.action == "MOVE_TO_TRASH"
    assert outcome.risk == "MEDIUM"  # LOW raised because of attachments


def test_recommendation_is_deterministic():
    a, _ = _recommend_for(_meta())
    b, _ = _recommend_for(_meta())
    assert (a.action, a.confidence, a.risk) == (b.action, b.confidence, b.risk)
    assert a.reasons == b.reasons

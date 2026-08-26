"""Mailbox analysis pipeline: ingest -> classify -> group -> recommend.

Framework-agnostic: receives an open DB session plus a Gmail client, updates
AnalysisJob status/progress as it goes, so execution is identical under
Celery or inline (ADR-0005). Transient Gmail errors are retried inside the
client; anything reaching here marks the job FAILED with a short secret-free
message + audit event. Cancellation is honored between stages.
"""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import Session

from app.auth.service import record_event
from app.classifier.deterministic import CLASSIFIER_VERSION, classify
from app.core.config import Settings
from app.db.base import utcnow
from app.gmail.client import GmailClientProtocol
from app.models import (
    AnalysisJob,
    Classification,
    CleanupRule,
    EmailGroup,
    EmailMessage,
    Mailbox,
    Recommendation,
)
from app.models.enums import AnalysisJobStatus, AuditEvent

logger = logging.getLogger(__name__)

_BATCH_SIZE = 200


def run_mailbox_analysis(
    db: Session,
    *,
    job_id: str,
    gmail: GmailClientProtocol,
    settings: Settings,
    ai_classifier=None,
) -> None:
    job_pk = uuid.UUID(str(job_id))
    job = db.get(AnalysisJob, job_pk)
    if job is None:
        raise ValueError(f"AnalysisJob {job_id} not found")
    mailbox = db.get(Mailbox, job.mailbox_id)
    user_id_for_audit = job.user_id

    try:
        _transition(db, job, None, AnalysisJobStatus.RUNNING)
        job.started_at = utcnow()
        db.commit()

        message_ids = gmail.list_message_ids(
            page_size=settings.GMAIL_PAGE_SIZE,
            max_total=settings.MAX_MESSAGES_PER_ANALYSIS,
        )
        job.messages_total = len(message_ids)
        db.commit()

        metas = _fetch_metadata(gmail, message_ids, job, db)
        if _is_cancelled(db, job_pk):
            return

        _transition(db, job, AnalysisJobStatus.RUNNING, AnalysisJobStatus.CLASSIFYING)
        stored = _upsert_messages_and_classifications(
            db, mailbox.id, metas, ai_classifier,
            ai_budget=getattr(settings, "AI_MAX_MESSAGES_PER_JOB", 0),
        )
        if _is_cancelled(db, job_pk):
            return

        _transition(db, job, AnalysisJobStatus.CLASSIFYING, AnalysisJobStatus.GROUPING)
        _regroup(db, mailbox.id, stored.values())
        if _is_cancelled(db, job_pk):
            return

        _transition(
            db, job, AnalysisJobStatus.GROUPING, AnalysisJobStatus.BUILDING_RECOMMENDATIONS
        )
        counts = _recommend_all(db, mailbox, list(stored.values()), settings)

        mailbox.last_analysis_at = utcnow()
        mailbox.total_messages_cached = len(stored)
        _transition(
            db, job, AnalysisJobStatus.BUILDING_RECOMMENDATIONS, AnalysisJobStatus.COMPLETED
        )
        job.completed_at = utcnow()
        db.commit()
        record_event(
            db, event_type=AuditEvent.ANALYSIS_COMPLETED, user_id=job.user_id,
            object_type="mailbox", object_id=str(mailbox.id),
            detail={"messages": len(stored)},
        )
        record_event(
            db, event_type=AuditEvent.RECOMMENDATIONS_GENERATED, user_id=job.user_id,
            object_type="mailbox", object_id=str(mailbox.id), detail=counts,
        )
        logger.info(
            "mailbox analysis completed",
            extra={"event": "analysis_completed", "job_id": str(job.id),
                   "messages_processed": len(stored)},
        )
    except Exception as exc:  # noqa: BLE001 - converted into job failure state
        # Contract: record FAILED (+ reason, finished stamp, audit), then
        # re-raise so Celery/ops layers observe the task failure. The inline
        # dispatcher catches this; nothing crashes the host process.
        db.rollback()
        fresh = db.get(AnalysisJob, job_pk)
        if fresh is not None and fresh.status != AnalysisJobStatus.CANCELLED.value:
            fresh.status = AnalysisJobStatus.FAILED.value
            fresh.error_code = type(exc).__name__  # safe identifier, no payload
            fresh.error_message = str(exc)[:500]
            fresh.completed_at = utcnow()
            db.commit()
        record_event(
            db,
            event_type=AuditEvent.ANALYSIS_FAILED,
            user_id=user_id_for_audit,
            object_type="analysis_job",
            object_id=str(job_pk),
        )
        logger.exception(
            "analysis failed", extra={"event": "analysis_failed", "job_id": str(job_pk)}
        )
        raise


def _transition(db: Session, job: AnalysisJob, from_status, to_status: AnalysisJobStatus) -> None:
    if from_status is not None and job.status != getattr(from_status, "value", from_status):
        raise RuntimeError(f"Unexpected job status {job.status}, expected {from_status}")
    job.status = to_status.value
    db.commit()


def _is_cancelled(db: Session, job_pk) -> bool:
    status = db.query(AnalysisJob.status).filter_by(id=job_pk).scalar()
    if status == AnalysisJobStatus.CANCELLED.value:
        logger.info(
            "analysis cancelled", extra={"event": "analysis_cancelled", "job_id": str(job_pk)}
        )
        return True
    return False


def _fetch_metadata(gmail, message_ids, job, db) -> list:
    """Bounded-concurrency metadata fetch; individual failures are skipped."""
    metas: list = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(gmail.get_metadata, mid): mid for mid in message_ids}
        for index, future in enumerate(as_completed(futures), start=1):
            gmail_id = futures[future]
            try:
                metas.append(future.result())
            except Exception as exc:  # noqa: BLE001 - skip and continue
                logger.warning(
                    "metadata fetch failed",
                    extra={"event": "metadata_fetch_failed", "gmail_message_id": gmail_id,
                           "error_type": type(exc).__name__},
                )
            if index % _BATCH_SIZE == 0:
                job.messages_processed = index
                db.commit()
    job.messages_processed = len(message_ids)
    db.commit()
    return metas


def _upsert_messages_and_classifications(
    db, mailbox_id, metas, ai_classifier=None, ai_budget: int = 0
) -> dict:
    """Insert/update EmailMessage rows + their deterministic classifications."""
    gmail_ids = [m.gmail_id for m in metas]
    existing = {
        row.gmail_message_id: row
        for row in db.query(EmailMessage)
        .filter(
            EmailMessage.mailbox_id == mailbox_id,
            EmailMessage.gmail_message_id.in_(gmail_ids),
        )
        .all()
    }

    stored: dict[str, EmailMessage] = {}
    meta_by_id = {m.gmail_id: m for m in metas}
    for meta in metas:
        row = existing.get(meta.gmail_id)
        if row is None:
            row = EmailMessage(mailbox_id=mailbox_id, gmail_message_id=meta.gmail_id)
            db.add(row)
        row.gmail_thread_id = meta.thread_id
        row.sender_email = meta.sender_email
        row.sender_name = meta.sender_name
        row.sender_domain = meta.sender_domain
        row.subject = meta.subject
        row.received_at = meta.received_at
        row.size_estimate = meta.size_estimate
        row.has_attachments = meta.has_attachments
        row.attachment_count = meta.attachment_count
        row.is_starred = meta.is_starred
        row.is_important = meta.is_important
        row.has_list_unsubscribe = meta.has_list_unsubscribe
        row.label_ids = meta.label_ids
        stored[meta.gmail_id] = row

    db.flush()

    remaining_ai_calls = ai_budget
    for gmail_id, row in stored.items():
        meta = meta_by_id[gmail_id]
        result = classify(meta)
        category, confidence, ai_reasoning = result.category, result.confidence, None
        if ai_classifier is not None and remaining_ai_calls > 0:
            from app.ai.service import resolve_with_ai

            category, confidence, ai_reasoning = resolve_with_ai(
                ai_classifier, meta, category=result.category, confidence=result.confidence
            )
            if ai_reasoning is not None:
                remaining_ai_calls -= 1
        classification = db.query(Classification).filter_by(message_id=row.id).one_or_none()
        if classification is None:
            classification = Classification(message_id=row.id)
            db.add(classification)
        classification.category = category
        classification.source = "AI" if ai_reasoning else "RULE"
        classification.confidence = confidence
        classification.risk = result.risk
        classification.reasons = result.reasons
        classification.ai_reasoning = ai_reasoning
        classification.classifier_version = CLASSIFIER_VERSION

    db.commit()
    return stored


def _regroup(db: Session, mailbox_id, messages) -> None:
    """Rebuild groups and re-point every message at its group."""
    from app.analysis.grouping import build_group_key, display_name_for, group_messages

    rows = [
        {
            "gmail_id": m.gmail_message_id,
            "subject": m.subject,
            "received_at": m.received_at,
            "sender_domain": m.sender_domain,
            "sender_name": m.sender_name,
            "category": getattr(m.classification, "category", None),
        }
        for m in messages
    ]

    key_for_message = {
        row["gmail_id"]: build_group_key(
            row["sender_domain"], row["category"], row["subject"]
        )
        for row in rows
    }
    specs = group_messages(rows)

    existing_groups = {
        g.group_key: g
        for g in db.query(EmailGroup).filter_by(mailbox_id=mailbox_id).all()
    }
    for spec in specs:
        group = existing_groups.get(spec.group_key)
        if group is None:
            group = EmailGroup(mailbox_id=mailbox_id, group_key=spec.group_key)
            db.add(group)
        group.display_name = (
            spec.display_name or display_name_for(spec.primary_sender_domain, None)
        )
        group.primary_sender_domain = spec.primary_sender_domain
        group.primary_category = spec.primary_category
        group.message_count = spec.message_count
        group.first_message_at = spec.first_message_at
        group.last_message_at = spec.last_message_at
        group.sample_subjects = spec.sample_subjects
    db.flush()

    groups_by_key = dict(
        db.query(EmailGroup.group_key, EmailGroup.id)
        .filter_by(mailbox_id=mailbox_id)
        .all()
    )
    for m in messages:
        m.group_id = groups_by_key.get(key_for_message[m.gmail_message_id])
    db.commit()


def _recommend_all(db: Session, mailbox: Mailbox, messages: list, settings: Settings) -> dict:
    """Evaluate rules + recommender per message; upsert pending Recommendations."""
    from app.gmail.models import age_in_days
    from app.recommendations.engine import recommend
    from app.rules.engine import MessageContext, evaluate_rules

    rules = (
        db.query(CleanupRule)
        .filter(CleanupRule.user_id == mailbox.user_id, CleanupRule.enabled.is_(True))
        .order_by(CleanupRule.kind.desc(), CleanupRule.priority.asc())
        .all()
    )
    rule_dicts = [
        {"id": str(r.id), "name": r.name, "kind": r.kind,
         "match_all": r.match_all, "conditions": r.conditions}
        for r in rules
    ]

    counts: dict[str, int] = {}
    now = utcnow()
    for message in messages:
        classification = message.classification
        ctx = MessageContext(
            sender_domain=message.sender_domain,
            sender_email=message.sender_email,
            subject=message.subject,
            category=getattr(classification, "category", None),
            age_days=age_in_days(message.received_at, now=now),
            is_starred=message.is_starred,
            has_attachment=message.has_attachments,
            has_list_unsubscribe=message.has_list_unsubscribe,
        )
        evaluation = evaluate_rules(rule_dicts, ctx)
        outcome = recommend(
            classification_category=getattr(classification, "category", None),
            classification_confidence=getattr(classification, "confidence", None),
            classification_risk=getattr(classification, "risk", None),
            received_at=message.received_at,
            is_starred=message.is_starred,
            is_important=message.is_important,
            has_attachments=message.has_attachments,
            retention_years=settings.DEFAULT_RETENTION_YEARS,
            protected_by_rule_id=evaluation.protected_by_rule_id,
            protected_by_rule_name=evaluation.protected_by_rule_name,
            matched_cleanup_rule_ids=evaluation.matched_cleanup_rule_ids,
            now=now,
        )

        recommendation = (
            db.query(Recommendation).filter_by(message_id=message.id).one_or_none()
        )
        if recommendation is None:
            recommendation = Recommendation(message_id=message.id, mailbox_id=mailbox.id)
            db.add(recommendation)
        else:
            recommendation.status = "pending"  # re-analysis supersedes
        recommendation.action = outcome.action
        recommendation.confidence = outcome.confidence
        recommendation.risk = outcome.risk
        recommendation.reasons = outcome.reasons
        recommendation.contributing_rule_ids = outcome.contributing_rule_ids
        counts[outcome.action] = counts.get(outcome.action, 0) + 1

    db.commit()
    return counts

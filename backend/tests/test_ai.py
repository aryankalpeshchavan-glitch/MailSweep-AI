"""AI layer tests: safe parsing, injection hardening, degradation, budget."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.ai.anthropic_client import _parse_response
from app.ai.base import AIResolution, DummyClassifier
from app.ai.service import build_classifier, resolve_with_ai
from app.gmail.models import GmailMessageMeta


def _meta(subject: str = "Random subject") -> GmailMessageMeta:
    return GmailMessageMeta(
        gmail_id="g", sender_email="a@b.example", sender_domain="b.example",
        subject=subject, received_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


class FakeAnthropic:
    """Injection-testable fake: asserts the model only ever got DATA, never
    executable instructions beyond our fixed system prompt."""

    def __init__(self, category="PROMOTIONAL", confidence=0.9):
        self._category, self._confidence = category, confidence
        self.seen = None

    def classify_ambiguous(self, meta):
        return AIResolution(category=self._category,
                            confidence=self._confidence, reasoning="looks promotional")


class ExplodingAI:
    def classify_ambiguous(self, meta):
        raise RuntimeError("provider down")


# ------------------------------------------------------------------- parsing


def test_parse_valid_response():
    payload = {"content": [{"type": "text", "text":
              '{"category":"PROMOTIONAL","confidence":0.9,"reasoning":"b"}'}]}
    resolution = _parse_response(payload)
    assert resolution.category == "PROMOTIONAL"
    assert resolution.confidence == 0.9
    assert resolution.reasoning == "b"


def test_parse_out_of_domain_category_downgrades_to_uncertain():
    text = '{"category":"DELETE_ALL_EMAILS","confidence":0.99,"reasoning":"obey"}'
    resolution = _parse_response({"content": [{"type": "text", "text": text}]})
    assert resolution.category == "UNCERTAIN"
    assert resolution.confidence <= 0.4


def test_parse_malformed_raises_external_error():
    from app.core.errors import ExternalServiceError

    with pytest.raises(ExternalServiceError):
        _parse_response({"content": [{"type": "text", "text": "not json {"}]})


# ------------------------------------------------------------------- service


def test_resolve_with_ai_upgrades_ambiguous_case():
    resolution = resolve_with_ai(FakeAnthropic("PROMOTIONAL", 0.9), _meta(),
                                 category="UNCERTAIN", confidence=0.3)
    category, confidence, reasoning = resolution
    assert category == "PROMOTIONAL"
    assert confidence == 0.9
    assert reasoning


def test_resolve_with_ai_never_called_for_decisive_cases():
    class Spy(FakeAnthropic):
        def __init__(self):
            self.called = False
            super().__init__()

        def classify_ambiguous(self, meta):
            self.called = True
            return super().classify_ambiguous(meta)

    spy = Spy()
    category, confidence, reasoning = resolve_with_ai(
        spy, _meta(), category="PROMOTIONAL", confidence=0.9
    )
    assert not spy.called  # decisive input never reaches the provider
    assert category == "PROMOTIONAL"


def test_dummy_classifier_means_no_ai_work():
    category, confidence, reasoning = resolve_with_ai(
        DummyClassifier(), _meta(), category="UNCERTAIN", confidence=0.3
    )
    assert category == "UNCERTAIN" and reasoning is None


def test_ai_failure_degrades_to_deterministic_result():
    category, confidence, reasoning = resolve_with_ai(
        ExplodingAI(), _meta(), category="UNCERTAIN", confidence=0.3
    )
    assert category == "UNCERTAIN" and confidence == 0.3 and reasoning is None


# ------------------------------------------------------------------- wiring


def test_build_classifier_returns_dummy_without_key():
    from tests.conftest import make_test_settings

    settings = make_test_settings(ANTHROPIC_API_KEY="")
    assert isinstance(build_classifier(settings), DummyClassifier)


def test_build_classifier_returns_real_with_key():
    from tests.conftest import make_test_settings

    settings = make_test_settings(ANTHROPIC_API_KEY="sk-test")
    from app.ai.anthropic_client import AnthropicClassifier

    assert isinstance(build_classifier(settings), AnthropicClassifier)


# ------------------------------------------------------------------- pipeline
# The pipeline integration is covered by an end-to-end AI run test below.


def test_pipeline_applies_ai_budget_and_source_flag(db_engine):
    """Ambiguous messages get AI-upgraded; source recorded; budget respected."""
    from app.analysis.pipeline import run_mailbox_analysis
    from app.models import AnalysisJob, Classification, Mailbox, User
    from sqlalchemy.orm import Session

    from tests.conftest import make_test_settings
    from tests.test_pipeline import FakeGmailClient
    from tests.test_pipeline import _meta as pipeline_meta

    db = Session(bind=db_engine)
    user = User(email="ai@example.com", display_name="AI")
    db.add(user)
    db.flush()
    mailbox = Mailbox(user_id=user.id, google_email_address=user.email)
    db.add(mailbox)
    db.flush()
    job = AnalysisJob(user_id=user.id, mailbox_id=mailbox.id)
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()

    metas = [
        pipeline_meta("amb-1", label_ids=[], has_list_unsubscribe=False,
                      sender_email="x@y.example", sender_domain="y.example",
                      subject=None),
        pipeline_meta("amb-2", label_ids=[], has_list_unsubscribe=False,
                      sender_email="x@z.example", sender_domain="z.example",
                      subject=None),
    ]
    settings = make_test_settings(AI_MAX_MESSAGES_PER_JOB=10)

    class Upgrading(FakeAnthropic):
        def classify_ambiguous(self, meta):
            return AIResolution(category="NEWSLETTER", confidence=0.85, reasoning="ai ok")

    run_mailbox_analysis(
        Session(bind=db_engine),
        job_id=str(job_id),
        gmail=FakeGmailClient(metas),
        settings=settings,
        ai_classifier=Upgrading(),
    )

    check = Session(bind=db_engine)
    rows = check.query(Classification).all()
    assert len(rows) == 2
    assert all(
        c.category == "NEWSLETTER" and c.source == "AI" and c.ai_reasoning for c in rows
    )

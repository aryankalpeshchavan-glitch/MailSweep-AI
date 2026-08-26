"""AI resolution pass for the analysis pipeline (opt-in).

Only messages the deterministic classifier left ambiguous are sent to the
provider, and only subject-derived text is used. If AI is disabled or fails,
the deterministic result stands (UNCERTAIN -> REVIEW), so the app is fully
functional without any API key (spec §17/§18). Untrusted email content is
never treated as instructions (spec §18).
"""

from __future__ import annotations

import logging

from app.ai.base import AIClassifier, DummyClassifier
from app.core.config import Settings
from app.gmail.models import GmailMessageMeta

logger = logging.getLogger(__name__)

_AI_THRESHOLD = 0.55  # below this the classifier result counts as "ambiguous"


def resolve_with_ai(
    classifier: AIClassifier,
    meta: GmailMessageMeta,
    *,
    category: str,
    confidence: float | None,
) -> tuple[str, float | None, str | None]:
    """Optionally upgrade an ambiguous classification. Returns (cat, conf, ai_reasoning).

    Decisive classifications never reach the provider. Failures degrade to the
    deterministic result instead of breaking the job.
    """
    if category not in {"UNCERTAIN"} and (confidence or 0.0) >= _AI_THRESHOLD:
        return category, confidence, None
    if isinstance(classifier, DummyClassifier):
        return category, confidence, None

    try:
        resolution = classifier.classify_ambiguous(meta)
    except Exception as exc:  # noqa: BLE001 - AI failure must never break a job
        logger.warning(
            "AI resolution skipped",
            extra={"event": "ai_resolution_skipped", "error_type": type(exc).__name__},
        )
        return category, confidence, None

    if resolution.category == "UNCERTAIN":
        return category, confidence, resolution.reasoning
    upgraded = resolution.confidence >= (confidence or 0.0)
    return (
        resolution.category,
        resolution.confidence if upgraded else confidence,
        resolution.reasoning,
    )


def build_classifier(settings: Settings) -> AIClassifier:
    """Use the AI provider only when configured; otherwise a no-op."""
    if settings.ai_enabled and settings.ANTHROPIC_API_KEY:
        from app.ai.anthropic_client import AnthropicClassifier

        return AnthropicClassifier(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.ANTHROPIC_MODEL,
        )
    return DummyClassifier()

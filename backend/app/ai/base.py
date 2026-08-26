"""AI provider interface.

Every AI call in the codebase flows through :func:`classify_ambiguous` on
some implementation of :class:`AIClassifier`. There is no scattered provider
code. The Anthropic implementation lives in app.ai.anthropic_client; swap in
another provider (OpenAI, local LLM) by implementing this protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.gmail.models import GmailMessageMeta


@dataclass(slots=True)
class AIResolution:
    category: str
    confidence: float
    reasoning: str
    source: str = "ai"


class AIClassifier(Protocol):
    """Contract: resolve an ambiguous message's category, never execute."""

    def classify_ambiguous(self, meta: GmailMessageMeta) -> AIResolution: ...


class DummyClassifier:
    """No-op placeholder: never invoked when AI is disabled, keeps DI honest."""

    def classify_ambiguous(self, meta: GmailMessageMeta) -> AIResolution:
        raise AssertionError("AI classification invoked but provider is disabled.")

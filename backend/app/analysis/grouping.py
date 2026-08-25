"""Deterministic email grouping (spec §10).

Grouping key = hash(sender_domain | primary_category | subject_signature).
The signature normalizes volatile parts (digits, campaign ids, whitespace) so
"Your order #12345 shipped" and "Your order #67890 shipped" cluster together.

Pure functions - the pipeline feeds DB rows in and persists GroupSpecs out.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime

_SIGNATURE_MAX_CHARS = 40
_STRIP_NOISE = re.compile(r"[^a-z\s]")
_COLLAPSE_WS = re.compile(r"\s+")


@dataclass(slots=True)
class GroupSpec:
    group_key: str
    display_name: str
    primary_sender_domain: str | None
    primary_category: str | None
    message_count: int = 0
    first_message_at: datetime | None = None
    last_message_at: datetime | None = None
    sample_subjects: list[str] = field(default_factory=list)


def subject_signature(subject: str | None) -> str:
    """Stable, noise-free signature used inside the group key."""
    if not subject:
        return "nosubject"
    lowered = subject.lower()
    denoised = _STRIP_NOISE.sub(" ", lowered)
    collapsed = _COLLAPSE_WS.sub(" ", denoised).strip()
    return collapsed[:_SIGNATURE_MAX_CHARS] or "nosubject"


def build_group_key(sender_domain: str | None, category: str | None, subject: str | None) -> str:
    domain = sender_domain or "unknown"
    category_value = category or "unclassified"
    canonical = f"{domain}|{category_value}|{subject_signature(subject)}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def display_name_for(sender_domain: str | None, sender_name: str | None) -> str:
    if sender_domain:
        without_tld = sender_domain.rsplit(".", 1)[0]
        pretty = without_tld.replace("-", " ").replace("_", " ").replace(".", " ").strip()
        return pretty.title() or sender_domain
    return (sender_name or "Unknown sender").strip()


def group_messages(rows: list[dict]) -> list[GroupSpec]:
    """Aggregate message dicts into groups.

    Each row needs: gmail_id, subject, received_at,
    sender_domain, sender_name, category (classification result or None).
    """
    buckets: dict[str, GroupSpec] = {}
    for row in rows:
        domain = row.get("sender_domain")
        category = row.get("category")
        key = build_group_key(domain, category, row.get("subject"))
        spec = buckets.get(key)
        if spec is None:
            spec = GroupSpec(
                group_key=key,
                display_name=display_name_for(domain, row.get("sender_name")),
                primary_sender_domain=domain,
                primary_category=category,
            )
            buckets[key] = spec

        spec.message_count += 1
        received = row.get("received_at")
        if isinstance(received, datetime):
            if spec.first_message_at is None or received < spec.first_message_at:
                spec.first_message_at = received
            if spec.last_message_at is None or received > spec.last_message_at:
                spec.last_message_at = received
        subject = (row.get("subject") or "").strip()
        if subject and len(spec.sample_subjects) < 3 and subject not in spec.sample_subjects:
            spec.sample_subjects.append(subject)
    return sorted(buckets.values(), key=lambda g: (-g.message_count, g.display_name))

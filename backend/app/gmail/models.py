"""Pure parsing helpers for Gmail message metadata.

Kept free of I/O so every edge case (malformed headers, weird timezones,
missing dates) is unit-testable without any Google dependency.
"""

from __future__ import annotations

import email.utils
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

_SUBJECT_MAX_LEN = 500

#: Headers we request from Gmail - deliberately minimal (privacy, ADR-0006).
METADATA_HEADERS = ["From", "Subject", "Date", "List-Unsubscribe"]

STARRED_LABEL = "STARRED"
IMPORTANT_LABEL = "IMPORTANT"


@dataclass(slots=True)
class GmailMessageMeta:
    """Everything MailSweep ever learns about one message. Nothing more."""

    gmail_id: str
    thread_id: str | None = None
    label_ids: list[str] = field(default_factory=list)
    sender_email: str | None = None
    sender_name: str | None = None
    sender_domain: str | None = None
    subject: str | None = None
    received_at: datetime | None = None
    size_estimate: int | None = None
    is_starred: bool = False
    is_important: bool = False
    has_list_unsubscribe: bool = False
    has_attachments: bool = False
    attachment_count: int = 0


def parse_from_header(raw: str | None) -> tuple[str | None, str | None]:
    """Return (email, display_name) from a From header value.

    ``parseaddr`` falls back to treating bracket-less junk as an address-spec;
    we reject anything without an ``@`` as an address and keep it as a display
    name so domain extraction can never produce nonsense domains.
    """
    if not raw:
        return None, None
    name, address = email.utils.parseaddr(raw.strip())
    if address and "@" not in address:
        return None, (address.strip() or name.strip() or None)
    return (address.lower() or None), (name.strip() or None)


def extract_domain(address: str | None) -> str | None:
    if not address or "@" not in address:
        return None
    domain = address.rsplit("@", 1)[1].strip().lower()
    return domain or None


def truncate_subject(subject: str | None) -> str | None:
    if not subject:
        return None
    cleaned = " ".join(subject.split())
    return cleaned[:_SUBJECT_MAX_LEN] if cleaned else None


def parse_date_header(raw: str | None) -> datetime | None:
    """RFC 5322 date -> aware UTC datetime. Naive values are assumed UTC."""
    if not raw:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def epoch_millis_to_datetime(millis: str | int | None) -> datetime | None:
    if millis in (None, ""):
        return None
    try:
        seconds = int(millis) / 1000
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(seconds, tz=UTC)


def meta_from_api_payload(payload: dict) -> GmailMessageMeta:
    """Build :class:`GmailMessageMeta` from a Gmail ``format=metadata`` body."""
    message_id = str(payload.get("id", ""))
    headers: dict[str, str] = {}
    for entry in (payload.get("payload") or {}).get("headers") or []:
        name = entry.get("name")
        if name in METADATA_HEADERS:
            headers[name] = entry.get("value") or ""

    label_ids = [str(label) for label in payload.get("labelIds") or []]

    sender_email, sender_name = parse_from_header(headers.get("From"))
    received = parse_date_header(headers.get("Date"))
    if received is None:
        received = epoch_millis_to_datetime(payload.get("internalDate"))

    files = (payload.get("payload") or {}).get("files") or []

    return GmailMessageMeta(
        gmail_id=message_id,
        thread_id=payload.get("threadId"),
        label_ids=label_ids,
        sender_email=sender_email,
        sender_name=sender_name,
        sender_domain=extract_domain(sender_email),
        subject=truncate_subject(headers.get("Subject")),
        received_at=received,
        size_estimate=int(payload["sizeEstimate"]) if payload.get("sizeEstimate") else None,
        is_starred=STARRED_LABEL in label_ids,
        is_important=IMPORTANT_LABEL in label_ids,
        has_list_unsubscribe=bool(headers.get("List-Unsubscribe")),
        has_attachments=bool(files),
        attachment_count=len(files),
    )


def age_in_days(received_at: datetime | None, *, now: datetime | None = None) -> float | None:
    """Signal used by retention rules. None means 'unknown age'."""
    if received_at is None:
        return None
    reference = now or datetime.now(UTC)
    return max((reference - received_at).total_seconds() / 86_400, 0.0)


def retention_cutoff(years: int, *, now: datetime | None = None) -> datetime:
    reference = now or datetime.now(UTC)
    # 365.25 keeps year boundaries stable across leap years.
    return reference - timedelta(days=365.25 * years)

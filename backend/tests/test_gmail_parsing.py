"""Pure parsing helper tests (no I/O, no Google SDK)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.gmail.models import (
    GmailMessageMeta,
    age_in_days,
    epoch_millis_to_datetime,
    extract_domain,
    meta_from_api_payload,
    parse_date_header,
    parse_from_header,
    retention_cutoff,
    truncate_subject,
)


@pytest.mark.parametrize(
    ("raw", "email", "name"),
    [
        ("Newsletter <news@shop.example>", "news@shop.example", "Newsletter"),
        ("<bare@domain.example>", "bare@domain.example", None),
        ("plain@example.com", "plain@example.com", None),
        ("  Padded Name <padded@example.com>  ", "padded@example.com", "Padded Name"),
        (None, None, None),
        ("not-an-address", None, "not-an-address"),
    ],
)
def test_parse_from_header(raw, email, name):
    assert parse_from_header(raw) == (email, name)


def test_extract_domain():
    assert extract_domain("a@Mail.Example.COM") == "mail.example.com"
    assert extract_domain("no-at-sign") is None
    assert extract_domain(None) is None


def test_truncate_subject_collapses_whitespace_and_caps_length():
    assert truncate_subject("  Hello   World \t!") == "Hello World !"
    assert len(truncate_subject("x" * 900)) == 500  # type: ignore[arg-type]
    assert truncate_subject(None) is None
    assert truncate_subject("   ") is None


def test_date_parsing_converts_to_utc():
    with_offset = parse_date_header("Mon, 01 Jan 2024 10:00:00 +0200")
    assert with_offset == datetime(2024, 1, 1, 8, tzinfo=UTC)  # normalized to UTC

    naive = parse_date_header("Mon, 01 Jan 2024 10:00:00")
    assert naive is not None and naive.tzinfo is not None  # assumed UTC

    assert parse_date_header("garbage") is None
    assert parse_date_header(None) is None


def test_epoch_millis_conversion():
    assert epoch_millis_to_datetime("1700000000000") == datetime.fromtimestamp(
        1_700_000_000, tz=UTC
    )
    assert epoch_millis_to_datetime("bogus") is None
    assert epoch_millis_to_datetime(None) is None


def _api_payload() -> dict:
    return {
        "id": "gm-123",
        "threadId": "th-9",
        "labelIds": ["INBOX", "STARRED"],
        "sizeEstimate": 4242,
        "internalDate": "1700000000000",
        "payload": {
            "headers": [
                {"name": "From", "value": "Shop Deals <deals@shop.example>"},
                {"name": "Subject", "value": "  MEGA   SALE  "},
                {"name": "Date", "value": "Mon, 01 Jan 2024 10:00:00 +0000"},
                {"name": "List-Unsubscribe", "value": "<mailto:unsub@shop.example>"},
            ],
            "files": [{"filename": "invoice.pdf"}],
        },
    }


def test_meta_from_api_payload_maps_all_signals():
    meta = meta_from_api_payload(_api_payload())
    assert isinstance(meta, GmailMessageMeta)
    assert meta.gmail_id == "gm-123"
    assert meta.thread_id == "th-9"
    assert meta.sender_email == "deals@shop.example"
    assert meta.sender_domain == "shop.example"
    assert meta.subject == "MEGA SALE"  # whitespace-collapsed
    assert meta.is_starred is True
    assert meta.is_important is False
    assert meta.has_list_unsubscribe is True
    assert meta.has_attachments is True and meta.attachment_count == 1
    assert meta.size_estimate == 4242
    assert meta.received_at == datetime(2024, 1, 1, 10, tzinfo=UTC)


def test_age_and_retention_cutoff_math():
    now = datetime(2026, 8, 25, tzinfo=UTC)
    old = datetime(2020, 8, 26, tzinfo=UTC)
    assert age_in_days(old, now=now) > 365 * 5
    assert age_in_days(None, now=now) is None

    cutoff = retention_cutoff(5, now=now)
    assert (now - cutoff).days >= 365 * 5 - 1  # leap-year tolerance window
    assert cutoff.tzinfo is not None

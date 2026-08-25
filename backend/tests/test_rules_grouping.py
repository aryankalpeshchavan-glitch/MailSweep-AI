"""Rule-engine mechanics + grouping tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.analysis.grouping import (
    build_group_key,
    display_name_for,
    group_messages,
    subject_signature,
)
from app.rules.engine import MessageContext, evaluate_rules

_NOW = datetime(2026, 8, 25, tzinfo=UTC)


def _ctx(**overrides) -> MessageContext:
    base = dict(
        sender_domain="deals.shop.example", sender_email="news@deals.shop.example",
        subject="Flash sale ends soon", category="PROMOTIONAL",
        age_days=1500, is_starred=False, has_attachment=False,
        has_list_unsubscribe=True,
    )
    base.update(overrides)
    return MessageContext(**base)


def test_match_all_requires_every_condition():
    rule = {
        "id": "r1", "kind": "CLEANUP", "match_all": True,
        "conditions": [
            {"field": "sender_domain", "op": "ends_with", "value": "shop.example"},
            {"field": "older_than_days", "op": "gte", "value": 2000},
        ],
    }
    matched = evaluate_rules([rule], _ctx(age_days=2500))
    unmatched = evaluate_rules([rule], _ctx(age_days=100))
    assert matched.matched_cleanup_rule_ids == ["r1"]
    assert unmatched.matched_cleanup_rule_ids == []


def test_match_any_needs_only_one_condition():
    rule = {
        "id": "r2", "name": "any-of", "kind": "CLEANUP", "match_all": False,
        "conditions": [
            {"field": "category", "op": "eq", "value": "NEWSLETTER"},
            {"field": "subject_contains", "op": "contains", "value": "flash sale"},
        ],
    }
    outcome = evaluate_rules([rule], _ctx(category="PROMOTIONAL"))
    assert outcome.matched_cleanup_rule_ids == ["r2"]


def test_unknown_fields_fail_closed():
    rule = {
        "id": "r3", "kind": "CLEANUP", "match_all": True,
        "conditions": [{"field": "email_body", "op": "contains", "value": "x"}],
    }
    outcome = evaluate_rules([rule], _ctx())
    assert outcome.matched_cleanup_rule_ids == []  # never crashes, never matches


def test_protection_rules_evaluated_before_cleanup_kind():
    rules = [
        {"id": "c1", "name": "cleanup", "kind": "CLEANUP", "match_all": True,
         "conditions": [{"field": "sender_domain", "op": "ends_with", "value": "shop.example"}]},
        {"id": "p1", "name": "protect shop", "kind": "PROTECT", "match_all": True,
         "conditions": [{"field": "sender_domain", "op": "eq", "value": "deals.shop.example"}]},
    ]
    outcome = evaluate_rules(rules, _ctx())
    assert outcome.protected_by_rule_id == "p1"
    assert outcome.protected_by_rule_name == "protect shop"
    assert outcome.matched_cleanup_rule_ids == ["c1"]


def test_empty_or_malformed_conditions_never_match():
    rules = [
        {"id": "e1", "kind": "CLEANUP", "match_all": True, "conditions": []},
        {"id": "e2", "kind": "CLEANUP", "conditions": "garbage"},
        {"id": "e3", "kind": "PROTECT"},
    ]
    outcome = evaluate_rules(rules, _ctx())
    assert outcome.protected_by_rule_id is None
    assert outcome.matched_cleanup_rule_ids == []


# ---------------------------------------------------------------------------
# grouping


def test_subject_signature_normalizes_volatile_parts():
    a = subject_signature("Your order #12345 shipped!")
    b = subject_signature("Your order #98765 shipped?")
    assert a == b


def test_group_key_is_stable_and_bounded():
    k1 = build_group_key("shop.example", "PROMOTIONAL", "Sale today only")
    k2 = build_group_key("shop.example", "PROMOTIONAL", "Sale today only")
    assert k1 == k2
    assert len(k1) == 32


def test_group_messages_aggregates_counts_samples_and_dates():
    rows = [
        {"gmail_id": f"m{i}", "subject": f"Weekly digest #{i}",
         "received_at": _NOW - timedelta(days=i),
         "sender_domain": "acme.example", "sender_name": "Acme Weekly",
         "category": "NEWSLETTER"}
        for i in range(5)
    ] + [
        {"gmail_id": "z1", "subject": "Invoice March", "received_at": _NOW - timedelta(days=10),
         "sender_domain": "bank.example", "sender_name": None, "category": "RECEIPT"},
    ]
    groups = group_messages(rows)

    assert len(groups) == 2
    top = groups[0]
    assert top.message_count == 5
    assert top.display_name == "Acme"
    assert top.primary_category == "NEWSLETTER"
    assert len(top.sample_subjects) <= 3
    assert top.first_message_at is not None and top.last_message_at is not None


def test_display_name_pretty_prints_domains():
    assert display_name_for("cs.university.edu", None) == "Cs University"
    assert display_name_for(None, "Ada Lovelace") == "Ada Lovelace"
    assert display_name_for(None, None) == "Unknown sender"

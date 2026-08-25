"""User rule engine - declarative JSON conditions, deterministic evaluation.

PROTECT rules first: any match makes a message untouchable. CLEANUP rules
second: matches strengthen cleanup candidacy. ``match_all`` is AND vs OR.
Supported fields/ops are declared in _FIELD_OPS; unknown fields fail closed.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field


def _contains(haystack: object, needle: object) -> bool:
    return str(needle).lower() in str(haystack or "").lower()


def _ends_with(value: object, suffix: object) -> bool:
    return str(value or "").lower().endswith(str(suffix).lower())


def _gte(actual: object, threshold: object) -> bool:
    if actual is None:
        return False
    try:
        return float(str(actual)) >= float(str(threshold))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


_EQ, _NEQ = operator.eq, operator.ne

_FIELD_OPS: dict[str, dict[str, object]] = {
    "sender_domain": {"eq": _EQ, "ends_with": _ends_with},
    "sender_email": {"eq": _EQ, "contains": _contains},
    "subject_contains": {"contains": _contains},
    "category": {"eq": _EQ},
    "older_than_days": {"gte": _gte},
    "is_starred": {"eq": _EQ},
    "has_attachment": {"eq": _EQ},
    "has_list_unsubscribe": {"eq": _EQ},
}


@dataclass(slots=True)
class MessageContext:
    """Everything a rule may inspect. Built from DB rows by the pipeline."""

    sender_domain: str | None
    sender_email: str | None
    subject: str | None
    category: str | None
    age_days: float | None
    is_starred: bool
    has_attachment: bool
    has_list_unsubscribe: bool


@dataclass(slots=True)
class RuleEvaluation:
    protected_by_rule_id: str | None = None
    protected_by_rule_name: str | None = None
    matched_cleanup_rule_ids: list[str] = field(default_factory=list)
    matched_cleanup_rule_names: list[str] = field(default_factory=list)


def _condition_matches(condition: dict, ctx: MessageContext) -> bool:
    rule_field = str(condition.get("field"))
    op_name = str(condition.get("op"))
    expected = condition.get("value")
    ops = _FIELD_OPS.get(rule_field)
    if ops is None:
        return False  # unknown field never crashes evaluation; it just fails
    op = ops.get(op_name)
    if op is None:
        return False
    # Field-name -> context-attribute mapping for the few that differ.
    attr = {"older_than_days": "age_days", "subject_contains": "subject"}.get(
        rule_field, rule_field
    )
    actual = getattr(ctx, attr, None)
    try:
        return bool(op(actual, expected))
    except (TypeError, ValueError):
        return False


def evaluate_rules(rules: list[dict], ctx: MessageContext) -> RuleEvaluation:
    """Evaluate pre-sorted rules (protect kind first). Pure function."""
    outcome = RuleEvaluation()
    for rule in rules:
        conditions = rule.get("conditions") or []
        if not isinstance(conditions, list) or not conditions:
            continue
        results = (_condition_matches(c, ctx) for c in conditions)
        matched = all(results) if rule.get("match_all", True) else any(results)
        if not matched:
            continue
        if rule.get("kind") == "PROTECT" and outcome.protected_by_rule_id is None:
            outcome.protected_by_rule_id = str(rule.get("id"))
            outcome.protected_by_rule_name = rule.get("name")
        elif rule.get("kind") == "CLEANUP":
            outcome.matched_cleanup_rule_ids.append(str(rule.get("id")))
            outcome.matched_cleanup_rule_names.append(rule.get("name") or "")
    return outcome


def build_condition(field_name: str, op: str, value: object) -> dict:
    """Tiny helper for seeding default rules programmatically."""
    return {"field": field_name, "op": op, "value": value}

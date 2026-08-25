"""Deterministic classifier - stage 1 of analysis.

Priority: Gmail tab-category labels -> subject heuristics -> sender heuristics,
then bulk evidence (List-Unsubscribe), financial keywords raising risk.
Anything unresolved becomes UNCERTAIN (low confidence), which the recommender
maps to REVIEW, never deletion. Version bumps whenever behavior changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.gmail.models import GmailMessageMeta

CLASSIFIER_VERSION = "deterministic-v1"

_PROMOTIONAL_TERMS = (
    "% off", "sale", "deals", "discount", "coupon", "flash sale",
    "limited time", "free shipping", "offer ends", "exclusive offer",
    "last chance", "save big", "clearance",
)
_NEWSLETTER_TERMS = ("newsletter", "digest", "weekly roundup", "this week at", "monthly recap")
_FINANCIAL_TERMS = (
    "invoice", "receipt", "payment", "order confirmation", "billing",
    "statement", "tax document", "purchase",
)
_NO_REPLY_LOCAL_PARTS = ("no-reply", "noreply", "donotreply", "no_reply")

#: Baseline (category, confidence) when Gmail's own category label is present.
_GMAIL_CATEGORY_MAP = {
    "CATEGORY_PROMOTIONS": ("PROMOTIONAL", 0.90),
    "CATEGORY_SOCIAL": ("SOCIAL_NOTIFICATION", 0.85),
    "CATEGORY_UPDATES": ("AUTOMATED_NOTIFICATION", 0.75),
    "CATEGORY_FORUMS": ("AUTOMATED_NOTIFICATION", 0.70),
}

#: Removal-damage baseline per category (risk != confidence, spec §19).
_CATEGORY_RISK = {
    "PROMOTIONAL": "LOW",
    "NEWSLETTER": "LOW",
    "SOCIAL_NOTIFICATION": "LOW",
    "AUTOMATED_NOTIFICATION": "MEDIUM",
    "RECEIPT": "HIGH",
    "INVOICE": "HIGH",
    "PERSONAL": "HIGH",
    "PROFESSIONAL": "MEDIUM",
    "UNCERTAIN": "MEDIUM",
}


@dataclass(slots=True)
class ClassificationResult:
    category: str
    confidence: float
    risk: str
    reasons: list[dict] = field(default_factory=list)

    def add_reason(self, code: str, detail: str) -> None:
        self.reasons.append({"code": code, "detail": detail})


def classify(meta: GmailMessageMeta) -> ClassificationResult:
    """Classify one message from metadata only. Deterministic + side-effect free."""
    result = ClassificationResult(category="UNCERTAIN", confidence=0.45, risk="MEDIUM")

    _apply_gmail_category(meta, result)
    if result.category == "UNCERTAIN":
        _apply_subject_heuristics(meta, result)
        if result.category == "UNCERTAIN":
            _apply_sender_heuristics(meta, result)

    _apply_bulk_evidence(meta, result)
    _apply_financial_risk(meta, result)
    _apply_default_fallback(meta, result)

    result.confidence = round(min(max(result.confidence, 0.05), 0.99), 2)
    return result


def _subject_lower(meta: GmailMessageMeta) -> str:
    return (meta.subject or "").lower()


def _set(
    result: ClassificationResult,
    category: str,
    confidence: float,
    code: str,
    detail: str,
) -> None:
    result.category = category
    result.confidence = max(result.confidence, confidence)
    result.risk = _CATEGORY_RISK.get(category, result.risk)
    result.add_reason(code, detail)


def _apply_gmail_category(meta: GmailMessageMeta, result: ClassificationResult) -> None:
    for label_id in meta.label_ids:
        mapped = _GMAIL_CATEGORY_MAP.get(label_id)
        if mapped:
            result.category, result.confidence = mapped
            result.risk = _CATEGORY_RISK[result.category]
            pretty = label_id.removeprefix("CATEGORY_").title()
            result.add_reason("gmail_tab_category", f"Gmail filed this under {pretty}.")
            return


def _apply_subject_heuristics(meta: GmailMessageMeta, result: ClassificationResult) -> None:
    subject = _subject_lower(meta)
    if not subject:
        return
    if any(term in subject for term in _NEWSLETTER_TERMS):
        _set(result, "NEWSLETTER", 0.80, "subject_newsletter_terms", "Looks like a newsletter.")
    elif any(term in subject for term in _FINANCIAL_TERMS):
        _set(result, "RECEIPT", 0.80, "subject_financial_terms", "References receipts/payments.")
    elif any(term in subject for term in _PROMOTIONAL_TERMS):
        _set(result, "PROMOTIONAL", 0.70, "subject_promotional_terms", "Promotional language.")


def _apply_sender_heuristics(meta: GmailMessageMeta, result: ClassificationResult) -> None:
    local_part = (meta.sender_email or "").split("@")[0]
    if any(marker in local_part for marker in _NO_REPLY_LOCAL_PARTS):
        _set(
            result,
            "AUTOMATED_NOTIFICATION",
            max(result.confidence, 0.65),
            "no_reply_sender",
            "Sent by a no-reply automation address.",
        )


def _apply_bulk_evidence(meta: GmailMessageMeta, result: ClassificationResult) -> None:
    if not meta.has_list_unsubscribe:
        return
    if result.category in {"PROMOTIONAL", "NEWSLETTER"}:
        result.confidence += 0.05
    elif result.category == "UNCERTAIN":
        _set(
            result, "NEWSLETTER", 0.62,
            "list_unsubscribe_header", "Bulk mail (unsubscribe header).",
        )
    result.add_reason("list_unsubscribe_header", "Message advertises an unsubscribe mechanism.")


def _apply_financial_risk(meta: GmailMessageMeta, result: ClassificationResult) -> None:
    subject = _subject_lower(meta)
    if any(term in subject for term in _FINANCIAL_TERMS):
        result.risk = "HIGH"
        result.add_reason("financial_keyword", "Mentions financial documents - treat as sensitive.")


def _apply_default_fallback(meta: GmailMessageMeta, result: ClassificationResult) -> None:
    if result.category != "UNCERTAIN":
        return
    if "CATEGORY_PERSONAL" in meta.label_ids:
        _set(
            result, "PERSONAL", 0.60,
            "gmail_personal_category", "Gmail classified this as personal.",
        )
        return
    result.add_reason("unresolved_signals", "No strong signals found; needs human review.")


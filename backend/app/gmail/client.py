"""Gmail client abstraction.

``GmailClientProtocol`` is the ONLY interface the rest of the application
knows about; the Celery pipeline and cleanup executor depend on it, never on
Google's SDK. This gives us:

* hermetic tests via a fake implementing the same protocol,
* a single place enforcing metadata-only access (ADR-0006): the real client
  physically cannot fetch bodies because no method asks for them.

Scoping note (ADR-0004): ``gmail.modify`` technically allows body reads.
The defense here is behavioral and auditable - grep this file: only
``list``, ``get_metadata``, ``trash`` exist.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import Settings
from app.gmail.models import (
    METADATA_HEADERS,
    GmailMessageMeta,
    meta_from_api_payload,
)
from app.gmail.retry import execute_with_retry

if TYPE_CHECKING:  # pragma: no cover
    pass

logger = logging.getLogger(__name__)

_GMAIL_API_NAME = "gmail"
_GMAIL_API_VERSION = "v1"


class GmailClientProtocol(Protocol):
    """Operations MailSweep needs. Nothing else exists."""

    def list_message_ids(self, *, page_size: int, max_total: int) -> list[str]: ...

    def get_metadata(self, message_id: str) -> GmailMessageMeta: ...

    def trash_message(self, message_id: str) -> None: ...

    def close(self) -> None: ...


class GoogleGmailClient:
    """Real client bound to one user's access token for its lifetime."""

    def __init__(self, access_token: str, settings: Settings) -> None:
        self._settings = settings
        credentials = Credentials(token=access_token, scopes=None)
        # static_discovery=True ships the schema with the library: no network
        # round-trip, no discovery-cache files, deterministic behavior.
        self._service = build(
            _GMAIL_API_NAME,
            _GMAIL_API_VERSION,
            credentials=credentials,
            static_discovery=True,
            cache_discovery=False,
        )

    # ----------------------------------------------------------------- reads
    def list_message_ids(self, *, page_size: int, max_total: int) -> list[str]:
        """Paginated id listing. Bounded by max_total to cap quota exposure."""
        ids: list[str] = []
        request = self._service.users().messages().list(
            userId="me", maxResults=min(page_size, 500)
        )
        while request is not None and len(ids) < max_total:
            response = execute_with_retry(request.execute, operation_name="messages.list")
            ids.extend(str(item["id"]) for item in response.get("messages", []))
            request = (
                self._service.users().messages().list(
                    userId="me", pageToken=response.get("nextPageToken"),
                    maxResults=min(page_size, 500),
                )
                if response.get("nextPageToken")
                else None
            )
        return ids[:max_total]

    def get_metadata(self, message_id: str) -> GmailMessageMeta:
        """Metadata-only fetch. Bodies are never requested (see module docstring)."""
        request = self._service.users().messages().get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=METADATA_HEADERS,
        )
        payload = execute_with_retry(request.execute, operation_name="messages.get")
        return meta_from_api_payload(payload)

    # ---------------------------------------------------------------- writes
    def trash_message(self, message_id: str) -> None:
        """Move ONE message to Trash. The MVP's only destructive verb."""
        request = self._service.users().messages().trash(userId="me", id=message_id)
        execute_with_retry(
            request.execute,
            operation_name="messages.trash",
            # Trash is NOT auto-retried blindly beyond transport errors;
            # execute_with_retry already limits itself to 429/5xx.
        )

    # --------------------------------------------------------------- cleanup
    def close(self) -> None:
        try:
            self._service.close()
        except Exception:  # noqa: BLE001 - closing must never raise
            logger.debug("gmail service close raised", exc_info=True)


def http_error_status(exc: Exception) -> int | None:
    """Best-effort status extraction from googleapiclient HttpError."""
    if isinstance(exc, HttpError):
        return int(getattr(exc.resp, "status", 0) or 0)
    status = getattr(getattr(exc, "resp", None), "status", None)
    return int(status) if status else None

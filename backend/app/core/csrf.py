"""CSRF defense for cookie-authenticated state-changing requests.

Layered strategy:

1. ``SameSite=Lax`` cookie - the browser itself withholds the cookie on most
   cross-site POSTs.
2. This middleware - when a browser DOES attach an ``Origin`` header to an
   unsafe method (it does for all cross-origin fetch/XHR/form POSTs), that
   origin must be explicitly allow-listed.

Non-browser clients (curl, tests) send no ``Origin`` and are unaffected;
they cannot carry a victim's cookie anyway.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import request_id_var

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CsrfOriginMiddleware:
    def __init__(self, app: Any, allowed_origins: list[str]) -> None:
        self.app = app
        self._allowed = {origin.rstrip("/") for origin in allowed_origins}

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope.get("method") in _UNSAFE_METHODS:
            headers = {k.lower(): v for k, v in scope.get("headers") or []}
            origin = headers.get(b"origin")
            if origin is not None:
                decoded = origin.decode("latin-1").rstrip("/")
                if decoded not in self._allowed:
                    body = json.dumps(
                        {
                            "error": {"code": "forbidden_origin",
                                      "message": "Request origin is not allowed."},
                            "request_id": request_id_var.get(),
                        }
                    ).encode()
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 403,
                            "headers": [(b"content-type", b"application/json")],
                        }
                    )
                    await send({"type": "http.response.body", "body": body})
                    return
        await self.app(scope, receive, send)

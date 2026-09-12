"""The single error shape used by every non-2xx response.

Every error the API emits -- application errors raised here, Pydantic request
validation failures, and framework errors such as 404/405 -- is rendered as:

    {"error": {"code": "...", "message": "...", "details": [...]}}

`details` is always a list. Its entries always carry an ``issue`` key, plus
whichever of ``row``, ``field`` or ``view`` locates the problem in the request.
"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """An application-level error that maps directly onto the error envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def error_body(
    code: str, message: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Build the error envelope."""
    return {"error": {"code": code, "message": message, "details": details or []}}

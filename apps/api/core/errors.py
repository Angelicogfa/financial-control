"""Domain exception hierarchy translated into HTTP responses by the API layer.

Only these exceptions carry user-facing meaning. Anything else that escapes a handler is a
bug and must surface as an internal server error, never as a 4xx (finding I-05).
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for expected, user-facing business errors."""

    code: str = "DOMAIN_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code

    @property
    def message(self) -> str:
        return str(self.args[0]) if self.args else ""


class ValidationError(DomainError, ValueError):
    """Input or state violates a business rule (HTTP 400)."""

    code = "VALIDATION_ERROR"


class NotFoundError(DomainError, LookupError):
    """A referenced aggregate does not exist (HTTP 404)."""

    code = "NOT_FOUND"


class ConflictError(DomainError):
    """The request conflicts with existing state (HTTP 409)."""

    code = "CONFLICT"


class ForbiddenError(DomainError, PermissionError):
    """The authenticated caller lacks permission for the requested operation (HTTP 403)."""

    code = "FORBIDDEN"


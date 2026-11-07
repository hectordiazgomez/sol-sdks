from typing import Any


class SolError(Exception):
    """Base class for SDK and API failures."""


class APIError(SolError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        details: Any = None,
        request_id: str | None = None,
        headers: Any = None,
    ):
        super().__init__(message)
        self.status_code, self.code, self.details = status_code, code, details
        self.request_id, self.headers = request_id, headers


class AuthenticationError(APIError):
    pass


class PermissionDeniedError(APIError):
    pass


class NotFoundError(APIError):
    pass


class RateLimitError(APIError):
    pass


class ConnectionError(SolError):
    pass


class TimeoutError(ConnectionError):
    pass


class ProtocolError(SolError):
    pass


def api_error(body: Any, status: int | None = None, headers: Any = None) -> APIError:
    error = body.get("error", {}) if isinstance(body, dict) else {}
    if not isinstance(error, dict):
        error = {"message": str(error)}
    cls = {
        401: AuthenticationError,
        403: PermissionDeniedError,
        404: NotFoundError,
        429: RateLimitError,
    }.get(status or 0, APIError)
    return cls(
        error.get("message") or f"Sol API returned HTTP {status}",
        status_code=status,
        code=error.get("code"),
        details=error.get("details"),
        request_id=(headers or {}).get("x-request-id"),
        headers=headers,
    )

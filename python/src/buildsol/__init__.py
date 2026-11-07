"""Official Sol Python SDK. Keep your API key on your server."""

from ._transport import VERSION as __version__
from .audio import AsyncAudioStream, Audio, AudioStream
from .client import AsyncSol, Sol
from .errors import (
    APIError,
    AuthenticationError,
    ConnectionError,
    NotFoundError,
    PermissionDeniedError,
    ProtocolError,
    RateLimitError,
    SolError,
    TimeoutError,
)
from .live import AsyncLiveConnection, LiveConnection

__all__ = [
    "Sol",
    "AsyncSol",
    "Audio",
    "AudioStream",
    "AsyncAudioStream",
    "SolError",
    "APIError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "RateLimitError",
    "ConnectionError",
    "TimeoutError",
    "ProtocolError",
    "LiveConnection",
    "AsyncLiveConnection",
    "__version__",
]

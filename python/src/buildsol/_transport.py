import asyncio
import json
import mimetypes
import os
import random
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx

from .errors import ConnectionError, ProtocolError, TimeoutError, api_error
from .types import Upload

VERSION = "0.1.1"


def upload(value: Upload) -> tuple[str, bytes, str]:
    if isinstance(value, (str, Path)):
        p = Path(value)
        name, data = p.name, p.read_bytes()
    elif isinstance(value, tuple):
        name, data = value[:2]
        if len(value) == 3:
            return (name, data, value[2])
    elif isinstance(value, bytes):
        name, data = "audio.wav", value
    else:
        name, data = Path(getattr(value, "name", "audio.wav")).name, value.read()
    if not isinstance(data, bytes):
        raise TypeError("Audio must contain binary data")
    return name, data, mimetypes.guess_type(name)[0] or "application/octet-stream"


def form(values: Mapping[str, Any]) -> dict[str, str]:
    return {
        k: str(v).lower() if isinstance(v, bool) else str(v)
        for k, v in values.items()
        if v is not None
    }


def delay(response: httpx.Response | None, attempt: int) -> float:
    value = response.headers.get("retry-after") if response is not None else None
    if value:
        try:
            seconds = float(value)
        except ValueError:
            try:
                seconds = (
                    parsedate_to_datetime(value) - datetime.now(timezone.utc)
                ).total_seconds()
            except (ValueError, TypeError):
                seconds = 0
        return max(0, min(seconds, 60))
    return min(0.5 * 2**attempt + random.random() * 0.25, 8)


def json_body(data: bytes) -> Any:
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return {}


def sse(lines):
    data = []
    completed = False
    try:
        for line in lines:
            if line == "":
                if data:
                    value = event("\n".join(data))
                    completed |= value.get("type") == "completed"
                    yield value
                    data = []
            elif line.startswith("data:"):
                data.append(line[5:].removeprefix(" "))
        if data:
            value = event("\n".join(data))
            completed |= value.get("type") == "completed"
            yield value
        if not completed:
            raise ProtocolError("Transcription stream ended without a completed event")
    except httpx.TransportError as exc:
        raise transport_error(exc) from exc


def transport_error(exc):
    cls = TimeoutError if isinstance(exc, httpx.TimeoutException) else ConnectionError
    return cls("Sol response interrupted; partial responses are not retried")


def event(data: str) -> dict[str, Any]:
    try:
        value = json.loads(data)
    except ValueError as exc:
        raise ProtocolError("Invalid JSON in Sol event stream") from exc
    if not isinstance(value, dict):
        raise ProtocolError("Expected an event object")
    if value.get("type") == "error":
        err = value.get("error", {})
        raise api_error(
            value if "error" in value else {"error": value},
            err.get("status") if isinstance(err, dict) else None,
        )
    return value


class Transport:
    def __init__(
        self,
        api_key=None,
        *,
        base_url="https://api.buildsol.ai",
        timeout=120.0,
        max_retries=2,
        http_client=None,
        asynchronous=False,
    ):
        key = api_key or os.environ.get("SOL_API_KEY")
        if not key:
            raise ValueError("Set SOL_API_KEY or pass api_key")
        url = urlparse(base_url)
        if (
            url.username
            or url.password
            or url.query
            or url.fragment
            or url.scheme not in ("http", "https")
        ):
            raise ValueError("Invalid base_url")
        if url.scheme != "https" and url.hostname not in (
            "localhost",
            "127.0.0.1",
            "::1",
        ):
            raise ValueError("Remote base_url must use HTTPS")
        if not isinstance(max_retries, int) or not 0 <= max_retries <= 10:
            raise ValueError("max_retries must be between 0 and 10")
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url, self.key, self.timeout, self.max_retries = (
            base_url.rstrip("/"),
            key,
            timeout,
            max_retries,
        )
        self.owns_client = http_client is None
        self.http = http_client or (
            httpx.AsyncClient() if asynchronous else httpx.Client()
        )

    def build(self, method, path, *, idempotency_key=None, timeout=None, **kwargs):
        if not path.startswith("/v1/") or ".." in path:
            raise ValueError("Only relative public API paths are accepted")
        headers = {
            "Authorization": f"Bearer {self.key}",
            "User-Agent": f"buildsol-python/{VERSION}",
            "Accept": "application/json",
        }
        if idempotency_key is not None:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", idempotency_key):
                raise ValueError(
                    "idempotency_key must contain 1-64 letters, digits, _ or -"
                )
            if path not in ("/v1/translate", "/v1/audio/transcriptions"):
                raise ValueError("This endpoint does not support idempotency")
            headers["Idempotency-Key"] = idempotency_key
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        return self.http.build_request(
            method,
            self.base_url + path,
            headers=headers,
            timeout=self.timeout if timeout is None else timeout,
            **kwargs,
        )

    def request(self, method, path, **kwargs):
        safe = method == "GET" or bool(kwargs.get("idempotency_key"))
        for attempt in range(self.max_retries + 1):
            try:
                response = self.http.send(
                    self.build(method, path, **kwargs),
                    stream=True,
                    follow_redirects=False,
                )
            except httpx.TransportError as exc:
                if safe and attempt < self.max_retries:
                    time.sleep(delay(None, attempt))
                    continue
                cls = (
                    TimeoutError
                    if isinstance(exc, httpx.TimeoutException)
                    else ConnectionError
                )
                raise cls(
                    "Sol request failed; no automatic retry for non-idempotent operations"
                ) from exc
            if (
                safe
                and response.status_code in (408, 429, 500, 502, 503, 504)
                and attempt < self.max_retries
            ):
                seconds = delay(response, attempt)
                response.close()
                time.sleep(seconds)
                continue
            if not response.is_success:
                try:
                    body = response.read()
                finally:
                    response.close()
                raise api_error(json_body(body), response.status_code, response.headers)
            return response
        raise AssertionError("unreachable")

    async def arequest(self, method, path, **kwargs):
        safe = method == "GET" or bool(kwargs.get("idempotency_key"))
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.http.send(
                    self.build(method, path, **kwargs),
                    stream=True,
                    follow_redirects=False,
                )
            except httpx.TransportError as exc:
                if safe and attempt < self.max_retries:
                    await asyncio.sleep(delay(None, attempt))
                    continue
                cls = (
                    TimeoutError
                    if isinstance(exc, httpx.TimeoutException)
                    else ConnectionError
                )
                raise cls(
                    "Sol request failed; no automatic retry for non-idempotent operations"
                ) from exc
            if (
                safe
                and response.status_code in (408, 429, 500, 502, 503, 504)
                and attempt < self.max_retries
            ):
                seconds = delay(response, attempt)
                await response.aclose()
                await asyncio.sleep(seconds)
                continue
            if not response.is_success:
                try:
                    body = await response.aread()
                finally:
                    await response.aclose()
                raise api_error(json_body(body), response.status_code, response.headers)
            return response
        raise AssertionError("unreachable")

    def json(self, method, path, **kwargs):
        response = self.request(method, path, **kwargs)
        try:
            response.read()
            try:
                return response.json()
            except ValueError as exc:
                raise ProtocolError("Invalid JSON response from Sol") from exc
        except httpx.TransportError as exc:
            raise transport_error(exc) from exc
        finally:
            response.close()

    async def ajson(self, method, path, **kwargs):
        response = await self.arequest(method, path, **kwargs)
        try:
            await response.aread()
            try:
                return response.json()
            except ValueError as exc:
                raise ProtocolError("Invalid JSON response from Sol") from exc
        except httpx.TransportError as exc:
            raise transport_error(exc) from exc
        finally:
            await response.aclose()

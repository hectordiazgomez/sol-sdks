from pathlib import Path

import httpx

from .errors import ConnectionError, TimeoutError


class Audio:
    """A fully downloaded result. Use speech.stream() to consume immediately."""

    def __init__(self, content: bytes, headers: httpx.Headers):
        self.content, self.headers = content, headers
        self.request_id = headers.get("x-request-id")

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(self.content)


class AudioStream:
    def __init__(self, response):
        self.response, self.headers = response, response.headers
        self.request_id = response.headers.get("x-request-id")

    def __iter__(self):
        try:
            yield from self.response.iter_bytes()
        except httpx.TransportError as exc:
            cls = (
                TimeoutError
                if isinstance(exc, httpx.TimeoutException)
                else ConnectionError
            )
            raise cls(
                "Audio stream interrupted; audio already received is not retried"
            ) from exc

    def save(self, path: str | Path) -> None:
        with open(path, "wb") as file:
            for chunk in self:
                file.write(chunk)

    def close(self):
        self.response.close()


class AsyncAudioStream:
    def __init__(self, response):
        self.response, self.headers = response, response.headers
        self.request_id = response.headers.get("x-request-id")

    async def __aiter__(self):
        try:
            async for chunk in self.response.aiter_bytes():
                yield chunk
        except httpx.TransportError as exc:
            cls = (
                TimeoutError
                if isinstance(exc, httpx.TimeoutException)
                else ConnectionError
            )
            raise cls(
                "Audio stream interrupted; audio already received is not retried"
            ) from exc

    async def save(self, path: str | Path) -> None:
        # Small sequential disk writes; no audio buffering or transformation.
        with open(path, "wb") as file:
            async for chunk in self:
                file.write(chunk)

    async def close(self):
        await self.response.aclose()

import asyncio
import builtins
import json
from urllib.parse import urlparse

from websockets.asyncio.client import connect as async_connect
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect as sync_connect

from ._transport import event
from .errors import ConnectionError, ProtocolError, TimeoutError


class _State:
    def __init__(self, session, *, timeout=30):
        parsed = urlparse(session["url"])
        if parsed.scheme not in ("ws", "wss") or parsed.username or parsed.password:
            raise ValueError("Invalid WebSocket URL")
        if parsed.scheme != "wss" and parsed.hostname not in (
            "127.0.0.1",
            "localhost",
            "::1",
        ):
            raise ValueError("Remote WebSocket URL must use WSS")
        self.session, self.timeout = session, timeout
        self.socket = None
        self.context = None
        self.ready = None
        self.completed = False
        self.stopped = False

    def validate_audio(self, data):
        if self.stopped or self.completed:
            raise ProtocolError("Audio input is already stopped")
        if (
            not isinstance(data, bytes)
            or not data
            or len(data) % 2
            or len(data) > 65536
        ):
            raise ValueError(
                "Send even-length PCM16 bytes, between 2 and 65536 bytes per frame"
            )

    def decode(self, message):
        if not isinstance(message, str):
            raise ProtocolError("Expected JSON text from live transcription")
        value = event(message)
        if value.get("type") == "completed":
            self.completed = True
        return value


class LiveConnection(_State):
    def __enter__(self):
        try:
            self.context = sync_connect(
                self.session["url"],
                open_timeout=self.timeout,
                close_timeout=5,
                user_agent_header="buildsol-python/0.1.0",
            )
            self.socket = self.context.__enter__()
            self.socket.send(
                json.dumps({"type": "start", "token": self.session["token"]})
            )
            self.ready = self.receive()
            if self.ready.get("type") != "ready":
                raise ProtocolError("Expected live ready event")
            return self
        except BaseException:
            self.close()
            raise

    def send_audio(self, data: bytes):
        self.validate_audio(data)
        try:
            self.socket.send(data)
        except ConnectionClosed as exc:
            raise ConnectionError("Live connection closed") from exc

    def stop(self):
        if not self.stopped and not self.completed:
            try:
                self.socket.send('{"type":"stop"}')
            except ConnectionClosed as exc:
                raise ConnectionError(
                    "Live connection closed before completion"
                ) from exc
            self.stopped = True

    def receive(self):
        try:
            return self.decode(self.socket.recv(timeout=self.timeout))
        except ConnectionClosed as exc:
            raise ConnectionError("Live connection closed before completion") from exc
        except TimeoutError:
            raise
        except builtins.TimeoutError as exc:
            raise TimeoutError("Timed out waiting for live event") from exc

    def __iter__(self):
        while not self.completed:
            yield self.receive()

    def close(self):
        if self.context is not None:
            self.context.__exit__(None, None, None)
            self.context = None
        elif self.socket is not None:
            self.socket.close()

    def __exit__(self, *args):
        self.close()


class AsyncLiveConnection(_State):
    async def __aenter__(self):
        try:
            self.socket = await async_connect(
                self.session["url"],
                open_timeout=self.timeout,
                close_timeout=5,
                user_agent_header="buildsol-python/0.1.0",
            )
            await self.socket.send(
                json.dumps({"type": "start", "token": self.session["token"]})
            )
            self.ready = await self.receive()
            if self.ready.get("type") != "ready":
                raise ProtocolError("Expected live ready event")
            return self
        except BaseException:
            await self.close()
            raise

    async def send_audio(self, data: bytes):
        self.validate_audio(data)
        try:
            await self.socket.send(data)
        except ConnectionClosed as exc:
            raise ConnectionError("Live connection closed") from exc

    async def stop(self):
        if not self.stopped and not self.completed:
            try:
                await self.socket.send('{"type":"stop"}')
            except ConnectionClosed as exc:
                raise ConnectionError(
                    "Live connection closed before completion"
                ) from exc
            self.stopped = True

    async def receive(self):
        try:
            return self.decode(await asyncio.wait_for(self.socket.recv(), self.timeout))
        except ConnectionClosed as exc:
            raise ConnectionError("Live connection closed before completion") from exc
        except asyncio.TimeoutError as exc:
            raise TimeoutError("Timed out waiting for live event") from exc

    async def __aiter__(self):
        while not self.completed:
            yield await self.receive()

    async def close(self):
        if self.socket is not None:
            await self.socket.close()

    async def __aexit__(self, *args):
        await self.close()

from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

import httpx
from typing_extensions import Unpack

from ._transport import Transport, event, form, transport_error, upload
from .audio import AsyncAudioStream, Audio
from .types import (
    Balance,
    LiveSession,
    SpeechParams,
    Transcription,
    TranscriptionParams,
    Translation,
    Upload,
    VoiceList,
    VoiceParams,
    VoiceResult,
)


class Resource:
    def __init__(self, transport: Transport):
        self._t = transport


class Speech(Resource):
    @asynccontextmanager
    async def stream(
        self,
        *,
        reference_file: Upload | None = None,
        timeout: float | None = None,
        **params: Unpack[SpeechParams],
    ):
        kwargs = (
            {"json": params}
            if reference_file is None
            else {
                "data": form(params),
                "files": {"reference_audio": upload(reference_file)},
            }
        )
        response = await self._t.arequest(
            "POST", "/v1/text-to-speech", timeout=timeout, **kwargs
        )
        try:
            yield AsyncAudioStream(response)
        finally:
            await response.aclose()

    async def create(
        self,
        *,
        reference_file: Upload | None = None,
        timeout: float | None = None,
        **params: Unpack[SpeechParams],
    ) -> Audio:
        async with self.stream(
            reference_file=reference_file, timeout=timeout, **params
        ) as stream:
            content = b"".join([chunk async for chunk in stream])
            return Audio(content, stream.headers)


class Voices(Resource):
    async def list(
        self,
        *,
        country: str | None = None,
        gender: str | None = None,
        age: str | None = None,
        category: str | None = None,
        timeout: float | None = None,
    ) -> VoiceList:
        return await self._t.ajson(
            "GET",
            "/v1/voices",
            params=form(
                {"country": country, "gender": gender, "age": age, "category": category}
            ),
            timeout=timeout,
        )

    async def get(self, voice_id: str, *, timeout: float | None = None) -> VoiceResult:
        return await self._t.ajson(
            "GET", "/v1/voices/" + quote(voice_id, safe=""), timeout=timeout
        )

    async def create(
        self,
        *,
        name: str,
        audio: Upload,
        consent: bool,
        timeout: float | None = None,
        **params: Unpack[VoiceParams],
    ) -> VoiceResult:
        return await self._t.ajson(
            "POST",
            "/v1/voices",
            data=form({"name": name, "consent": consent, **params}),
            files={"audio": upload(audio)},
            timeout=timeout,
        )

    async def delete(
        self, voice_id: str, *, timeout: float | None = None
    ) -> dict[str, bool]:
        return await self._t.ajson(
            "DELETE", "/v1/voices/" + quote(voice_id, safe=""), timeout=timeout
        )


class Controls(Resource):
    async def get(self, *, timeout: float | None = None) -> dict[str, Any]:
        return await self._t.ajson("GET", "/v1/tts/controls", timeout=timeout)


class Dialects(Resource):
    async def list(self, *, timeout: float | None = None) -> dict[str, Any]:
        return await self._t.ajson("GET", "/v1/dialects", timeout=timeout)


class BalanceResource(Resource):
    async def get(self, *, timeout: float | None = None) -> Balance:
        return await self._t.ajson("GET", "/v1/balance", timeout=timeout)


class Transcriptions(Resource):
    async def create(
        self,
        *,
        file: Upload,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        **params: Unpack[TranscriptionParams],
    ) -> Transcription:
        return await self._t.ajson(
            "POST",
            "/v1/audio/transcriptions",
            data=form(params),
            files={"file": upload(file)},
            idempotency_key=idempotency_key,
            timeout=timeout,
        )

    @asynccontextmanager
    async def stream(
        self,
        *,
        file: Upload,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        **params: Unpack[TranscriptionParams],
    ):
        """SSE transport for a processed file; use live.connect for real-time audio."""
        response = await self._t.arequest(
            "POST",
            "/v1/audio/transcriptions",
            data=form({**params, "stream": True}),
            files={"file": upload(file)},
            idempotency_key=idempotency_key,
            timeout=timeout,
        )
        try:
            yield _sse(response)
        finally:
            await response.aclose()


class Translations(Resource):
    async def create(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        model: str = "sol-v1-preview-translate",
        idempotency_key: str | None = None,
        timeout: float | None = None,
    ) -> Translation:
        return await self._t.ajson(
            "POST",
            "/v1/translate",
            json={
                "text": text,
                "source_language": source_language,
                "target_language": target_language,
                "model": model,
            },
            idempotency_key=idempotency_key,
            timeout=timeout,
        )


class Live(Resource):
    async def create_session(
        self,
        *,
        language: str | None = None,
        model: str = "sol-transcribe-v1",
        timeout: float | None = None,
    ) -> LiveSession:
        return await self._t.ajson(
            "POST",
            "/v1/audio/transcription-sessions",
            json=form({"model": model, "language": language}),
            timeout=timeout,
        )

    @asynccontextmanager
    async def connect(
        self,
        *,
        session: LiveSession | None = None,
        language: str | None = None,
        timeout: float = 30,
    ):
        from .live import AsyncLiveConnection

        session = session or await self.create_session(
            language=language, timeout=timeout
        )
        connection = AsyncLiveConnection(session, timeout=timeout)
        async with connection:
            yield connection


async def _sse(response):
    data = []
    completed = False
    try:
        async for line in response.aiter_lines():
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
            from .errors import ProtocolError

            raise ProtocolError("Transcription stream ended without a completed event")
    except httpx.TransportError as exc:
        raise transport_error(exc) from exc

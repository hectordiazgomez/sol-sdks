from contextlib import contextmanager
from typing import Any
from urllib.parse import quote

from typing_extensions import Unpack

from ._transport import Transport, form, sse, upload
from .audio import Audio, AudioStream
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
    @contextmanager
    def stream(
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
        response = self._t.request(
            "POST", "/v1/text-to-speech", timeout=timeout, **kwargs
        )
        try:
            yield AudioStream(response)
        finally:
            response.close()

    def create(
        self,
        *,
        reference_file: Upload | None = None,
        timeout: float | None = None,
        **params: Unpack[SpeechParams],
    ) -> Audio:
        with self.stream(
            reference_file=reference_file, timeout=timeout, **params
        ) as stream:
            content = b"".join(stream)
            return Audio(content, stream.headers)


class Voices(Resource):
    def list(
        self,
        *,
        country: str | None = None,
        gender: str | None = None,
        age: str | None = None,
        category: str | None = None,
        timeout: float | None = None,
    ) -> VoiceList:
        return self._t.json(
            "GET",
            "/v1/voices",
            params=form(
                {"country": country, "gender": gender, "age": age, "category": category}
            ),
            timeout=timeout,
        )

    def get(self, voice_id: str, *, timeout: float | None = None) -> VoiceResult:
        return self._t.json(
            "GET", "/v1/voices/" + quote(voice_id, safe=""), timeout=timeout
        )

    def create(
        self,
        *,
        name: str,
        audio: Upload,
        consent: bool,
        timeout: float | None = None,
        **params: Unpack[VoiceParams],
    ) -> VoiceResult:
        return self._t.json(
            "POST",
            "/v1/voices",
            data=form({"name": name, "consent": consent, **params}),
            files={"audio": upload(audio)},
            timeout=timeout,
        )

    def delete(self, voice_id: str, *, timeout: float | None = None) -> dict[str, bool]:
        return self._t.json(
            "DELETE", "/v1/voices/" + quote(voice_id, safe=""), timeout=timeout
        )


class Controls(Resource):
    def get(self, *, timeout: float | None = None) -> dict[str, Any]:
        return self._t.json("GET", "/v1/tts/controls", timeout=timeout)


class Dialects(Resource):
    def list(self, *, timeout: float | None = None) -> dict[str, Any]:
        return self._t.json("GET", "/v1/dialects", timeout=timeout)


class BalanceResource(Resource):
    def get(self, *, timeout: float | None = None) -> Balance:
        return self._t.json("GET", "/v1/balance", timeout=timeout)


class Transcriptions(Resource):
    def create(
        self,
        *,
        file: Upload,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        **params: Unpack[TranscriptionParams],
    ) -> Transcription:
        return self._t.json(
            "POST",
            "/v1/audio/transcriptions",
            data=form(params),
            files={"file": upload(file)},
            idempotency_key=idempotency_key,
            timeout=timeout,
        )

    @contextmanager
    def stream(
        self,
        *,
        file: Upload,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        **params: Unpack[TranscriptionParams],
    ):
        """SSE transport for a processed file; use live.connect for real-time audio."""
        response = self._t.request(
            "POST",
            "/v1/audio/transcriptions",
            data=form({**params, "stream": True}),
            files={"file": upload(file)},
            idempotency_key=idempotency_key,
            timeout=timeout,
        )
        try:
            yield sse(response.iter_lines())
        finally:
            response.close()


class Translations(Resource):
    def create(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        model: str = "sol-v1-preview-translate",
        idempotency_key: str | None = None,
        timeout: float | None = None,
    ) -> Translation:
        return self._t.json(
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
    def create_session(
        self,
        *,
        language: str | None = None,
        model: str = "sol-transcribe-v1",
        timeout: float | None = None,
    ) -> LiveSession:
        return self._t.json(
            "POST",
            "/v1/audio/transcription-sessions",
            json=form({"model": model, "language": language}),
            timeout=timeout,
        )

    @contextmanager
    def connect(
        self,
        *,
        session: LiveSession | None = None,
        language: str | None = None,
        timeout: float = 30,
    ):
        from .live import LiveConnection

        session = session or self.create_session(language=language, timeout=timeout)
        connection = LiveConnection(session, timeout=timeout)
        with connection:
            yield connection

from dataclasses import replace
from uuid import uuid4

from buildsol import AsyncSol
from buildsol.errors import APIError as SolAPIError
from buildsol.errors import ProtocolError, SolError
from livekit.agents import APIConnectOptions, APIError, APIStatusError, tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS


class TTS(tts.TTS):
    """Incremental PCM speech from Sol. LiveKit handles sentence aggregation.

    Reads SOL_API_KEY by default. A supplied client remains caller-owned.
    Generation is never retried automatically, including after partial audio.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        voice_id: str | None = None,
        speed: float = 1.0,
        instruction: str | None = None,
        client: AsyncSol | None = None,
    ):
        if client is not None and api_key is not None:
            raise ValueError("Pass client or api_key, not both")
        if not 0.5 <= speed <= 2.0:
            raise ValueError("speed must be between 0.5 and 2.0")
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=24000,
            num_channels=1,
        )
        self._client = client if client is not None else AsyncSol(api_key=api_key)
        self._owns_client = client is None
        self._speech_options = {"speed": speed}
        if voice_id:
            self._speech_options["voice_id"] = voice_id
        if instruction:
            self._speech_options["instruction"] = instruction

    @property
    def provider(self) -> str:
        return "Sol"

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> tts.ChunkedStream:
        return _Stream(
            tts=self, input_text=text, conn_options=replace(conn_options, max_retry=0)
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.close()


class _Stream(tts.ChunkedStream):
    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        provider = self._tts
        assert isinstance(provider, TTS)
        try:
            async with provider._client.speech.stream(
                text=self.input_text,
                output_format="pcm",
                timeout=self._conn_options.timeout,
                **provider._speech_options,
            ) as audio:
                if audio.headers.get("x-sample-rate") != "24000":
                    raise ProtocolError("Sol returned an unexpected PCM sample rate")
                output_emitter.initialize(
                    request_id=audio.request_id or str(uuid4()),
                    sample_rate=24000,
                    num_channels=1,
                    mime_type="audio/pcm",
                    frame_size_ms=20,
                )
                pending = b""
                async for chunk in audio:
                    data = pending + chunk
                    size = len(data) & ~1
                    if size:
                        output_emitter.push(data[:size])
                    pending = data[size:]
                if pending:
                    raise ProtocolError("Sol returned truncated PCM audio")
        except SolAPIError as exc:
            raise APIStatusError(
                f"Sol TTS failed (HTTP {exc.status_code})",
                status_code=exc.status_code or -1,
                request_id=exc.request_id,
                retryable=False,
            ) from exc
        except SolError as exc:
            raise APIError("Sol TTS stream failed", retryable=False) from exc

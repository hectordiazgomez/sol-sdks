from collections.abc import AsyncGenerator

from buildsol import AsyncSol
from buildsol.errors import APIError, ProtocolError, SolError
from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService


class SolTTSService(TTSService):
    """Stream Sol PCM at its native 24 kHz, mono, signed 16-bit LE.

    Reads SOL_API_KEY by default. A supplied client remains caller-owned.
    Use PipelineParams(audio_out_sample_rate=24000); transports may resample.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        voice_id: str | None = None,
        speed: float = 1.0,
        instruction: str | None = None,
        client: AsyncSol | None = None,
        **kwargs,
    ):
        if client is not None and api_key is not None:
            raise ValueError("Pass client or api_key, not both")
        if not 0.5 <= speed <= 2.0:
            raise ValueError("speed must be between 0.5 and 2.0")
        super().__init__(
            sample_rate=24000,
            push_start_frame=True,
            push_stop_frames=True,
            settings=TTSSettings(model=None, voice=voice_id, language=None),
            **kwargs,
        )
        self._client = client if client is not None else AsyncSol(api_key=api_key)
        self._owns_client = client is None
        self._speed = speed
        self._instruction = instruction

    def can_generate_metrics(self) -> bool:
        return True

    async def cleanup(self):
        try:
            await super().cleanup()
        finally:
            if self._owns_client:
                await self._client.close()

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        options = {"speed": self._speed}
        if self._settings.voice:
            options["voice_id"] = self._settings.voice
        if self._instruction:
            options["instruction"] = self._instruction
        await self.start_ttfb_metrics()
        try:
            async with self._client.speech.stream(
                text=text, output_format="pcm", **options
            ) as audio:
                if audio.headers.get("x-sample-rate") != "24000":
                    raise ProtocolError("Sol returned an unexpected PCM sample rate")
                await self.start_tts_usage_metrics(text)
                pending = b""
                received = False
                async for chunk in audio:
                    data = pending + chunk
                    size = len(data) & ~1
                    if size:
                        await self.stop_ttfb_metrics()
                        received = True
                        yield TTSAudioRawFrame(
                            data[:size], 24000, 1, context_id=context_id
                        )
                    pending = data[size:]
                if pending or not received:
                    raise ProtocolError("Sol returned empty or truncated PCM audio")
        except SolError as exc:
            # Do not expose response bodies, submitted text or keys in pipeline logs.
            status = f" (HTTP {exc.status_code})" if isinstance(exc, APIError) else ""
            yield ErrorFrame(error=f"Sol TTS stream failed{status}")
        finally:
            await self.stop_ttfb_metrics()

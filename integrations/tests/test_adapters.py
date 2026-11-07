import asyncio
import json

import httpx
import pytest
from buildsol import AsyncSol
from buildsol_livekit import TTS
from buildsol_pipecat import SolTTSService
from livekit.agents import APIConnectOptions, APIError
from pipecat.frames.frames import (
    EndFrame,
    ErrorFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.workers.runner import WorkerRunner

pytestmark = pytest.mark.asyncio
PCM = bytes(range(256)) * 15  # 80 ms, split across odd transport boundaries.


class Body(httpx.AsyncByteStream):
    def __init__(self, data=PCM, block=False, fail=False):
        self.data, self.block, self.fail = data, block, fail
        self.closed = False
        self.waiting = asyncio.Event()

    async def __aiter__(self):
        yield self.data[:1]
        yield self.data[1:1921]
        self.waiting.set()
        if self.block:
            await asyncio.Event().wait()
        if self.fail:
            raise httpx.ReadError("interrupted")
        yield self.data[1921:]

    async def aclose(self):
        self.closed = True


def setup_client(body=None, status=200, rate="24000"):
    calls = []
    body = body or Body()

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"x-sample-rate": rate, "x-request-id": "test-request"},
            stream=body if status == 200 else Body(b'{"error":{"message":"denied"}}'),
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AsyncSol(api_key="test-only", http_client=http), http, body, calls


async def collect(kind, client):
    if kind == "livekit":
        adapter = TTS(client=client, voice_id="test-voice", speed=1.1)
        async with adapter.synthesize("Hola, Perú.") as stream:
            frames = [event.frame async for event in stream]
        await adapter.aclose()
        assert all(f.sample_rate == 24000 and f.num_channels == 1 for f in frames)
        return b"".join(f.data.tobytes() for f in frames)
    adapter = SolTTSService(client=client, voice_id="test-voice", speed=1.1)
    frames = [f async for f in adapter.run_tts("Hola, Perú.", "context-test")]
    errors = [f for f in frames if isinstance(f, ErrorFrame)]
    if errors:
        raise RuntimeError(errors[0].error)
    assert all(
        f.context_id == "context-test" and f.sample_rate == 24000 for f in frames
    )
    return b"".join(f.audio for f in frames)


@pytest.mark.parametrize("kind", ["livekit", "pipecat"])
async def test_pcm_preserved_and_injected_client_owned_by_caller(kind):
    client, http, body, calls = setup_client()
    async with http:
        assert await collect(kind, client) == PCM
        assert body.closed and not http.is_closed
        assert len(calls) == 1
        assert calls[0].url.path == "/v1/text-to-speech"
        assert json.loads(calls[0].content) == {
            "text": "Hola, Perú.",
            "voice_id": "test-voice",
            "speed": 1.1,
            "output_format": "pcm",
        }


@pytest.mark.parametrize("kind", ["livekit", "pipecat"])
@pytest.mark.parametrize("failure", ["http", "rate", "truncated", "empty", "midstream"])
async def test_failure_does_not_retry_generation(kind, failure):
    body = Body(
        b"x" if failure == "truncated" else b"" if failure == "empty" else PCM,
        fail=failure == "midstream",
    )
    client, http, body, calls = setup_client(
        body,
        status=429 if failure == "http" else 200,
        rate="16000" if failure == "rate" else "24000",
    )
    async with http:
        with pytest.raises((APIError, RuntimeError)):
            await collect(kind, client)
        assert len(calls) == 1
        if failure != "http":
            assert body.closed


@pytest.mark.parametrize("kind", ["livekit", "pipecat"])
async def test_cancellation_closes_active_response(kind):
    client, http, body, calls = setup_client(Body(block=True))
    async with http:
        if kind == "livekit":
            adapter = TTS(client=client)
            stream = adapter.synthesize(
                "Hola", conn_options=APIConnectOptions(max_retry=5)
            )
            await asyncio.wait_for(body.waiting.wait(), 3)
            await stream.aclose()
        else:
            adapter = SolTTSService(client=client)

            async def consume():
                async for _ in adapter.run_tts("Hola", "cancel-test"):
                    pass

            task = asyncio.create_task(consume())
            await asyncio.wait_for(body.waiting.wait(), 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert body.closed and len(calls) == 1


class Collector(FrameProcessor):
    def __init__(self):
        super().__init__()
        self.frames = []

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            self.frames.append(frame)
        await self.push_frame(frame, direction)


async def test_pipecat_real_pipeline_orders_frames_and_stops():
    client, http, body, calls = setup_client()
    async with http:
        service, sink = SolTTSService(client=client), Collector()
        worker = PipelineWorker(
            Pipeline([service, sink]),
            params=PipelineParams(audio_out_sample_rate=24000),
            enable_rtvi=False,
        )
        await worker.queue_frames([TTSSpeakFrame("Hola, Perú."), EndFrame()])
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        await asyncio.wait_for(runner.run(), 10)
        types = [type(f) for f in sink.frames]
        assert types.index(TTSStartedFrame) < types.index(TTSAudioRawFrame)
        assert types.index(TTSAudioRawFrame) < types.index(TTSStoppedFrame)
        assert (
            b"".join(f.audio for f in sink.frames if isinstance(f, TTSAudioRawFrame))
            == PCM
        )
        assert body.closed and len(calls) == 1


async def test_pipecat_failed_pipeline_can_end():
    client, http, body, calls = setup_client(status=401)
    async with http:
        service, sink = SolTTSService(client=client), Collector()
        worker = PipelineWorker(Pipeline([service, sink]), enable_rtvi=False)
        await worker.queue_frames([TTSSpeakFrame("Hola"), EndFrame()])
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        await asyncio.wait_for(runner.run(), 5)
        assert len(calls) == 1


async def test_livekit_stream_adapter_accepts_incremental_text():
    from livekit.agents import tokenize, tts

    client, http, body, calls = setup_client()
    async with http:
        adapter = tts.StreamAdapter(
            tts=TTS(client=client),
            sentence_tokenizer=tokenize.basic.SentenceTokenizer(),
        )
        async with adapter.stream() as stream:
            stream.push_text("Hola, ")
            stream.push_text("¿cómo estás?")
            stream.end_input()
            frames = [event.frame.data.tobytes() async for event in stream]
        await adapter.aclose()
        # LiveKit's StreamAdapter pads its final fixed-size frame with silence.
        result = b"".join(frames)
        assert result[: len(PCM)] == PCM
        assert not any(result[len(PCM) :])
        assert len(result) - len(PCM) < 9600
        assert len(calls) == 1 and body.closed

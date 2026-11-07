"""Generate sol-pipecat.wav through a real Pipecat pipeline; needs SOL_API_KEY."""

import asyncio
import os
import wave

from buildsol_pipecat import SolTTSService
from pipecat.frames.frames import EndFrame, TTSAudioRawFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.workers.runner import WorkerRunner


class WavOutput(FrameProcessor):
    def __init__(self, output):
        super().__init__()
        self.output = output

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM and isinstance(
            frame, TTSAudioRawFrame
        ):
            self.output.writeframesraw(frame.audio)
        await self.push_frame(frame, direction)


async def main():
    with wave.open("sol-pipecat.wav", "wb") as output:
        output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        worker = PipelineWorker(
            Pipeline(
                [SolTTSService(voice_id=os.getenv("SOL_VOICE_ID")), WavOutput(output)]
            ),
            params=PipelineParams(audio_out_sample_rate=24000),
            enable_rtvi=False,
        )
        await worker.queue_frames(
            [
                TTSSpeakFrame(
                    "Hola, soy Sol. Esta voz se está generando desde Pipecat."
                ),
                EndFrame(),
            ]
        )
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        await runner.run()


if __name__ == "__main__":
    asyncio.run(main())

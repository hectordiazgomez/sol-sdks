# Sol for Pipecat

Use Sol as the streaming TTS step in a Python Pipecat pipeline, locally or on
Pipecat Cloud. Maintained by Sol; not a built-in Pipecat provider listing.

## Install

Python 3.11+. Tested with Pipecat 1.15.0.

```sh
pip install "buildsol-pipecat @ git+https://github.com/hectordiazgomez/sol-sdks.git@integrations-v0.1.0#subdirectory=integrations/pipecat"
export SOL_API_KEY="your-sol-api-key"
```

Create your key at [Sol API keys](https://www.buildsol.ai/api-keys).
Keep it on your server. The adapter reads `SOL_API_KEY` automatically.

## Add to your pipeline

```python
from buildsol_pipecat import SolTTSService
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker

tts = SolTTSService()
pipeline = Pipeline(
    [
        transport.input(),
        stt,
        context_aggregator.user(),
        llm,
        tts,
        transport.output(),
        context_aggregator.assistant(),
    ]
)
worker = PipelineWorker(
    pipeline,
    params=PipelineParams(audio_out_sample_rate=24000),
)
```

Keep the transport, STT, LLM and context aggregator from your existing bot.
For a specific voice, pass `SolTTSService(voice_id="your-voice-id", speed=1.0)`.
Voice IDs, including your own clones, come from `AsyncSol().voices.list()`.
Omitting `voice_id` uses Sol's default voice. `instruction` is optional.

[Runnable pipeline](../../examples/pipecat_speech.py) generates a short WAV with
the real Pipecat pipeline and only a Sol key:
`python examples/pipecat_speech.py`. For Pipecat Cloud, include this package in
your bot's dependencies and set `SOL_API_KEY` in the deployment's secret set.
Your STT, LLM and transport/cloud usage remain separate from Sol TTS usage.

## Behavior

- Streams raw PCM16 mono at its native 24 kHz; configure pipeline output at 24 kHz.
  A transport can resample for its device or network requirements.
- Pipecat handles text aggregation, interruptions, context IDs and start/stop
  frames. Cancelling a running synthesis closes its HTTP response.
- The pipeline's cleanup closes the owned HTTP client; a supplied `client=AsyncSol(...)`
  remains caller-owned. No automatic generation retries.
- Errors are emitted as Pipecat `ErrorFrame`s. Empty/truncated audio and unexpected
  sample rates are errors. Text is not silently split or truncated.
- Requests are limited to 3,000 characters. No word-level alignment or guaranteed
  latency; location, network, text and server load affect first audio.

Native inclusion in Pipecat's provider catalogue requires upstream review.

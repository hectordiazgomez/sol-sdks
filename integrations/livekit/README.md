# Sol for LiveKit Agents

Stream Spanish speech from Sol in any Python LiveKit agent. Maintained by Sol;
this package does not add Sol to LiveKit Cloud's hosted provider selector.

## Install

Python 3.11+. Tested with LiveKit Agents 1.8.11.

```sh
pip install "buildsol-livekit @ git+https://github.com/hectordiazgomez/sol-sdks.git@integrations-v0.1.0#subdirectory=integrations/livekit"
export SOL_API_KEY="your-sol-api-key"
```

Create your key at [Sol API keys](https://www.buildsol.ai/api-keys).
Keep it on your server. The adapter reads `SOL_API_KEY` automatically.

## Add to your agent

```python
from livekit.agents import AgentSession
from buildsol_livekit import TTS

session = AgentSession(
    # Keep your existing STT, LLM and turn detection here.
    tts=TTS(),
)
```

For a specific voice, pass `TTS(voice_id="your-voice-id", speed=1.0)`.
Voice IDs, including your own clones, come from `AsyncSol().voices.list()`.
Omitting `voice_id` uses Sol's default voice. `instruction` is optional.

[Runnable agent](../../examples/livekit_agent.py): install the `silero` LiveKit
plugin, set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` and `SOL_API_KEY`,
then run `python examples/livekit_agent.py dev`. This example uses LiveKit
Inference for STT and LLM; their usage is separate from Sol's TTS usage.

## Behavior

- Streams raw PCM16 mono at 24 kHz; LiveKit receives 20 ms audio frames.
- LiveKit aggregates LLM text into sentences; audio streams as each sentence is
  synthesized. `capabilities.streaming=False` means no bidirectional text socket,
  not that the entire audio file is buffered.
- Cancelling/closing a synthesis stream closes its HTTP response. Close the TTS
  instance with `await tts.aclose()` when used outside an `AgentSession`.
- No automatic generation retries, even if LiveKit's connection options request
  retries. Repeating a synthesis can consume additional characters.
- Accepts an existing `AsyncSol` via `client=`; that client stays caller-owned.
- Requests are limited to 3,000 characters. Provider errors propagate to LiveKit.
- No word-level alignment. No guaranteed latency: location, network, text and
  server load affect time to first audio.

For native hosted listing, Sol and LiveKit must separately coordinate publication.

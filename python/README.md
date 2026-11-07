# Sol Python SDK

Official synchronous and asynchronous Python client. Requires Python 3.10+.

## Install

```sh
python -m pip install 'https://github.com/hectordiazgomez/sol-sdks/releases/download/v0.1.0/buildsol-0.1.0-py3-none-any.whl'
```

The versioned wheel is distributed through GitHub Releases. PyPI publication is pending. For development, clone this repository and run `pip install -e './python[dev]'`.

Set `SOL_API_KEY` on your server, then:

```python
from buildsol import Sol

with Sol() as sol:
    voices = sol.voices.list(country="PE")
    voice_id = voices["voices"][0]["id"]  # handle an empty catalogue in your app
    with sol.speech.stream(
        text="Hola, tu pedido llega mañana.", voice_id=voice_id, speed=1.0
    ) as audio:
        print(audio.request_id)
        audio.save("speech.mp3")
```

`AudioStream` is an iterator of unchanged `bytes`. Always use its context manager so an early exit closes the connection. `speech.create()` returns `Audio` with `.content`, `.headers`, `.request_id` and `.save(path)` after downloading the full result. `reference_file=` supports multipart references; the JSON `reference_audio=` field is base64 text. Do not combine references with `voice_id`.

## Async and incremental bytes

```python
import asyncio
from buildsol import AsyncSol


async def main():
    async with AsyncSol() as sol:
        async with sol.speech.stream(text="Buenos días.", output_format="pcm") as audio:
            async for chunk in audio:
                print(len(chunk))  # forward to your own compatible playback pipeline


asyncio.run(main())
```

## Transcription, translation and voices

```python
from buildsol import Sol

with Sol() as sol:
    transcript = sol.transcriptions.create(
        file="recording.wav",
        language="es",
        diarize=True,
        transcription_style="verbatim",
        idempotency_key="recording-2026-001",
    )
    print(transcript["text"], transcript["billing"])
    translated = sol.translations.create(
        text="Buenos días.",
        source_language="es",
        target_language="pt",
        idempotency_key="translation-2026-001",
    )
    print(translated["translation"])
    print(sol.controls.get(), sol.dialects.list(), sol.balance.get())

    # Only with the speaker's permission; creates an account voice:
    # voice = sol.voices.create(name="Mi voz", audio="reference.wav", consent=True)
    # sol.voices.get(voice["voice"]["id"])
    # sol.voices.delete(voice["voice"]["id"])  # irreversible
```

File inputs accept a path, `Path`, bytes (default filename `audio.wav`), an open binary file, `(filename, bytes)` or `(filename, bytes, content_type)`. Uploads are read into memory once, allowing safe idempotent replay of accepted small uploads. The SDK does not close caller-owned file objects.

File SSE:

```python
with Sol() as sol:
    with sol.transcriptions.stream(file="recording.wav", language="es") as events:
        for event in events:
            print(event)  # segment, metadata, completed; an error raises APIError
```

This does not make file transcription real-time. Use a live session for microphone input. See [live_python.py](https://github.com/hectordiazgomez/sol-sdks/blob/main/examples/live_python.py) for concurrent sending, real-time pacing and finalization. `LiveConnection` and `AsyncLiveConnection` can also consume a pre-issued single-use session. Live receive timeout defaults to 30 seconds; close the connection when done. No token is reused or reconnected automatically.

## Configuration and errors

```python
from buildsol import Sol, APIError, ConnectionError, TimeoutError

with Sol(timeout=120.0, max_retries=2) as sol:
    try:
        balance = sol.balance.get(timeout=15.0)
    except APIError as error:
        print(error.status_code, error.code, error.request_id)
    except TimeoutError:
        print("Request timed out")
    except ConnectionError:
        print("Connection interrupted")
```

Optional `api_key=`, `base_url=` and `http_client=` configure the client. HTTPX's timeout is a per-network-operation timeout (connect/read/write/pool), in seconds. Cancel an async task normally; `async with` releases resources. `AuthenticationError`, `PermissionDeniedError`, `NotFoundError` and `RateLimitError` subclass `APIError`; `.details` and `.headers` retain server information. `ProtocolError` reports malformed server events/JSON. Never log secrets or full audio.

Retries are limited to GET or explicit-idempotency transcription/translation requests; **TTS is never automatically retried**. Partial-stream failures preserve the partial file and raise an error; the caller should remove or label incomplete files. See the repository README for full API coverage, limits, token rules and billing distinctions.

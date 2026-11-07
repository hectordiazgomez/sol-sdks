# Sol SDKs

Official SDKs for [Sol](https://www.buildsol.ai): streaming text to speech, voice cloning, file/live transcription and translation.

| SDK | Runtime | Package |
| --- | --- | --- |
| [Python](python/README.md) | Python 3.10+ | `buildsol` — `Sol` and `AsyncSol` |
| [JavaScript / TypeScript](javascript/README.md) | Node.js 20+ | `buildsol` — ESM, CommonJS and TypeScript |

**Packages:** [Python on PyPI](https://pypi.org/project/buildsol/) and [JavaScript/TypeScript on npm](https://www.npmjs.com/package/buildsol). Versioned archives and checksums are also available in [GitHub Releases](https://github.com/hectordiazgomez/sol-sdks/releases).

```sh
python -m pip install buildsol
npm install buildsol
```

Create an API key at https://www.buildsol.ai/api-keys and set `SOL_API_KEY` in your server environment. Never put permanent keys in browsers, mobile bundles, logs or source control. Both clients call **https://api.buildsol.ai/v1** and never use private Studio/GPU endpoints.

```python
from buildsol import Sol

with Sol() as sol:
    with sol.speech.stream(text="Hola, tu pedido llega mañana.", speed=1.0) as audio:
        audio.save("speech.mp3")
```

```javascript
import { Sol } from "buildsol";

const sol = new Sol();
const audio = await sol.speech.stream({ text: "Hola, tu pedido llega mañana.", speed: 1.0 });
await audio.save("speech.mp3");
```

`stream()` exposes the first available bytes without waiting for the whole audio. `save()` writes incrementally; `create()` buffers the completed result. These examples save audio; they are not browser playback implementations. Audio chunks are not standalone files. The SDK does not resample audio, modify tags, normalize your text or change speed.

## Public API coverage

| Feature | Python | JavaScript |
| --- | --- | --- |
| Generate/download speech | `sol.speech.create(...)` | `sol.speech.create(params)` |
| Incremental speech | `with sol.speech.stream(...)` | `await sol.speech.stream(params)` |
| Filter/list/get voices | `sol.voices.list(...)`, `.get(id)` | `sol.voices.list(filters)`, `.get(id)` |
| Clone a consented voice | `sol.voices.create(name=..., audio=..., consent=True)` | `sol.voices.create({name, audio, consent: true})` |
| Delete own cloned voice | `sol.voices.delete(id)` | `sol.voices.delete(id)` |
| Supported voice controls | `sol.controls.get()` | `sol.controls.get()` |
| Dialects | `sol.dialects.list()` | `sol.dialects.list()` |
| Speech character balance | `sol.balance.get()` | `sol.balance.get()` |
| Transcribe uploaded file | `sol.transcriptions.create(file=...)` | `sol.transcriptions.create({file})` |
| File transcription SSE | `with sol.transcriptions.stream(file=...)` | `await sol.transcriptions.stream({file})` |
| Create live STT token | `sol.live.create_session(language="es")` | `sol.live.createSession({language: "es"})` |
| Live STT WebSocket | `with sol.live.connect(...)` | `await sol.live.connect(options)` |
| Translate | `sol.translations.create(...)` | `sol.translations.create(params)` |

All Python methods have equivalent awaitable methods on `AsyncSol`; streaming/live use `async with`. JSON responses are dictionaries in Python and typed objects in TypeScript. Field names match Sol's REST responses. No pagination is invented for the unpaginated voice catalogue. Supported country/gender/age/style combinations come from `controls.get()`; voice IDs come from `voices.list()`.

## Files, limits and billing

- Speech: up to 3,000 Unicode characters per request. `speed` 0.5–2.0, default 1.0. MP3, WAV or raw PCM. Read returned headers, including `x-sample-rate`; TTS PCM is separate from STT's input format.
- Cloning: a supported audio file, at least one minute, up to 25 MiB. Only clone voices you have permission to use. `consent` is required, never automatically asserted. The optional transcript corresponds to the first 30 seconds.
- File transcription: supported file up to 5 minutes / 25 MB. SSE is a transport for a processed upload, **not** live microphone recognition.
- Live transcription: single-use token expires after 60 seconds. Send raw signed PCM16 little-endian, 16 kHz, mono at real-time speed; no WAV header, compressed audio or whole-file burst. Send `stop`, then read `completed`. `transcript.text` replaces the cumulative hypothesis; do not append repeated hypotheses. No automatic reconnect or token reuse.
- Translation: up to 5,000 characters; Spanish paired with Portuguese, Quechua, Aymara or Guarani. Actual billing/usage is returned by the API.
- `balance.get()` is **TTS character credit**, not the separate USD credit used for transcription and translation. Do not infer one from the other.
- SDKs never split, truncate or discard input silently. Server validation errors are returned to your application.

## Reliability and security

`max_retries` / `maxRetries` defaults to 2. Only GET requests and file-transcription/translation calls with an explicit idempotency key may retry transient connection failures, 408, 429, 500, 502, 503 or 504. `Retry-After` is respected, capped at 60 seconds; otherwise retries use bounded exponential backoff with jitter. TTS, cloning, deletion and live-session creation are not retried automatically. After any response-body bytes arrive, an interrupted stream is never replayed. The application owns deciding whether to repeat a billable request.

Use a unique idempotency key per logical operation; reuse the same key only with the same file/settings or translation. Keys contain 1–64 ASCII letters, digits, hyphens or underscores. HTTP 409 in-progress/conflict errors are exposed to the caller; they are not silently retried. The SDK does not create idempotency keys for you.

Both clients require HTTPS for remote API URLs, disable redirects to avoid forwarding credentials, preserve error codes/details/request IDs, and have no telemetry. Local HTTP/WS is allowed only for localhost tests. Python reuses an HTTPX connection pool; Node reuses the runtime fetch pool. Python owns and closes its default client; an injected HTTPX client remains caller-owned. Node streams must be consumed or explicitly closed. Protect any application proxy with its own authentication and per-user limits.

- [Python guide](python/README.md)
- [JavaScript/TypeScript guide](javascript/README.md)
- [Runnable examples](examples/)
- [REST reference](https://www.buildsol.ai/docs)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [MIT license](LICENSE)

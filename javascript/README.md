# Sol JavaScript / TypeScript SDK

Official server-side Node.js 20+ client with TypeScript declarations, ESM and CommonJS.

## Install

```sh
npm install buildsol
```

Install the official `buildsol` package from [npm](https://www.npmjs.com/package/buildsol). For development, clone the repository and run `npm ci && npm run build` in `javascript/`.

Set `SOL_API_KEY` in your server environment. Do not bundle this SDK or permanent API keys into a browser.

```javascript
import { Sol } from "buildsol";

const sol = new Sol();
const audio = await sol.speech.stream({ text: "Hola, tu pedido llega mañana.", speed: 1.0 });
await audio.save("speech.mp3");
```

CommonJS: `const { Sol } = require("buildsol");`. TypeScript imports and options are identical. `speech.create()` returns a fully downloaded `Audio` with `.content` (`Uint8Array`), `.headers`, `.requestId` and `.save(path)`. `speech.stream()` returns a single-use async iterable of unchanged audio chunks, `.headers`, `.requestId`, `.save(path)` and `.close()`. Consume it or close it; `for await` early breaks clean up the response automatically.

```javascript
const stream = await sol.speech.stream({ text: "Buenos días.", output_format: "pcm" });
try {
  for await (const chunk of stream) {
    console.log(chunk.byteLength); // forward to a compatible playback pipeline
  }
} finally { await stream.close(); }
```

## All public resources

```javascript
import { Sol, fromFile } from "buildsol";
const sol = new Sol();

const { voices } = await sol.voices.list({ country: "PE" });
if (voices.length) console.log(await sol.voices.get(voices[0].id));
console.log(await sol.controls.get());
console.log(await sol.dialects.list());
console.log(await sol.balance.get()); // TTS characters, not STT/translation USD

const transcript = await sol.transcriptions.create({
  file: await fromFile("recording.wav", "audio/wav"),
  language: "es", diarize: true, transcription_style: "verbatim",
}, { idempotencyKey: "recording-2026-001" });
console.log(transcript.text, transcript.billing);

const translated = await sol.translations.create({
  text: "Buenos días.", source_language: "es", target_language: "pt",
}, { idempotencyKey: "translation-2026-001" });
console.log(translated.translation);

// Only with the speaker's permission; creates an account voice:
// const { voice } = await sol.voices.create({
//   name: "Mi voz", audio: await fromFile("reference.wav"), consent: true,
// });
// await sol.voices.delete(voice.id); // irreversible
```

Uploads accept `Blob`, `File`, `Uint8Array` (default filename `audio.wav`) or `{data, filename, contentType?}`. `fromFile(path, contentType?)` reads a local file once into memory. In speech, `referenceFile` sends multipart audio; `reference_audio` is the base64 JSON alternative. Do not combine either with `voice_id`.

`await sol.transcriptions.stream({file})` returns an async event iterable for file SSE (`segment`, `metadata`, `completed`). It is a transport for an already processed upload, not live transcription. Errors raise typed exceptions. Always consume or `.close()` it.

`sol.live.createSession({language: "es"})` issues a short-lived single-use token. `sol.live.connect({language: "es"})` creates one and opens the WebSocket; `sol.live.connect({session})` or `LiveConnection.connect(session)` consumes an existing session. It waits for `ready`. Use `sendAudio(bytes)`, `stop()` and async iteration, then `close()`. Read events while sending audio. Send raw PCM16LE, 16 kHz mono, paced in real time; no WAV header. Transcript events contain the cumulative hypothesis. Wait for `completed` after `stop`. There is no automatic reconnect. See [live_javascript.mjs](https://github.com/hectordiazgomez/sol-sdks/blob/main/examples/live_javascript.mjs).

## Timeouts, cancellation and errors

```javascript
import { Sol, APIError, TimeoutError, AbortError } from "buildsol";
const sol = new Sol({ timeoutMs: 120_000, maxRetries: 2 });
const controller = new AbortController();
try {
  const audio = await sol.speech.create({ text: "Hola." }, {
    timeoutMs: 30_000, signal: controller.signal,
  });
  await audio.save("hello.mp3");
} catch (error) {
  if (error instanceof APIError) console.error(error.status, error.code, error.requestId);
  else if (error instanceof AbortError) console.error("Cancelled");
  else if (error instanceof TimeoutError) console.error("Timed out");
  else throw error;
}
// Call controller.abort() from your application to cancel a pending request.
```

Client options: `apiKey`, `baseURL`, `timeoutMs`, `maxRetries` and injectable `fetch`. Every request accepts `signal` and `timeoutMs` as its second argument (catalogue methods without params take options as the first argument). HTTP timeouts include reading the response body, per attempt; retry backoff is additional. Live `timeoutMs` bounds the handshake and each event receive.

Errors: `APIError` includes `.status`, `.code`, `.details`, `.requestId`, `.headers`; subclasses `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`, `RateLimitError`. `ConnectionError`, `TimeoutError`, `AbortError`, `ProtocolError` cover transport/cancellation/protocol failures. No telemetry or automatic credential logging.

GET and explicit-idempotency transcription/translation operations can retry transient failures. **TTS, voice creation/deletion and live session creation are never automatically retried.** Streaming failures never trigger a replay. Partial audio files remain for your application to remove or label incomplete. See the repository README for all limits and billing distinctions.

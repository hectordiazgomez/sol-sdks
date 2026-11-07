import { Transport, multipart } from "./transport.js";
import { AudioStream, EventStream, collect } from "./streams.js";
import { LiveConnection } from "./live.js";
import type { SolOptions, SpeechParams, RequestOptions, FileInput, Voice, VoiceParams, Balance, TranscriptionParams, Transcription, TranslationParams, Translation, IdempotentOptions, LiveOptions, LiveSession } from "./types.js";
export * from "./types.js";
export * from "./errors.js";
export { Audio, AudioStream, EventStream } from "./streams.js";
export { LiveConnection } from "./live.js";
export { fromFile, VERSION } from "./transport.js";
/** Server-side Node.js/TypeScript client. Reads SOL_API_KEY by default. */
export class Sol {
  private transport: Transport;
  constructor(options: SolOptions = {}) { this.transport = new Transport(options); }
  readonly speech = {
    stream: async (params: SpeechParams & {referenceFile?: FileInput}, options?: RequestOptions): Promise<AudioStream> => {
      const {referenceFile, ...fields} = params;
      const body = referenceFile ? multipart(fields, "reference_audio", referenceFile) : fields;
      return new AudioStream(await this.transport.request("POST", "/v1/text-to-speech", body, options));
    },
    create: async (params: SpeechParams & {referenceFile?: FileInput}, options?: RequestOptions) => collect(await this.speech.stream(params, options)),
  };
  readonly voices = {
    list: (params: {country?: string; gender?: string; age?: string; category?: string} = {}, options?: RequestOptions) => {
      const query = new URLSearchParams(); for (const [key, value] of Object.entries(params)) if (value !== undefined) query.set(key, value);
      return this.transport.json<{voices: Voice[]; categories: Array<Record<string, unknown>>}>("GET", "/v1/voices" + (query.size ? "?" + query : ""), undefined, options);
    },
    get: (id: string, options?: RequestOptions) => this.transport.json<{voice: Voice}>("GET", "/v1/voices/" + encodeURIComponent(id), undefined, options),
    create: (params: VoiceParams, options?: RequestOptions) => { const {audio, ...fields} = params; return this.transport.json<{voice: Voice}>("POST", "/v1/voices", multipart(fields, "audio", audio), options); },
    delete: (id: string, options?: RequestOptions) => this.transport.json<{ok: boolean}>("DELETE", "/v1/voices/" + encodeURIComponent(id), undefined, options),
  };
  readonly controls = {get: (options?: RequestOptions) => this.transport.json<Record<string, unknown>>("GET", "/v1/tts/controls", undefined, options)};
  readonly dialects = {list: (options?: RequestOptions) => this.transport.json<{dialects: Array<Record<string, unknown>>}>("GET", "/v1/dialects", undefined, options)};
  readonly balance = {get: (options?: RequestOptions) => this.transport.json<Balance>("GET", "/v1/balance", undefined, options)};
  readonly transcriptions = {
    create: (params: TranscriptionParams, options?: IdempotentOptions) => { const {file, ...fields} = params; return this.transport.json<Transcription>("POST", "/v1/audio/transcriptions", multipart(fields, "file", file), options); },
    stream: async (params: TranscriptionParams, options?: IdempotentOptions) => { const {file, ...fields} = params; return new EventStream(new AudioStream(await this.transport.request("POST", "/v1/audio/transcriptions", multipart({...fields, stream: true}, "file", file), options))); },
  };
  readonly translations = {create: (params: TranslationParams, options?: IdempotentOptions) => this.transport.json<Translation>("POST", "/v1/translate", params, options)};
  readonly live = {
    createSession: (params: {language?: string; model?: "sol-transcribe-v1"} = {}, options?: RequestOptions) => this.transport.json<LiveSession>("POST", "/v1/audio/transcription-sessions", params, options),
    connect: async (options: LiveOptions = {}): Promise<LiveConnection> => {
      const {session, language, ...requestOptions} = options;
      return LiveConnection.connect(session || await this.live.createSession({language}, requestOptions), requestOptions);
    },
  };
}
export default Sol;

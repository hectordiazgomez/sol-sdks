export interface SpeechParams {
  text: string; voice_id?: string; country?: string; gender?: "female" | "male";
  age?: "young" | "middle_aged" | "old"; dialect?: string; style?: string;
  style_position?: "start" | "middle" | "end"; instruction?: string; speed?: number;
  output_format?: "mp3" | "wav" | "pcm"; reference_audio?: string;
  reference_text?: string; reference_filename?: string; seed?: number;
}
export interface Upload { data: Uint8Array | Blob; filename: string; contentType?: string }
export type FileInput = Upload | Blob | Uint8Array;
export interface Voice {
  id: string; name: string; description: string; gender: string; age_group: string;
  country: string; kind: string; categories: string[]; profile_key: string;
  dialect: Record<string, unknown> | null; preview_url: string | null;
  is_default: boolean; created_at: string;
}
export interface VoiceParams {
  name: string; audio: FileInput; consent: boolean; transcript?: string; dialect?: string;
  gender?: "female" | "male" | "neutral"; age_group?: "young" | "middle_aged" | "old";
  country?: string; description?: string;
}
export interface Balance {
  characters_remaining: number; free_remaining: number; subscription_remaining: number;
  topup_remaining: number; free_resets_at: string | null;
}
export interface TranscriptionParams {
  file: FileInput; model?: "sol-transcribe-v1"; language?: string; diarize?: boolean;
  transcription_style?: "verbatim" | "clean";
}
export interface Transcription {
  id: string; model: string; text: string; segments: Array<{id: number; text: string; start: number; end: number; speaker?: string}>;
  language: string | null; words: unknown[]; usage: Record<string, unknown>; billing: Record<string, unknown>;
}
export interface TranslationParams {
  text: string; source_language: string; target_language: string; model?: "sol-v1-preview-translate";
}
export interface Translation {
  id: string; model: string; translation: string; source_language: string; target_language: string;
  characters: number; usage: Record<string, unknown>; billing: Record<string, unknown>;
}
export interface LiveSession {
  id: string; model: string; token: string; expires_in: number; url: string;
  audio_format: {encoding: "pcm_s16le"; sample_rate: 16000; channels: 1}; max_seconds: number;
  billing: Record<string, unknown>;
}
export type SolEvent = Record<string, unknown> & { type: string; text?: string };
export interface RequestOptions { signal?: AbortSignal; timeoutMs?: number; }
export interface IdempotentOptions extends RequestOptions { idempotencyKey?: string; }
export interface LiveOptions extends RequestOptions { session?: LiveSession; language?: string; }
export interface SolOptions {
  apiKey?: string; baseURL?: string; timeoutMs?: number; maxRetries?: number;
  /** Injectable fetch for proxies/testing. Must preserve streaming. */
  fetch?: typeof globalThis.fetch;
}

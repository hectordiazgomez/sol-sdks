import { readFile } from "node:fs/promises";
import { basename } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { APIError, AbortError, ConnectionError, ProtocolError, TimeoutError, apiError } from "./errors.js";
import type { FileInput, IdempotentOptions, SolOptions, Upload } from "./types.js";
export const VERSION = "0.1.0";
export async function fromFile(path: string, contentType = "application/octet-stream"): Promise<Upload> {
  return {data: await readFile(path), filename: basename(path), contentType};
}
export function multipart(fields: Record<string, unknown>, key: string, input: FileInput): FormData {
  const form = new FormData();
  for (const [name, value] of Object.entries(fields)) if (value !== undefined && value !== null) form.set(name, String(value));
  const upload = input instanceof Blob || input instanceof Uint8Array ? {data: input, filename: "audio.wav"} : input;
  const blob = upload.data instanceof Blob ? upload.data : new Blob([new Uint8Array(upload.data)], {type: upload.contentType || "application/octet-stream"});
  // Preserve File.name when a Node File is supplied.
  const filename = "name" in upload.data && typeof upload.data.name === "string" ? upload.data.name : upload.filename;
  form.set(key, blob, filename);
  return form;
}
export interface PendingResponse { response: Response; dispose: () => void; mapError: (cause: unknown) => Error; }
export class Transport {
  readonly baseURL: string;
  private readonly key: string;
  private readonly timeoutMs: number;
  private readonly retries: number;
  private readonly fetcher: typeof fetch;
  constructor(options: SolOptions) {
    if (typeof window !== "undefined") throw new Error("Use the Sol SDK on your server; never expose SOL_API_KEY to a browser");
    this.key = options.apiKey || process.env.SOL_API_KEY || "";
    if (!this.key) throw new Error("Set SOL_API_KEY or pass apiKey");
    this.baseURL = (options.baseURL || "https://api.buildsol.ai").replace(/\/$/, "");
    const url = new URL(this.baseURL);
    if (url.username || url.password || url.search || url.hash || !["http:", "https:"].includes(url.protocol)) throw new Error("Invalid baseURL");
    if (url.protocol !== "https:" && !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) throw new Error("Remote baseURL must use HTTPS");
    this.timeoutMs = options.timeoutMs ?? 120_000;
    this.retries = options.maxRetries ?? 2;
    if (!Number.isInteger(this.retries) || this.retries < 0 || this.retries > 10) throw new Error("maxRetries must be between 0 and 10");
    if (!(this.timeoutMs > 0)) throw new Error("timeoutMs must be positive");
    this.fetcher = options.fetch || globalThis.fetch;
  }
  async request(method: string, path: string, body?: unknown, options: IdempotentOptions = {}): Promise<PendingResponse> {
    if (!path.startsWith("/v1/") || path.includes("..")) throw new Error("Only relative public API paths are accepted");
    if (options.idempotencyKey !== undefined && (!/^[A-Za-z0-9_-]{1,64}$/.test(options.idempotencyKey) || !["/v1/translate", "/v1/audio/transcriptions"].includes(path))) throw new Error("Invalid idempotencyKey or unsupported endpoint");
    const safe = method === "GET" || !!options.idempotencyKey;
    const timeout = options.timeoutMs ?? this.timeoutMs;
    if (!(timeout > 0)) throw new Error("timeoutMs must be positive");
    for (let attempt = 0; ; attempt++) {
      if (options.signal?.aborted) throw new AbortError("Sol request cancelled");
      const controller = new AbortController();
      let timedOut = false;
      const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeout);
      const abort = () => controller.abort();
      options.signal?.addEventListener("abort", abort, {once: true});
      const dispose = () => { clearTimeout(timer); options.signal?.removeEventListener("abort", abort); };
      const mapError = (cause: unknown) => options.signal?.aborted ? new AbortError("Sol request cancelled", {cause}) : timedOut ? new TimeoutError("Sol request timed out", {cause}) : cause instanceof APIError || cause instanceof ProtocolError ? cause : new ConnectionError("Sol request or stream interrupted; partial audio is not retried", {cause});
      const headers: Record<string, string> = {Authorization: `Bearer ${this.key}`, "User-Agent": `buildsol-node/${VERSION}`, Accept: "application/json"};
      if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
      if (body !== undefined && !(body instanceof FormData)) headers["Content-Type"] = "application/json";
      let response: Response;
      try {
        response = await this.fetcher(this.baseURL + path, {method, headers, redirect: "manual", signal: controller.signal,
          body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body)});
      } catch (cause) {
        dispose();
        if (safe && !options.signal?.aborted && attempt < this.retries) { await this.backoff(attempt, undefined, options.signal); continue; }
        throw mapError(cause);
      }
      if (safe && [408, 429, 500, 502, 503, 504].includes(response.status) && attempt < this.retries) {
        try { await response.body?.cancel(); } finally { dispose(); }
        await this.backoff(attempt, response.headers.get("retry-after"), options.signal); continue;
      }
      if (!response.ok) {
        let data: unknown;
        try { const text = await response.text(); try { data = JSON.parse(text); } catch { data = {}; } }
        catch (cause) { throw mapError(cause); } finally { dispose(); }
        throw apiError(data, response.status, response.headers);
      }
      return {response, dispose, mapError};
    }
  }
  private async backoff(attempt: number, retryAfter?: string | null, signal?: AbortSignal) {
    const seconds = retryAfter ? Number.isFinite(Number(retryAfter)) ? Number(retryAfter) : (Date.parse(retryAfter) - Date.now()) / 1000 : NaN;
    const ms = Number.isFinite(seconds) ? Math.max(0, Math.min(seconds * 1000, 60_000)) : Math.min(500 * 2 ** attempt + Math.random() * 250, 8000);
    try { await sleep(ms, undefined, {signal}); } catch (cause) { throw new AbortError("Sol retry cancelled", {cause}); }
  }
  async json<T>(method: string, path: string, body?: unknown, options?: IdempotentOptions): Promise<T> {
    const pending = await this.request(method, path, body, options);
    try {
      const text = await pending.response.text();
      try { return JSON.parse(text) as T; } catch (cause) { throw new ProtocolError("Invalid JSON response from Sol", {cause}); }
    } catch (cause) { throw pending.mapError(cause); } finally { pending.dispose(); }
  }
}

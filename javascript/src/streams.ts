import { open, writeFile } from "node:fs/promises";
import type { PendingResponse } from "./transport.js";
import { parseEvent, ProtocolError } from "./errors.js";
import type { SolEvent } from "./types.js";
export class Audio {
  readonly requestId?: string;
  constructor(readonly content: Uint8Array, readonly headers: Headers) { this.requestId = headers.get("x-request-id") ?? undefined; }
  async save(path: string): Promise<void> { await writeFile(path, this.content); }
}
export class AudioStream implements AsyncIterable<Uint8Array> {
  readonly headers: Headers;
  readonly requestId?: string;
  private used = false;
  constructor(private pending: PendingResponse) { this.headers = pending.response.headers; this.requestId = this.headers.get("x-request-id") ?? undefined; }
  async *[Symbol.asyncIterator](): AsyncGenerator<Uint8Array> {
    if (this.used) throw new ProtocolError("Stream already consumed");
    this.used = true;
    const reader = this.pending.response.body?.getReader();
    try {
      if (!reader) throw new ProtocolError("Sol returned no response body");
      while (true) { const {done, value} = await reader.read(); if (done) break; if (value.length) yield value; }
    } catch (cause) { throw this.pending.mapError(cause); }
    finally { try { await reader?.cancel().catch(() => {}); } finally { reader?.releaseLock(); this.pending.dispose(); } }
  }
  async save(path: string): Promise<void> {
    let file;
    try { file = await open(path, "w"); for await (const chunk of this) await file.writeFile(chunk); }
    finally { await file?.close(); await this.close(); }
  }
  async close(): Promise<void> {
    try { if (!this.pending.response.body?.locked) await this.pending.response.body?.cancel().catch(() => {}); }
    finally { this.pending.dispose(); }
  }
}
export class EventStream implements AsyncIterable<SolEvent> {
  constructor(private audio: AudioStream) {}
  async *[Symbol.asyncIterator](): AsyncGenerator<SolEvent> {
    const decoder = new TextDecoder(); let buffer = ""; let data: string[] = []; let completed = false;
    const line = (line: string) => {
      if (!line) { if (data.length) { const value = parseEvent(data.join("\n")); completed ||= value.type === "completed"; data = []; return value; } }
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    };
    for await (const chunk of this.audio) {
      buffer += decoder.decode(chunk, {stream: true});
      let index;
      while ((index = buffer.indexOf("\n")) >= 0) { const value = line(buffer.slice(0, index).replace(/\r$/, "")); buffer = buffer.slice(index + 1); if (value) yield value; }
      if (buffer.length > 8 * 1024 * 1024) throw new ProtocolError("SSE event exceeds 8 MiB");
    }
    buffer += decoder.decode();
    if (buffer) { const value = line(buffer.replace(/\r$/, "")); if (value) yield value; }
    if (data.length) { const value = parseEvent(data.join("\n")); completed ||= value.type === "completed"; yield value; }
    if (!completed) throw new ProtocolError("Transcription stream ended without a completed event");
  }
  close(): Promise<void> { return this.audio.close(); }
}
export async function collect(stream: AudioStream): Promise<Audio> {
  const chunks: Uint8Array[] = []; let length = 0;
  for await (const chunk of stream) { chunks.push(chunk); length += chunk.length; }
  const content = new Uint8Array(length); let offset = 0;
  for (const chunk of chunks) { content.set(chunk, offset); offset += chunk.length; }
  return new Audio(content, stream.headers);
}

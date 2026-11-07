import WebSocket from "ws";
import { AbortError, ConnectionError, ProtocolError, TimeoutError, parseEvent } from "./errors.js";
import type { LiveSession, RequestOptions, SolEvent } from "./types.js";
/** A single-use live session. Send raw PCM16LE/16 kHz/mono at real-time speed. */
export class LiveConnection implements AsyncIterable<SolEvent> {
  ready!: SolEvent;
  private queue: SolEvent[] = [];
  private waiter?: { resolve: (event: SolEvent) => void; reject: (error: Error) => void };
  private failure?: Error;
  private completed = false;
  private stopped = false;
  private socket: WebSocket;
  private abort: () => void;
  private constructor(readonly session: LiveSession, private options: RequestOptions) {
    if (options.timeoutMs !== undefined && !(options.timeoutMs > 0)) throw new Error("timeoutMs must be positive");
    const url = new URL(session.url);
    if (url.username || url.password || !["ws:", "wss:"].includes(url.protocol)) throw new Error("Invalid WebSocket URL");
    if (url.protocol !== "wss:" && !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) throw new Error("Remote WebSocket URL must use WSS");
    this.socket = new WebSocket(url, {handshakeTimeout: options.timeoutMs ?? 30_000, maxPayload: 8 * 1024 * 1024, headers: {"User-Agent": "buildsol-node/0.1.1"}});
    this.abort = () => { this.fail(new AbortError("Live session cancelled")); this.socket.terminate(); };
    options.signal?.addEventListener("abort", this.abort, {once: true});
    this.socket.on("message", (data, binary) => {
      try {
        if (binary) throw new ProtocolError("Expected JSON text from live transcription");
        const value = parseEvent(data.toString());
        if (value.type === "completed") this.completed = true;
        if (this.waiter) { const waiter = this.waiter; this.waiter = undefined; waiter.resolve(value); }
        else { this.queue.push(value); if (this.queue.length > 1024) throw new ProtocolError("Read live events while sending audio; queue exceeded 1024 events"); }
      } catch (error) { this.fail(error instanceof Error ? error : new ProtocolError(String(error))); this.socket.close(); }
    });
    this.socket.on("error", (cause) => this.fail(new ConnectionError("Live connection failed", {cause})));
    this.socket.on("close", () => {
      if (!this.completed) this.fail(new ConnectionError("Live connection closed before completion"));
      options.signal?.removeEventListener("abort", this.abort);
    });
  }
  static async connect(session: LiveSession, options: RequestOptions = {}): Promise<LiveConnection> {
    if (options.signal?.aborted) throw new AbortError("Live session cancelled");
    const connection = new LiveConnection(session, options);
    try {
      await new Promise<void>((resolve, reject) => {
        const opened = () => { cleanup(); resolve(); };
        const errored = (cause: Error) => { cleanup(); reject(new ConnectionError("Live connection failed", {cause})); };
        const closed = () => { cleanup(); reject(connection.failure || new ConnectionError("Live connection closed during handshake")); };
        const cleanup = () => { connection.socket.off("open", opened); connection.socket.off("error", errored); connection.socket.off("close", closed); };
        connection.socket.once("open", opened); connection.socket.once("error", errored); connection.socket.once("close", closed);
      });
      await connection.send(JSON.stringify({type: "start", token: session.token}));
      connection.ready = await connection.receive();
      if (connection.ready.type !== "ready") throw new ProtocolError("Expected live ready event");
      return connection;
    } catch (error) { await connection.close(); throw error; }
  }
  private fail(error: Error) { this.failure ??= error; if (this.waiter) { this.waiter.reject(error); this.waiter = undefined; } }
  private send(data: string | Uint8Array): Promise<void> {
    if (this.failure) return Promise.reject(this.failure);
    return new Promise((resolve, reject) => this.socket.send(data, (cause) => cause ? reject(new ConnectionError("Could not send live audio", {cause})) : resolve()));
  }
  async sendAudio(data: Uint8Array): Promise<void> {
    if (this.stopped || this.completed) throw new ProtocolError("Audio input is already stopped");
    if (!(data instanceof Uint8Array) || !data.length || data.length % 2 || data.length > 65536) throw new Error("Send even-length PCM16 bytes, between 2 and 65536 bytes per frame");
    await this.send(data);
  }
  async stop(): Promise<void> { if (!this.stopped && !this.completed) { this.stopped = true; await this.send('{"type":"stop"}'); } }
  async receive(): Promise<SolEvent> {
    if (this.failure) throw this.failure;
    const queued = this.queue.shift(); if (queued) return queued;
    if (this.completed) throw new ProtocolError("Live session already completed");
    if (this.waiter) throw new ProtocolError("Only one live event reader is allowed");
    let timer: NodeJS.Timeout | undefined;
    try { return await new Promise<SolEvent>((resolve, reject) => {
      this.waiter = {resolve, reject};
      timer = setTimeout(() => { this.waiter = undefined; reject(new TimeoutError("Timed out waiting for live event")); }, this.options.timeoutMs ?? 30_000);
    }); } finally { clearTimeout(timer); }
  }
  async *[Symbol.asyncIterator](): AsyncGenerator<SolEvent> {
    try { while (this.queue.length || !this.completed) yield await this.receive(); }
    finally { await this.close(); }
  }
  async close(): Promise<void> {
    this.options.signal?.removeEventListener("abort", this.abort);
    if (this.socket.readyState === WebSocket.CLOSED) return;
    await new Promise<void>((resolve) => {
      const timer = setTimeout(() => { this.socket.terminate(); }, 2000);
      this.socket.once("close", () => { clearTimeout(timer); resolve(); });
      if (this.socket.readyState === WebSocket.CONNECTING) this.socket.terminate(); else this.socket.close();
    });
  }
}

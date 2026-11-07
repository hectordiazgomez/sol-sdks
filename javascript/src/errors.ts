export class SolError extends Error { constructor(message: string, options?: ErrorOptions) { super(message, options); this.name = new.target.name; } }
export class APIError extends SolError {
  constructor(message: string, public status?: number, public code?: string, public details?: unknown,
    public requestId?: string, public headers?: Headers) { super(message); }
}
export class AuthenticationError extends APIError {}
export class PermissionDeniedError extends APIError {}
export class NotFoundError extends APIError {}
export class RateLimitError extends APIError {}
export class ConnectionError extends SolError {}
export class TimeoutError extends ConnectionError {}
export class AbortError extends ConnectionError {}
export class ProtocolError extends SolError {}
export function apiError(body: unknown, status?: number, headers?: Headers): APIError {
  const error = typeof body === "object" && body !== null && "error" in body ? body.error : {};
  const e = typeof error === "object" && error !== null ? error as Record<string, unknown> : {};
  const Cls = status === 401 ? AuthenticationError : status === 403 ? PermissionDeniedError : status === 404 ? NotFoundError : status === 429 ? RateLimitError : APIError;
  return new Cls(typeof e.message === "string" ? e.message : `Sol API returned HTTP ${status}`,
    status, typeof e.code === "string" ? e.code : undefined, e.details, headers?.get("x-request-id") ?? undefined, headers);
}
export function parseEvent(text: string): import("./types.js").SolEvent {
  let value;
  try { value = JSON.parse(text); } catch (cause) { throw new ProtocolError("Invalid JSON in Sol event stream", {cause}); }
  if (!value || typeof value !== "object" || typeof value.type !== "string") throw new ProtocolError("Invalid Sol event");
  if (value.type === "error") throw apiError(value.error ? value : {error: value}, value.error?.status ?? value.status);
  return value;
}

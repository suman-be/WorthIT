/**
 * Minimal JSON client for the WorthIT backend.
 *
 * Every outcome is turned into either parsed, validated data or an ApiError
 * with a plain-language message and fix. Nothing else escapes this module.
 */
import { API_BASE_URL } from './config';
import { ApiError, badResponseError, networkError, timeoutError } from './errors';

export interface RequestOptions<T> {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  /** Validates the JSON body and returns typed data. Throw if the shape is wrong. */
  parse: (data: unknown) => T;
  /** Used in messages, for example "the serial number lookup". */
  what: string;
  /** Replace the generic 404 error with a specific one. */
  notFound?: () => ApiError;
  timeoutMs?: number;
}

export const DEFAULT_TIMEOUT_MS = 10_000;

interface ServerErrorBody {
  message?: string;
  field?: string;
}

/** Reads `{ "error": { "message", "field" } }` or `{ "message", "field" }` if present. */
async function readErrorBody(response: Response): Promise<ServerErrorBody> {
  try {
    const data: unknown = await response.json();
    if (typeof data !== 'object' || data === null) return {};
    const root = data as Record<string, unknown>;
    const inner = typeof root.error === 'object' && root.error !== null ? (root.error as Record<string, unknown>) : root;
    const message = typeof inner.message === 'string' && inner.message.length <= 300 ? inner.message : undefined;
    const field = typeof inner.field === 'string' ? inner.field : undefined;
    return { ...(message ? { message } : {}), ...(field ? { field } : {}) };
  } catch {
    return {};
  }
}

function parseRetryAfter(header: string | null): number | undefined {
  if (!header) return undefined;
  const seconds = Number(header);
  if (Number.isFinite(seconds) && seconds >= 0) return Math.ceil(seconds);
  const date = Date.parse(header);
  if (Number.isNaN(date)) return undefined;
  return Math.max(0, Math.ceil((date - Date.now()) / 1000));
}

export async function errorFromResponse(response: Response, what: string, notFound?: () => ApiError): Promise<ApiError> {
  const { status } = response;
  const body = await readErrorBody(response);

  if (status === 400 || status === 422) {
    return new ApiError(
      'invalid_request',
      body.message ?? `The service could not accept ${what}.`,
      'Check what you entered, then try again.',
      { status, ...(body.field ? { field: body.field } : {}) },
    );
  }
  if (status === 401 || status === 403) {
    return new ApiError('unauthorized', 'Your session has ended or you do not have access.', 'Sign in again, then retry.', {
      status,
    });
  }
  if (status === 404) {
    return notFound?.() ?? new ApiError('not_found', `We could not find ${what}.`, 'Check the details and try again.', { status });
  }
  if (status === 408) return timeoutError(what);
  if (status === 429) {
    const retryAfterSeconds = parseRetryAfter(response.headers.get('Retry-After'));
    return new ApiError(
      'rate_limited',
      'Too many requests were sent in a short time.',
      retryAfterSeconds
        ? `Wait ${retryAfterSeconds} ${retryAfterSeconds === 1 ? 'second' : 'seconds'}, then select Try again.`
        : 'Wait a minute, then select Try again.',
      { status, ...(retryAfterSeconds !== undefined ? { retryAfterSeconds } : {}) },
    );
  }
  return new ApiError(
    'server',
    `The WorthIT service had a problem with ${what} (error ${status}).`,
    'This was not caused by anything you did. Select Try again in a moment.',
    { status },
  );
}

export async function request<T>(path: string, options: RequestOptions<T>): Promise<T> {
  const { method = 'GET', body, parse, what, notFound, timeoutMs = DEFAULT_TIMEOUT_MS } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await globalThis.fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      // Auth uses an HttpOnly session cookie set by the backend. No tokens live in the frontend.
      credentials: 'include',
      signal: controller.signal,
    });
  } catch {
    throw controller.signal.aborted ? timeoutError(what) : networkError(what);
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) throw await errorFromResponse(response, what, notFound);

  let data: unknown;
  if (response.status !== 204) {
    try {
      data = await response.json();
    } catch {
      throw badResponseError(what);
    }
  }

  try {
    return parse(data);
  } catch {
    throw badResponseError(what);
  }
}

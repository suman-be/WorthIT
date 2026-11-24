export type ApiErrorCode =
  | 'not_found'
  | 'invalid_request'
  | 'unauthorized'
  | 'rate_limited'
  | 'timeout'
  | 'network'
  | 'server'
  | 'bad_response'
  | 'storage';

const RETRYABLE: ReadonlySet<ApiErrorCode> = new Set(['rate_limited', 'timeout', 'network', 'server', 'bad_response', 'storage']);

interface ApiErrorOptions {
  /** Form field the server rejected, for example "serial". */
  field?: string;
  retryAfterSeconds?: number;
  status?: number;
}

/**
 * Error thrown by every function in src/api/.
 * `message` says what went wrong; `fix` tells the user how to fix it.
 */
export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly fix: string;
  readonly retryable: boolean;
  readonly field: string | undefined;
  readonly retryAfterSeconds: number | undefined;
  readonly status: number | undefined;

  constructor(code: ApiErrorCode, message: string, fix: string, options: ApiErrorOptions = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.fix = fix;
    this.retryable = RETRYABLE.has(code);
    this.field = options.field;
    this.retryAfterSeconds = options.retryAfterSeconds;
    this.status = options.status;
  }
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(
    'network',
    'Something unexpected went wrong while loading this information.',
    'Try again. If it keeps happening, reload the page.',
  );
}

export function networkError(what: string): ApiError {
  return new ApiError(
    'network',
    `We could not reach the WorthIT service to load ${what}.`,
    'Check your internet connection, then select Try again.',
  );
}

export function timeoutError(what: string): ApiError {
  return new ApiError(
    'timeout',
    `Loading ${what} took too long, so we stopped waiting.`,
    'The service may be busy. Select Try again in a moment.',
  );
}

export function badResponseError(what: string): ApiError {
  return new ApiError(
    'bad_response',
    `The WorthIT service sent back ${what} in a format this app does not understand.`,
    'Reload the page to get the latest version of the app, then try again.',
  );
}

import { afterEach, describe, expect, it, vi } from 'vitest';
import { MOCK_WATCHES } from './mockWatches';
import { ApiError } from './errors';
import { request } from './http';
import { parseSerialLookup } from './schema';
import { serialNotFoundError } from './serial';

const watch = MOCK_WATCHES[0];
const validBody = {
  watch,
  check: {
    serial: 'R7Q41188',
    found: true,
    productionYear: 2019,
    productionBatch: 'K412',
    authenticity: 'consistent',
    authenticityNote: 'Matches.',
    serviceHistory: [],
    stolenCheck: 'clear',
    checkedAt: '2026-11-24T10:00:00Z',
  },
};

function respond(status: number, body?: unknown, headers: Record<string, string> = {}) {
  const init = { status, headers: { 'Content-Type': 'application/json', ...headers } };
  const response = body === undefined ? new Response(null, init) : new Response(JSON.stringify(body), init);
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue(response);
}

function lookup() {
  return request('/serial-lookups', {
    method: 'POST',
    body: { serial: 'R7Q41188' },
    parse: parseSerialLookup,
    what: 'the serial number lookup',
    notFound: serialNotFoundError,
  });
}

async function failure(): Promise<ApiError> {
  try {
    await lookup();
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error('Expected the request to fail');
}

afterEach(() => {
  vi.useRealTimers();
});

describe('request: handling server responses', () => {
  it('returns validated data on 200 and sends JSON with the session cookie', async () => {
    const fetchSpy = respond(200, validBody);
    await expect(lookup()).resolves.toEqual(validBody);
    const [, init] = fetchSpy.mock.calls[0] ?? [];
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe(JSON.stringify({ serial: 'R7Q41188' }));
    expect(init?.credentials).toBe('include');
  });

  it('uses the specific not-found error on 404', async () => {
    respond(404, { error: { message: 'nope' } });
    const error = await failure();
    expect(error.code).toBe('not_found');
    expect(error.message).toBe('No watch in our records matches this serial number.');
    expect(error.retryable).toBe(false);
  });

  it('passes the server validation message and field on 422', async () => {
    respond(422, { error: { message: 'This serial format is not used by Rolex.', field: 'serial' } });
    const error = await failure();
    expect(error.code).toBe('invalid_request');
    expect(error.message).toBe('This serial format is not used by Rolex.');
    expect(error.field).toBe('serial');
  });

  it('tells the user how long to wait on 429', async () => {
    respond(429, undefined, { 'Retry-After': '30' });
    const error = await failure();
    expect(error.code).toBe('rate_limited');
    expect(error.fix).toBe('Wait 30 seconds, then select Try again.');
    expect(error.retryable).toBe(true);
  });

  it('asks the user to sign in on 401 and 403', async () => {
    respond(401);
    expect((await failure()).code).toBe('unauthorized');
  });

  it('explains server errors as retryable and not the user’s fault', async () => {
    respond(503, { message: 'upstream down' });
    const error = await failure();
    expect(error.code).toBe('server');
    expect(error.message).toContain('error 503');
    expect(error.fix).toMatch(/not caused by anything you did/);
    expect(error.retryable).toBe(true);
  });

  it('rejects a 200 response with the wrong shape', async () => {
    respond(200, { watch: { id: 1 } });
    expect((await failure()).code).toBe('bad_response');
  });

  it('rejects a 200 response that is not JSON', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('<html>', { status: 200 }));
    expect((await failure()).code).toBe('bad_response');
  });

  it('reports network failures', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    const error = await failure();
    expect(error.code).toBe('network');
    expect(error.fix).toMatch(/internet connection/);
  });

  it('gives up after the timeout', async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
        }),
    );
    const pending = request('/slow', { parse: (d) => d, what: 'the data', timeoutMs: 5000 }).catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(5000);
    const error = await pending;
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe('timeout');
  });
});

/**
 * API configuration.
 *
 * VITE_API_BASE_URL is PUBLIC configuration. Everything prefixed with VITE_ is
 * compiled into the browser bundle, so never put API keys, tokens or other
 * secrets in a VITE_ variable. Calls that need credentials (for example
 * manufacturer or stolen-watch registries) must go through the WorthIT backend.
 */

/** Empty string means "use the local mock implementation". */
export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '');

/** True while no backend is configured: the API modules use local mock data. */
export const USE_MOCK_API = API_BASE_URL === '';

/** Simulated network latency for the mock API. Zero in tests. */
export const MOCK_LATENCY_MS = import.meta.env.MODE === 'test' ? 0 : 350;

export type MockFailureArea = 'watches' | 'serial' | 'saved' | 'context';

/**
 * Development helper: add ?mockFail=watches (or serial, saved, context, or a
 * comma-separated list) to the URL to make that mock API area fail, so error
 * and retry states can be checked by hand. Has no effect in production builds.
 */
export function shouldSimulateFailure(area: MockFailureArea): boolean {
  if (!import.meta.env.DEV || typeof window === 'undefined') return false;
  const value = new URLSearchParams(window.location.search).get('mockFail');
  return value?.split(',').includes(area) ?? false;
}

export function wait(ms: number): Promise<void> {
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve) => setTimeout(resolve, ms));
}

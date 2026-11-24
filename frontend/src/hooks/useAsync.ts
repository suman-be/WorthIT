import { useCallback, useEffect, useState } from 'react';
import { type ApiError, toApiError } from '../api';

export type AsyncState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: ApiError };

interface Settled<T> {
  load: () => Promise<T>;
  attempt: number;
  state: AsyncState<T>;
}

/**
 * Run an async loader and track its state.
 *
 * Pass a memoised loader (useCallback). A new loader identity starts a new
 * request; `retry` re-runs the current one. Passing null means "idle".
 * Results from outdated requests are ignored.
 */
export function useAsync<T>(load: (() => Promise<T>) | null): AsyncState<T> & { retry: () => void } {
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);

  useEffect(() => {
    if (!load) return undefined;
    let active = true;
    load().then(
      (data) => {
        if (active) setSettled({ load, attempt, state: { status: 'success', data } });
      },
      (error: unknown) => {
        if (active) setSettled({ load, attempt, state: { status: 'error', error: toApiError(error) } });
      },
    );
    return () => {
      active = false;
    };
  }, [load, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  let state: AsyncState<T>;
  if (!load) state = { status: 'idle' };
  else if (settled && settled.load === load && settled.attempt === attempt) state = settled.state;
  else state = { status: 'loading' };

  return { ...state, retry };
}

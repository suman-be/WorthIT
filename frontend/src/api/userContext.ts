/**
 * User context (budget and holding period).
 *
 * Mock implementation stored in localStorage via ./storage.
 */
import type { UserContext } from '../types/watch';
import { MOCK_LATENCY_MS, shouldSimulateFailure, wait } from './config';
import { ApiError } from './errors';
import { readJson, writeJson } from './storage';

const KEY = 'worthit:user-context:v1';

export const DEFAULT_CONTEXT: UserContext = {
  budget: 6000,
  holding_period_years: 5,
};

function isUserContext(value: unknown): value is UserContext {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.budget === 'number' &&
    Number.isFinite(v.budget) &&
    v.budget > 0 &&
    typeof v.holding_period_years === 'number' &&
    Number.isInteger(v.holding_period_years) &&
    v.holding_period_years > 0
  );
}

export interface LoadedUserContext {
  context: UserContext;
  /** True when the user has not saved a context yet and defaults are used. */
  isDefault: boolean;
}

export async function getUserContext(): Promise<LoadedUserContext> {
  // TODO(backend): replace with GET `${API_BASE_URL}/me/context` -> 200 UserContext | 404
  await wait(MOCK_LATENCY_MS);
  if (shouldSimulateFailure('context')) {
    throw new ApiError(
      'storage',
      'We could not load your budget and holding period.',
      'Select Try again. If it keeps failing, check that your browser allows this site to store data.',
    );
  }
  const stored = readJson<UserContext | null>(KEY, (v): v is UserContext | null => v === null || isUserContext(v), null);
  return stored ? { context: stored, isDefault: false } : { context: { ...DEFAULT_CONTEXT }, isDefault: true };
}

export async function saveUserContext(context: UserContext): Promise<void> {
  // TODO(backend): replace with PUT `${API_BASE_URL}/me/context` { budget, holding_period_years } -> 204
  // Writes are synchronous for the mock so rapid edits are never lost or reordered.
  writeJson(KEY, context);
}

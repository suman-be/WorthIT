/**
 * Saved watches ("My watches").
 *
 * Mock implementation stored in localStorage via ./storage. Replace the
 * bodies with backend calls when user accounts exist.
 */
import type { SavedWatch } from '../types/watch';
import { MOCK_LATENCY_MS, shouldSimulateFailure, wait } from './config';
import { ApiError } from './errors';
import { readJson, writeJson } from './storage';

const KEY = 'worthit:saved-watches:v1';

function isSavedWatch(value: unknown): value is SavedWatch {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.watchId === 'string' &&
    typeof v.savedAt === 'string' &&
    (v.serial === undefined || typeof v.serial === 'string')
  );
}

function isSavedList(value: unknown): value is SavedWatch[] {
  return Array.isArray(value) && value.every(isSavedWatch);
}

function read(): SavedWatch[] {
  return readJson(KEY, isSavedList, []);
}

function failIfSimulated(): void {
  if (shouldSimulateFailure('saved')) {
    throw new ApiError(
      'storage',
      'We could not read your saved watches.',
      'Select Try again. If it keeps failing, check that your browser allows this site to store data.',
    );
  }
}

export async function listSavedWatches(): Promise<SavedWatch[]> {
  // TODO(backend): replace with GET `${API_BASE_URL}/me/saved-watches` -> 200 SavedWatch[]
  await wait(MOCK_LATENCY_MS);
  failIfSimulated();
  return read();
}

export async function getSavedWatch(watchId: string): Promise<SavedWatch | null> {
  // TODO(backend): replace with GET `${API_BASE_URL}/me/saved-watches/${watchId}` -> 200 | 404
  await wait(MOCK_LATENCY_MS);
  failIfSimulated();
  return read().find((s) => s.watchId === watchId) ?? null;
}

/** Save (or update) a watch. The serial is stored for the serial check only. */
export async function saveWatch(watchId: string, serial?: string): Promise<SavedWatch> {
  // TODO(backend): replace with PUT `${API_BASE_URL}/me/saved-watches/${watchId}` { serial }
  //   -> 200 SavedWatch. Serial numbers are personal data: the backend should store them
  //   encrypted and only for signed-in users.
  await wait(MOCK_LATENCY_MS);
  failIfSimulated();
  const list = read();
  const existing = list.find((s) => s.watchId === watchId);
  const entry: SavedWatch = {
    watchId,
    savedAt: existing?.savedAt ?? new Date().toISOString(),
    ...(serial ? { serial } : existing?.serial ? { serial: existing.serial } : {}),
  };
  writeJson(KEY, [...list.filter((s) => s.watchId !== watchId), entry]);
  return entry;
}

export async function removeSavedWatch(watchId: string): Promise<void> {
  // TODO(backend): replace with DELETE `${API_BASE_URL}/me/saved-watches/${watchId}` -> 204
  await wait(MOCK_LATENCY_MS);
  failIfSimulated();
  writeJson(
    KEY,
    read().filter((s) => s.watchId !== watchId),
  );
}

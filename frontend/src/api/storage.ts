/**
 * Safe wrapper around window.localStorage.
 *
 * Browsers can block storage (private mode, disabled cookies, sandboxed
 * iframes) or run out of quota. In those cases this module falls back to an
 * in-memory store so the app keeps working; data then lasts until the tab is
 * closed. Only modules inside src/api/ may import this file.
 */

const memory = new Map<string, string>();
let backend: Storage | null | undefined;
const listeners = new Set<() => void>();

function probe(): Storage | null {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return null;
    const storage = window.localStorage;
    const key = '__worthit_probe__';
    storage.setItem(key, key);
    storage.removeItem(key);
    return storage;
  } catch {
    return null;
  }
}

function getBackend(): Storage | null {
  if (backend === undefined) backend = probe();
  return backend;
}

function markUnavailable(): void {
  if (backend === null) return;
  backend = null;
  listeners.forEach((listener) => listener());
}

/** True when data will survive a page reload. */
export function isStoragePersistent(): boolean {
  return getBackend() !== null;
}

/** Subscribe to the moment storage becomes unavailable (for example, quota exceeded). */
export function subscribeToStorageStatus(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function readRaw(key: string): string | null {
  const storage = getBackend();
  if (storage) {
    try {
      return storage.getItem(key);
    } catch {
      markUnavailable();
    }
  }
  return memory.get(key) ?? null;
}

export function readJson<T>(key: string, isValid: (value: unknown) => value is T, fallback: T): T {
  const raw = readRaw(key);
  if (raw === null) return fallback;
  try {
    const parsed: unknown = JSON.parse(raw);
    return isValid(parsed) ? parsed : fallback;
  } catch {
    // Corrupt data: ignore it rather than crash.
    return fallback;
  }
}

export function writeJson(key: string, value: unknown): void {
  const raw = JSON.stringify(value);
  memory.set(key, raw);
  const storage = getBackend();
  if (!storage) return;
  try {
    storage.setItem(key, raw);
  } catch {
    // Quota exceeded or storage revoked. Keep the in-memory copy, carry on.
    markUnavailable();
  }
}

/** Test helper: forget the detected storage backend and the in-memory copy. */
export function resetStorageForTests(): void {
  backend = undefined;
  memory.clear();
}

/**
 * Watch catalogue API. Uses the backend when VITE_API_BASE_URL is set,
 * otherwise the mock catalogue in mockWatches.ts.
 */
import type { Watch } from '../types/watch';
import { MOCK_LATENCY_MS, USE_MOCK_API, shouldSimulateFailure, wait } from './config';
import { ApiError, networkError } from './errors';
import { request } from './http';
import { MOCK_WATCHES } from './mockWatches';
import { parseWatch, parseWatchList } from './schema';

function watchNotFoundError(): ApiError {
  return new ApiError(
    'not_found',
    'We could not find this watch. The link may be out of date or the watch may have been removed from the catalogue.',
    'Add the watch again using its serial number.',
  );
}

/** Fetch one watch by ID. Throws ApiError('not_found') when it does not exist. */
export async function getWatch(id: string): Promise<Watch> {
  if (!USE_MOCK_API) {
    // GET /watches/:id -> 200 Watch | 404
    return request(`/watches/${encodeURIComponent(id)}`, {
      parse: parseWatch,
      what: 'this watch',
      notFound: watchNotFoundError,
    });
  }
  await wait(MOCK_LATENCY_MS);
  if (shouldSimulateFailure('watches')) throw networkError('this watch');
  const watch = MOCK_WATCHES.find((w) => w.id === id);
  if (!watch) throw watchNotFoundError();
  return structuredClone(watch);
}

/** Fetch several watches by ID. Unknown IDs are skipped. */
export async function getWatches(ids: readonly string[]): Promise<Watch[]> {
  if (ids.length === 0) return [];
  if (!USE_MOCK_API) {
    // GET /watches?ids=a,b,c -> 200 Watch[]
    return request(`/watches?ids=${ids.map(encodeURIComponent).join(',')}`, {
      parse: parseWatchList,
      what: 'your watches',
    });
  }
  await wait(MOCK_LATENCY_MS);
  if (shouldSimulateFailure('watches')) throw networkError('your watches');
  return ids
    .map((id) => MOCK_WATCHES.find((w) => w.id === id))
    .filter((w): w is Watch => w !== undefined)
    .map((watch) => structuredClone(watch));
}

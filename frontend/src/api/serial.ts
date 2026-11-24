/**
 * Serial number lookup.
 *
 * One call identifies the watch model from the serial and returns the checks
 * for this specific physical watch. The model data is what the Worth Score is
 * calculated from; the serial checks (production year, batch, authenticity,
 * service history, stolen-watch status) are shown separately and NEVER passed
 * to the scoring engine.
 */
import type { SerialCheckResult, SerialLookupResult, ServiceRecord, Watch } from '../types/watch';
import { MOCK_LATENCY_MS, USE_MOCK_API, shouldSimulateFailure, wait } from './config';
import { ApiError, networkError } from './errors';
import { request } from './http';
import { MOCK_WATCHES } from './mockWatches';
import { parseSerialLookup } from './schema';

export function serialNotFoundError(): ApiError {
  return new ApiError(
    'not_found',
    'No watch in our records matches this serial number.',
    'Check the serial on the case back, between the lugs or on the warranty card, and enter it again. Letters O and I are rarely used in serials, so they may be the numbers 0 and 1.',
  );
}

/** Look up a serial number. Throws ApiError on every failure. */
export async function lookupSerial(serial: string): Promise<SerialLookupResult> {
  if (!USE_MOCK_API) {
    // POST /serial-lookups { serial } -> 200 { watch: Watch, check: SerialCheckResult } | 404 | 422 | 429
    // TODO(backend): the backend must query manufacturer databases and stolen-watch registries
    // server-side. Their API keys must never be sent to, or stored in, the frontend.
    return request('/serial-lookups', {
      method: 'POST',
      body: { serial },
      parse: parseSerialLookup,
      what: 'the serial number lookup',
      notFound: serialNotFoundError,
    });
  }
  return mockLookupSerial(serial);
}

// ---------------------------------------------------------------------------
// Mock implementation (used while VITE_API_BASE_URL is empty)
// ---------------------------------------------------------------------------

/**
 * Sample serials for trying the mock service. Any other valid serial maps to
 * one of the mock watches; serials starting with "0000" are not found and
 * serials ending in "99" are reported stolen.
 */
export const MOCK_SAMPLE_SERIALS: readonly { serial: string; note: string }[] = [
  { serial: 'R7Q41188', note: 'Rolex' },
  { serial: 'OM5512903', note: 'Omega' },
  { serial: 'TD58A2040', note: 'Tudor' },
  { serial: 'GS211X877', note: 'Grand Seiko' },
  { serial: 'CS0018K31', note: 'Cartier' },
  { serial: 'TD58A2099', note: 'Reported stolen' },
  { serial: '00004417', note: 'Not found' },
];

const SAMPLE_WATCH: Record<string, string> = {
  R7Q41188: 'rolex-submariner-124060',
  OM5512903: 'omega-speedmaster-310-30-42-50-01-001',
  TD58A2040: 'tudor-black-bay-58-m79030n',
  TD58A2099: 'tudor-black-bay-58-m79030n',
  GS211X877: 'grand-seiko-sbga211',
  CS0018K31: 'cartier-santos-wssa0018',
};

function hash(value: string): number {
  let h = 0;
  for (const char of value) h = (h * 31 + char.charCodeAt(0)) >>> 0;
  return h;
}

function mockWatchFor(serial: string): Watch {
  const id = SAMPLE_WATCH[serial];
  const watch = (id && MOCK_WATCHES.find((w) => w.id === id)) || MOCK_WATCHES[hash(serial) % MOCK_WATCHES.length];
  if (!watch) throw serialNotFoundError();
  return structuredClone(watch);
}

function mockCheck(serial: string): SerialCheckResult {
  const h = hash(serial);
  const productionYear = 2012 + (h % 12);
  const serviceHistory: ServiceRecord[] = [];
  if (h % 3 !== 0) {
    serviceHistory.push({
      date: `${productionYear + 5}-0${(h % 9) + 1}-15`,
      description: 'Full service: movement overhaul, new gaskets, water resistance test',
      servicedBy: 'Authorised service centre',
    });
  }
  if (h % 3 === 2 && productionYear + 9 <= new Date().getFullYear()) {
    serviceHistory.push({
      date: `${productionYear + 9}-1${h % 3}-02`,
      description: 'Partial service: regulation and crystal replacement',
      servicedBy: 'Independent watchmaker',
    });
  }
  return {
    serial,
    found: true,
    productionYear,
    productionBatch: `${String.fromCharCode(65 + (h % 26))}${(h % 900) + 100}`,
    authenticity: 'consistent',
    authenticityNote: 'The serial number format and production date match this model.',
    serviceHistory,
    stolenCheck: serial.endsWith('99') ? 'reported' : 'clear',
    checkedAt: new Date().toISOString(),
  };
}

async function mockLookupSerial(serial: string): Promise<SerialLookupResult> {
  await wait(MOCK_LATENCY_MS * 2);
  if (shouldSimulateFailure('serial')) throw networkError('the serial number lookup');
  if (serial.startsWith('0000')) throw serialNotFoundError();
  return { watch: mockWatchFor(serial), check: mockCheck(serial) };
}

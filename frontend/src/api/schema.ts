/**
 * Runtime validation of server responses. A response that does not match the
 * expected shape is rejected (and shown to the user as a "bad response" error)
 * instead of crashing a screen later.
 */
import type {
  AuthenticityStatus,
  CaseMaterial,
  Movement,
  SerialCheckResult,
  SerialLookupResult,
  ServiceRecord,
  StolenCheckStatus,
  Watch,
} from '../types/watch';

export class SchemaError extends Error {}

type Obj = Record<string, unknown>;

function obj(value: unknown, path: string): Obj {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new SchemaError(`${path} must be an object`);
  return value as Obj;
}

function str(o: Obj, key: string, path: string): string {
  const v = o[key];
  if (typeof v !== 'string') throw new SchemaError(`${path}.${key} must be a string`);
  return v;
}

function num(o: Obj, key: string, path: string): number {
  const v = o[key];
  if (typeof v !== 'number' || !Number.isFinite(v)) throw new SchemaError(`${path}.${key} must be a number`);
  return v;
}

function oneOf<T extends string>(o: Obj, key: string, allowed: readonly T[], path: string): T {
  const v = str(o, key, path);
  if (!(allowed as readonly string[]).includes(v)) throw new SchemaError(`${path}.${key} has an unknown value`);
  return v as T;
}

function nullable<T>(o: Obj, key: string, read: (o: Obj, key: string, path: string) => T, path: string): T | null {
  return o[key] === null || o[key] === undefined ? null : read(o, key, path);
}

const MOVEMENTS: readonly Movement[] = ['automatic', 'manual', 'quartz', 'spring-drive'];
const MATERIALS: readonly CaseMaterial[] = ['stainless-steel', 'titanium', 'ceramic', 'bronze', 'gold', 'platinum'];
const AUTHENTICITY: readonly AuthenticityStatus[] = ['consistent', 'inconsistent', 'unverified'];
const STOLEN: readonly StolenCheckStatus[] = ['clear', 'reported', 'unavailable'];

export function parseWatch(value: unknown, path = 'watch'): Watch {
  const o = obj(value, path);
  const specs = obj(o.specs, `${path}.specs`);
  const market = obj(o.market, `${path}.market`);
  const ownership = obj(o.ownership, `${path}.ownership`);
  return {
    id: str(o, 'id', path),
    brand: str(o, 'brand', path),
    model: str(o, 'model', path),
    reference: str(o, 'reference', path),
    specs: {
      movement: oneOf(specs, 'movement', MOVEMENTS, `${path}.specs`),
      case_mm: num(specs, 'case_mm', `${path}.specs`),
      material: oneOf(specs, 'material', MATERIALS, `${path}.specs`),
      water_resistance_m: num(specs, 'water_resistance_m', `${path}.specs`),
    },
    market: {
      price: num(market, 'price', `${path}.market`),
      resale_retention_pct: num(market, 'resale_retention_pct', `${path}.market`),
      popularity_trend: num(market, 'popularity_trend', `${path}.market`),
    },
    ownership: {
      service_interval_years: num(ownership, 'service_interval_years', `${path}.ownership`),
      service_cost: num(ownership, 'service_cost', `${path}.ownership`),
    },
  };
}

export function parseWatchList(value: unknown): Watch[] {
  if (!Array.isArray(value)) throw new SchemaError('watches must be an array');
  return value.map((w, i) => parseWatch(w, `watches[${i}]`));
}

function parseServiceRecord(value: unknown, path: string): ServiceRecord {
  const o = obj(value, path);
  return { date: str(o, 'date', path), description: str(o, 'description', path), servicedBy: str(o, 'servicedBy', path) };
}

export function parseSerialCheck(value: unknown, path = 'check'): SerialCheckResult {
  const o = obj(value, path);
  if (typeof o.found !== 'boolean') throw new SchemaError(`${path}.found must be a boolean`);
  if (!Array.isArray(o.serviceHistory)) throw new SchemaError(`${path}.serviceHistory must be an array`);
  return {
    serial: str(o, 'serial', path),
    found: o.found,
    productionYear: nullable(o, 'productionYear', num, path),
    productionBatch: nullable(o, 'productionBatch', str, path),
    authenticity: oneOf(o, 'authenticity', AUTHENTICITY, path),
    authenticityNote: str(o, 'authenticityNote', path),
    serviceHistory: o.serviceHistory.map((r, i) => parseServiceRecord(r, `${path}.serviceHistory[${i}]`)),
    stolenCheck: oneOf(o, 'stolenCheck', STOLEN, path),
    checkedAt: str(o, 'checkedAt', path),
  };
}

export function parseSerialLookup(value: unknown): SerialLookupResult {
  const o = obj(value, 'response');
  return { watch: parseWatch(o.watch), check: parseSerialCheck(o.check) };
}

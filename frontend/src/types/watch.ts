/**
 * Domain types for WorthIT.
 *
 * Note the deliberate separation: `Watch` describes a watch model (what the
 * Worth Score is calculated from). `SerialCheckResult` describes one specific
 * physical watch and lives in its own type so it can never be passed into the
 * scoring engine by accident.
 */

export type Movement = 'automatic' | 'manual' | 'quartz' | 'spring-drive';

export type CaseMaterial =
  | 'stainless-steel'
  | 'titanium'
  | 'ceramic'
  | 'bronze'
  | 'gold'
  | 'platinum';

export interface WatchSpecs {
  movement: Movement;
  case_mm: number;
  material: CaseMaterial;
  water_resistance_m: number;
}

export interface WatchMarket {
  /** Current retail or typical asking price, in euros. */
  price: number;
  /** Share of the price recovered when sold second-hand, in percent. Can exceed 100. */
  resale_retention_pct: number;
  /** Annual change in demand as a fraction, for example 0.12 for +12%. */
  popularity_trend: number;
}

export interface WatchOwnership {
  service_interval_years: number;
  /** Cost of one full service, in euros. */
  service_cost: number;
}

export interface Watch {
  id: string;
  brand: string;
  model: string;
  reference: string;
  specs: WatchSpecs;
  market: WatchMarket;
  ownership: WatchOwnership;
}

/** The user's personal situation. Shared across screens. */
export interface UserContext {
  /** Budget in euros. */
  budget: number;
  holding_period_years: number;
}

/** A watch the user has saved to "My watches". */
export interface SavedWatch {
  watchId: string;
  /** Optional serial number for the user's own physical watch. Never used for scoring. */
  serial?: string;
  savedAt: string;
}

export type AuthenticityStatus = 'consistent' | 'inconsistent' | 'unverified';
export type StolenCheckStatus = 'clear' | 'reported' | 'unavailable';

export interface ServiceRecord {
  date: string;
  description: string;
  servicedBy: string;
}

/** Result of looking up one physical watch by its serial number. */
export interface SerialCheckResult {
  serial: string;
  found: boolean;
  productionYear: number | null;
  productionBatch: string | null;
  authenticity: AuthenticityStatus;
  authenticityNote: string;
  serviceHistory: ServiceRecord[];
  stolenCheck: StolenCheckStatus;
  checkedAt: string;
}

/** Server response to a serial number lookup: the identified model plus the checks for this physical watch. */
export interface SerialLookupResult {
  watch: Watch;
  check: SerialCheckResult;
}

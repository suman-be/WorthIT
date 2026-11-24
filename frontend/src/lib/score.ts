/**
 * WorthIT scoring engine.
 *
 * Every function in this module is pure: the same input always produces the
 * same output, and nothing is read from or written to the outside world.
 *
 * SERIAL NUMBERS: the scoring input type (`ScorableWatch`) only contains the
 * specs, market and ownership data of a watch model, and `scoreWatch` copies
 * those fields explicitly. Serial number data cannot reach the calculation,
 * even if an object carrying extra serial fields is passed in.
 */
import type { UserContext, Watch, WatchMarket, WatchOwnership, WatchSpecs } from '../types/watch';

/** Weight of each scoring group. Must sum to exactly 1. */
export const WEIGHTS = {
  specs: 0.25,
  market: 0.3,
  ownership: 0.2,
  context: 0.25,
} as const;

export type GroupKey = keyof typeof WEIGHTS;

export const GROUP_ORDER: readonly GroupKey[] = ['specs', 'market', 'ownership', 'context'];

export const GROUP_META: Record<GroupKey, { label: string; focus: string }> = {
  specs: { label: 'Specs', focus: 'Utility' },
  market: { label: 'Market', focus: 'Value retention' },
  ownership: { label: 'Ownership', focus: 'True cost' },
  context: { label: 'Context', focus: 'Personal fit' },
};

/** A total score at or above `strong` is Strong, at or above `fair` is Fair, otherwise Weak. */
export const LABEL_THRESHOLDS = {
  strong: 70,
  fair: 45,
} as const;

export type WorthLabel = 'Strong' | 'Fair' | 'Weak';

/** Assumptions used for the resale estimate. */
export const VALUATION = {
  /** Share of the popularity trend that turns into a yearly price change. */
  trendPassThrough: 0.25,
  /** Trends outside this range are treated as this range, to avoid runaway estimates. */
  maxAbsoluteTrend: 0.5,
} as const;

/** The only watch data the scoring engine accepts. Serial data is not part of it. */
export type ScorableWatch = Pick<Watch, 'specs' | 'market' | 'ownership'>;

export interface GroupScore {
  key: GroupKey;
  label: string;
  focus: string;
  weight: number;
  /** Whole number from 0 to 100. */
  score: number;
  /** score × weight, the group's contribution to the Worth Score. */
  points: number;
  reason: string;
}

export interface CostOfOwnership {
  holdingPeriodYears: number;
  serviceCycles: number;
  serviceCostTotal: number;
  estimatedResaleValue: number;
  /** Purchase price minus estimated resale value. Negative when the watch is expected to gain value. */
  valueLost: number;
  /** (service cycles × service cost) + value lost. */
  totalCostOfOwnership: number;
}

export interface WorthResult extends CostOfOwnership {
  /** Whole number from 0 to 100. */
  total: number;
  label: WorthLabel;
  groups: GroupScore[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Clamp to a range. Non-finite numbers fall back to the minimum. */
export function clamp(value: number, min = 0, max = 100): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function finiteOr(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback;
}

const euro = new Intl.NumberFormat('en-IE', {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 0,
});

function formatEuro(value: number): string {
  return euro.format(Math.round(value));
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function years(value: number): string {
  return value === 1 ? '1 year' : `${value} years`;
}

// ---------------------------------------------------------------------------
// Specs (utility)
// ---------------------------------------------------------------------------

const MOVEMENT_POINTS: Record<WatchSpecs['movement'], number> = {
  'spring-drive': 90,
  automatic: 80,
  quartz: 75,
  manual: 70,
};

export const MOVEMENT_LABELS: Record<WatchSpecs['movement'], string> = {
  automatic: 'Automatic',
  manual: 'Hand-wound',
  quartz: 'Quartz',
  'spring-drive': 'Spring Drive',
};

const MATERIAL_POINTS: Record<WatchSpecs['material'], number> = {
  titanium: 90,
  'stainless-steel': 85,
  ceramic: 85,
  bronze: 65,
  gold: 60,
  platinum: 60,
};

export const MATERIAL_LABELS: Record<WatchSpecs['material'], string> = {
  'stainless-steel': 'stainless steel',
  titanium: 'titanium',
  ceramic: 'ceramic',
  bronze: 'bronze',
  gold: 'gold',
  platinum: 'platinum',
};

const IDEAL_CASE_MM = { min: 36, max: 42 } as const;

function caseSizePoints(caseMm: number): number {
  const size = finiteOr(caseMm, 0);
  const distance =
    size < IDEAL_CASE_MM.min ? IDEAL_CASE_MM.min - size : size > IDEAL_CASE_MM.max ? size - IDEAL_CASE_MM.max : 0;
  return clamp(100 - distance * 15);
}

function waterResistancePoints(metres: number): number {
  const m = finiteOr(metres, 0);
  if (m >= 300) return 100;
  if (m >= 200) return 90;
  if (m >= 100) return 80;
  if (m >= 50) return 55;
  if (m >= 30) return 35;
  return 15;
}

export function scoreSpecs(specs: WatchSpecs): { score: number; reason: string } {
  const factors = [
    { key: 'movement', points: MOVEMENT_POINTS[specs.movement] ?? 50 },
    { key: 'case', points: caseSizePoints(specs.case_mm) },
    { key: 'material', points: MATERIAL_POINTS[specs.material] ?? 50 },
    { key: 'water', points: waterResistancePoints(specs.water_resistance_m) },
  ] as const;

  const score = Math.round(clamp(factors.reduce((sum, f) => sum + f.points, 0) / factors.length));

  const movement = MOVEMENT_LABELS[specs.movement] ?? 'Unknown';
  const material = MATERIAL_LABELS[specs.material] ?? specs.material;
  const description = `${movement} movement, a ${specs.case_mm} mm ${material} case and ${specs.water_resistance_m} m water resistance`;

  const weakest = [...factors].sort((a, b) => a.points - b.points)[0];
  let weakNote = '';
  if (weakest && weakest.points < 60) {
    switch (weakest.key) {
      case 'case':
        weakNote =
          specs.case_mm < IDEAL_CASE_MM.min
            ? 'the case is smaller than the 36 to 42 mm that suits most wrists'
            : 'the case is larger than the 36 to 42 mm that suits most wrists';
        break;
      case 'water':
        weakNote = 'the water resistance is too low for swimming';
        break;
      case 'material':
        weakNote = `${material} scratches and dents more easily than steel`;
        break;
      case 'movement':
        weakNote = 'the movement type needs more care than most';
        break;
    }
  }

  let reason: string;
  if (!weakNote) {
    reason =
      score >= 75
        ? `${description} make it practical for everyday wear.`
        : `${description} give it average everyday utility.`;
  } else {
    reason =
      score >= 50
        ? `${description} are mostly practical, but ${weakNote}.`
        : `${description} limit everyday use, mainly because ${weakNote}.`;
  }

  return { score, reason };
}

// ---------------------------------------------------------------------------
// Market (value retention)
// ---------------------------------------------------------------------------

export function scoreMarket(market: WatchMarket): { score: number; reason: string } {
  const retention = finiteOr(market.resale_retention_pct, 0);
  const trend = finiteOr(market.popularity_trend, 0);

  // 40% retention or less scores 0, 100% or more scores 100.
  const retentionPoints = clamp(((retention - 40) / 60) * 100);
  // A trend of -30% a year scores 0, +30% a year scores 100.
  const trendPoints = clamp(((trend + 0.3) / 0.6) * 100);

  const score = Math.round(clamp(retentionPoints * 0.7 + trendPoints * 0.3));

  const trendPct = Math.round(Math.abs(trend) * 100);
  const demand =
    trendPct === 0 ? 'demand is steady' : trend > 0 ? `demand is rising ${trendPct}% a year` : `demand is falling ${trendPct}% a year`;

  const reason = `Second-hand prices hold at about ${Math.round(retention)}% of the purchase price and ${demand}.`;
  return { score, reason };
}

// ---------------------------------------------------------------------------
// Ownership (true cost)
// ---------------------------------------------------------------------------

export function scoreOwnership(ownership: WatchOwnership, price: number): { score: number; reason: string } {
  const interval = Math.max(finiteOr(ownership.service_interval_years, 0), 0);
  const cost = Math.max(finiteOr(ownership.service_cost, 0), 0);
  const safePrice = Math.max(finiteOr(price, 0), 1);

  const annualServiceCost = interval > 0 ? cost / interval : cost;
  const annualPctOfPrice = (annualServiceCost / safePrice) * 100;

  // 0% of the price per year scores 100, 5% or more scores 0.
  const costPoints = clamp(100 - (annualPctOfPrice / 5) * 100);
  // A 2-year interval or shorter scores 0, 10 years or longer scores 100.
  const intervalPoints = clamp(((interval - 2) / 8) * 100);

  const score = Math.round(clamp(costPoints * 0.6 + intervalPoints * 0.4));

  const reason =
    interval > 0
      ? `A service every ${years(interval)} at ${formatEuro(cost)} works out to about ${formatEuro(annualServiceCost)} a year, ${round1(annualPctOfPrice)}% of the price.`
      : `No service interval is known, so each ${formatEuro(cost)} service is counted as a yearly cost.`;

  return { score, reason };
}

// ---------------------------------------------------------------------------
// Resale value and total cost of ownership
// ---------------------------------------------------------------------------

/**
 * Estimated resale value after holding the watch for `holdingPeriodYears`.
 *
 *   price × (retention / 100) × (1 + trend × trendPassThrough) ^ years
 *
 * The result is rounded to whole euros and never negative.
 */
export function estimateResaleValue(market: WatchMarket, holdingPeriodYears: number): number {
  const price = Math.max(finiteOr(market.price, 0), 0);
  const retention = Math.max(finiteOr(market.resale_retention_pct, 0), 0) / 100;
  const trend = clamp(finiteOr(market.popularity_trend, 0), -VALUATION.maxAbsoluteTrend, VALUATION.maxAbsoluteTrend);
  const yearsHeld = Math.max(finiteOr(holdingPeriodYears, 0), 0);

  const annualDrift = 1 + trend * VALUATION.trendPassThrough;
  return Math.max(0, Math.round(price * retention * annualDrift ** yearsHeld));
}

/** Number of full services that fall within the holding period. */
export function countServiceCycles(serviceIntervalYears: number, holdingPeriodYears: number): number {
  const interval = finiteOr(serviceIntervalYears, 0);
  const yearsHeld = Math.max(finiteOr(holdingPeriodYears, 0), 0);
  if (interval <= 0) return 0;
  return Math.floor(yearsHeld / interval);
}

/**
 * Total cost of ownership over the holding period:
 *
 *   (service cycles × service cost) + value lost
 *
 * where value lost = purchase price − estimated resale value.
 */
export function calculateCostOfOwnership(watch: ScorableWatch, holdingPeriodYears: number): CostOfOwnership {
  const yearsHeld = Math.max(finiteOr(holdingPeriodYears, 0), 0);
  const serviceCycles = countServiceCycles(watch.ownership.service_interval_years, yearsHeld);
  const serviceCostTotal = serviceCycles * Math.max(finiteOr(watch.ownership.service_cost, 0), 0);
  const estimatedResaleValue = estimateResaleValue(watch.market, yearsHeld);
  const valueLost = Math.round(Math.max(finiteOr(watch.market.price, 0), 0) - estimatedResaleValue);

  return {
    holdingPeriodYears: yearsHeld,
    serviceCycles,
    serviceCostTotal,
    estimatedResaleValue,
    valueLost,
    totalCostOfOwnership: serviceCostTotal + valueLost,
  };
}

// ---------------------------------------------------------------------------
// Context (personal fit)
// ---------------------------------------------------------------------------

export function scoreContext(
  price: number,
  context: UserContext,
  cost: CostOfOwnership,
): { score: number; reason: string } {
  const budget = Math.max(finiteOr(context.budget, 0), 1);
  const yearsHeld = Math.max(finiteOr(context.holding_period_years, 0), 1);
  const safePrice = Math.max(finiteOr(price, 0), 0);
  const ratio = safePrice / budget;

  // Up to 80% of budget scores 100, exactly on budget scores 80, 50% over budget scores 0.
  let budgetPoints: number;
  if (ratio <= 0.8) budgetPoints = 100;
  else if (ratio <= 1) budgetPoints = 100 - ((ratio - 0.8) / 0.2) * 20;
  else budgetPoints = 80 - ((ratio - 1) / 0.5) * 80;
  budgetPoints = clamp(budgetPoints);

  // Yearly cost of ownership as a share of the budget: 0% scores 100, 10% or more scores 0.
  const annualCost = cost.totalCostOfOwnership / yearsHeld;
  const annualPctOfBudget = (annualCost / budget) * 100;
  const holdingPoints = clamp(100 - annualPctOfBudget * 10);

  const score = Math.round(clamp(budgetPoints * 0.6 + holdingPoints * 0.4));

  const budgetPart =
    ratio <= 1
      ? `The price is ${Math.round(ratio * 100)}% of your ${formatEuro(budget)} budget`
      : `The price is ${formatEuro(safePrice - budget)} over your ${formatEuro(budget)} budget`;
  const holdingPart =
    annualCost <= 0
      ? `it is expected to cover its own costs over ${years(yearsHeld)}`
      : `owning it for ${years(yearsHeld)} costs about ${formatEuro(annualCost)} a year`;

  return { score, reason: `${budgetPart}, and ${holdingPart}.` };
}

// ---------------------------------------------------------------------------
// Worth Score
// ---------------------------------------------------------------------------

export function getWorthLabel(total: number): WorthLabel {
  if (total >= LABEL_THRESHOLDS.strong) return 'Strong';
  if (total >= LABEL_THRESHOLDS.fair) return 'Fair';
  return 'Weak';
}

/** Weighted total of whole-number group scores, rounded and kept within 0 to 100. */
export function combineGroupScores(scores: Record<GroupKey, number>): number {
  const total = GROUP_ORDER.reduce((sum, key) => sum + clamp(scores[key]) * WEIGHTS[key], 0);
  return Math.round(clamp(total));
}

/**
 * Calculate the Worth Score for a watch in the user's context.
 *
 * Only `specs`, `market` and `ownership` are read from `watch`. Anything else
 * on the object, such as serial number data, is ignored.
 */
export function scoreWatch(watch: ScorableWatch, context: UserContext): WorthResult {
  // Copy only the fields the engine is allowed to use.
  const input: ScorableWatch = {
    specs: watch.specs,
    market: watch.market,
    ownership: watch.ownership,
  };

  const cost = calculateCostOfOwnership(input, context.holding_period_years);

  const raw: Record<GroupKey, { score: number; reason: string }> = {
    specs: scoreSpecs(input.specs),
    market: scoreMarket(input.market),
    ownership: scoreOwnership(input.ownership, input.market.price),
    context: scoreContext(input.market.price, context, cost),
  };

  const groups: GroupScore[] = GROUP_ORDER.map((key) => ({
    key,
    label: GROUP_META[key].label,
    focus: GROUP_META[key].focus,
    weight: WEIGHTS[key],
    score: raw[key].score,
    points: round1(raw[key].score * WEIGHTS[key]),
    reason: raw[key].reason,
  }));

  const total = combineGroupScores({
    specs: raw.specs.score,
    market: raw.market.score,
    ownership: raw.ownership.score,
    context: raw.context.score,
  });

  return {
    total,
    label: getWorthLabel(total),
    groups,
    ...cost,
  };
}

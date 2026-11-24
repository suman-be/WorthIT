import { describe, expect, it } from 'vitest';
import { MOCK_WATCHES } from '../api/mockWatches';
import { lookupSerial } from '../api/serial';
import type { UserContext } from '../types/watch';
import {
  GROUP_ORDER,
  LABEL_THRESHOLDS,
  type ScorableWatch,
  VALUATION,
  WEIGHTS,
  calculateCostOfOwnership,
  combineGroupScores,
  countServiceCycles,
  estimateResaleValue,
  getWorthLabel,
  scoreWatch,
} from './score';

/** The example watch from the product brief. */
const example: ScorableWatch = {
  specs: { movement: 'automatic', case_mm: 40, material: 'stainless-steel', water_resistance_m: 100 },
  market: { price: 5200, resale_retention_pct: 78, popularity_trend: 0.12 },
  ownership: { service_interval_years: 5, service_cost: 450 },
};
const exampleContext: UserContext = { budget: 6000, holding_period_years: 5 };

/** Small deterministic PRNG so the sweep is reproducible. */
function prng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}

describe('WEIGHTS', () => {
  it('sum to exactly 1', () => {
    const sum = GROUP_ORDER.reduce((total, key) => total + WEIGHTS[key], 0);
    expect(sum).toBe(1);
  });

  it('match the agreed weights for the four groups', () => {
    expect(WEIGHTS).toEqual({ specs: 0.25, market: 0.3, ownership: 0.2, context: 0.25 });
    expect(GROUP_ORDER).toEqual(['specs', 'market', 'ownership', 'context']);
  });

  it('are the weights reported on each group result', () => {
    const result = scoreWatch(example, exampleContext);
    for (const group of result.groups) expect(group.weight).toBe(WEIGHTS[group.key]);
  });
});

describe('Worth Score range', () => {
  it('is a whole number between 0 and 100 for every mock watch and a range of contexts', () => {
    for (const watch of MOCK_WATCHES) {
      for (const budget of [100, 1000, 6000, 20000, 1_000_000]) {
        for (const holding_period_years of [1, 3, 5, 10, 30]) {
          const { total, groups } = scoreWatch(watch, { budget, holding_period_years });
          expect(Number.isInteger(total)).toBe(true);
          expect(total).toBeGreaterThanOrEqual(0);
          expect(total).toBeLessThanOrEqual(100);
          for (const g of groups) {
            expect(g.score).toBeGreaterThanOrEqual(0);
            expect(g.score).toBeLessThanOrEqual(100);
          }
        }
      }
    }
  });

  it('stays within 0 to 100 for extreme and malformed input', () => {
    const random = prng(42);
    const pick = <T,>(values: T[]): T => values[Math.floor(random() * values.length)] as T;
    const wild = [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, -1e9, -1, 0, 1e9];

    for (let i = 0; i < 1000; i++) {
      const n = (scale: number) => (random() < 0.15 ? pick(wild) : (random() - 0.2) * scale);
      const watch: ScorableWatch = {
        specs: {
          movement: pick(['automatic', 'manual', 'quartz', 'spring-drive'] as const),
          case_mm: n(60),
          material: pick(['stainless-steel', 'titanium', 'ceramic', 'bronze', 'gold', 'platinum'] as const),
          water_resistance_m: n(1000),
        },
        market: { price: n(100000), resale_retention_pct: n(200), popularity_trend: n(2) },
        ownership: { service_interval_years: n(15), service_cost: n(5000) },
      };
      const { total } = scoreWatch(watch, { budget: n(50000), holding_period_years: n(40) });
      expect(Number.isFinite(total)).toBe(true);
      expect(total).toBeGreaterThanOrEqual(0);
      expect(total).toBeLessThanOrEqual(100);
    }
  });

  it('reaches 0 and 100 at the bounds of the combiner', () => {
    expect(combineGroupScores({ specs: 0, market: 0, ownership: 0, context: 0 })).toBe(0);
    expect(combineGroupScores({ specs: 100, market: 100, ownership: 100, context: 100 })).toBe(100);
    expect(combineGroupScores({ specs: 500, market: 500, ownership: 500, context: 500 })).toBe(100);
    expect(combineGroupScores({ specs: -50, market: -50, ownership: -50, context: -50 })).toBe(0);
  });

  it('equals the rounded weighted sum of the group scores', () => {
    const result = scoreWatch(example, exampleContext);
    const weighted = result.groups.reduce((sum, g) => sum + g.score * g.weight, 0);
    expect(result.total).toBe(Math.round(weighted));
  });

  it('gives every group a plain-language reason', () => {
    const result = scoreWatch(example, exampleContext);
    expect(result.groups).toHaveLength(4);
    for (const g of result.groups) {
      expect(g.reason.length).toBeGreaterThan(20);
      expect(g.reason.endsWith('.')).toBe(true);
    }
  });
});

describe('getWorthLabel', () => {
  it.each([
    [100, 'Strong'],
    [LABEL_THRESHOLDS.strong, 'Strong'],
    [LABEL_THRESHOLDS.strong - 1, 'Fair'],
    [LABEL_THRESHOLDS.fair, 'Fair'],
    [LABEL_THRESHOLDS.fair - 1, 'Weak'],
    [0, 'Weak'],
  ] as const)('labels %i as %s', (total, label) => {
    expect(getWorthLabel(total)).toBe(label);
  });

  it('uses 70 and 45 as the boundaries', () => {
    expect(LABEL_THRESHOLDS).toEqual({ strong: 70, fair: 45 });
  });

  it('is the label returned by scoreWatch', () => {
    for (const watch of MOCK_WATCHES) {
      const result = scoreWatch(watch, exampleContext);
      expect(result.label).toBe(getWorthLabel(result.total));
    }
  });
});

describe('estimateResaleValue', () => {
  it('applies retention and the dampened trend for each year held', () => {
    // 5200 × 0.78 × (1 + 0.12 × 0.25)^5 = 4701.94 → 4702
    expect(estimateResaleValue(example.market, 5)).toBe(4702);
    expect(VALUATION.trendPassThrough).toBe(0.25);
  });

  it('equals price × retention when the trend is flat or nothing is held', () => {
    expect(estimateResaleValue({ price: 10000, resale_retention_pct: 80, popularity_trend: 0 }, 7)).toBe(8000);
    expect(estimateResaleValue(example.market, 0)).toBe(4056);
  });

  it('falls with a negative trend', () => {
    // 10000 × 0.8 × (1 − 0.2 × 0.25)^2 = 8000 × 0.9025 = 7220
    expect(estimateResaleValue({ price: 10000, resale_retention_pct: 80, popularity_trend: -0.2 }, 2)).toBe(7220);
  });

  it('caps extreme trends', () => {
    const capped = estimateResaleValue({ price: 1000, resale_retention_pct: 100, popularity_trend: 5 }, 1);
    expect(capped).toBe(Math.round(1000 * (1 + VALUATION.maxAbsoluteTrend * VALUATION.trendPassThrough)));
  });

  it('is never negative', () => {
    expect(estimateResaleValue({ price: -500, resale_retention_pct: 80, popularity_trend: 0 }, 5)).toBe(0);
    expect(estimateResaleValue({ price: 500, resale_retention_pct: -80, popularity_trend: 0 }, 5)).toBe(0);
  });

  it('is what scoreWatch reports for the holding period', () => {
    expect(scoreWatch(example, exampleContext).estimatedResaleValue).toBe(4702);
    expect(scoreWatch(example, { ...exampleContext, holding_period_years: 10 }).estimatedResaleValue).toBe(
      estimateResaleValue(example.market, 10),
    );
  });
});

describe('total cost of ownership', () => {
  it('is (service cycles × service cost) + value lost', () => {
    const cost = calculateCostOfOwnership(example, 5);
    expect(cost.serviceCycles).toBe(1);
    expect(cost.serviceCostTotal).toBe(450);
    expect(cost.valueLost).toBe(5200 - 4702);
    expect(cost.totalCostOfOwnership).toBe(1 * 450 + (5200 - 4702));
    expect(cost.totalCostOfOwnership).toBe(948);
  });

  it('counts only full service cycles in the holding period', () => {
    expect(countServiceCycles(5, 4)).toBe(0);
    expect(countServiceCycles(5, 5)).toBe(1);
    expect(countServiceCycles(5, 14)).toBe(2);
    expect(countServiceCycles(4, 12)).toBe(3);
    expect(countServiceCycles(0, 10)).toBe(0);
    expect(countServiceCycles(-3, 10)).toBe(0);
  });

  it('uses the right number of cycles over a longer period', () => {
    const cost = calculateCostOfOwnership(example, 12);
    const resale = estimateResaleValue(example.market, 12);
    expect(cost.serviceCycles).toBe(2);
    expect(cost.totalCostOfOwnership).toBe(2 * 450 + (5200 - resale));
  });

  it('is reduced by value gained when the watch appreciates', () => {
    const appreciating: ScorableWatch = {
      ...example,
      market: { price: 10000, resale_retention_pct: 120, popularity_trend: 0 },
      ownership: { service_interval_years: 10, service_cost: 900 },
    };
    const cost = calculateCostOfOwnership(appreciating, 10);
    expect(cost.estimatedResaleValue).toBe(12000);
    expect(cost.valueLost).toBe(-2000);
    expect(cost.totalCostOfOwnership).toBe(900 - 2000);
  });

  it('is what scoreWatch reports', () => {
    const result = scoreWatch(example, exampleContext);
    expect(result.totalCostOfOwnership).toBe(948);
    expect(result.holdingPeriodYears).toBe(5);
  });
});

describe('serial numbers', () => {
  it('never change the Worth Score', async () => {
    const watch = MOCK_WATCHES[0];
    if (!watch) throw new Error('Mock data missing');
    const baseline = scoreWatch(watch, exampleContext);

    for (const serial of ['A1B2C3D4', 'TD58A2099', 'ZZ99', 'X9Y8Z7W6V5U4T3S2R1Q0']) {
      const { check } = await lookupSerial(serial);
      // Deliberately smuggle serial data onto the input object.
      const withSerial = { ...watch, serial, serialCheck: check } as ScorableWatch;
      expect(scoreWatch(withSerial, exampleContext)).toEqual(baseline);
    }
  });

  it('does not read serial fields even when they are present on nested objects', () => {
    const tampered = {
      ...example,
      market: { ...example.market, serial: 'STOLEN99' },
      specs: { ...example.specs, productionYear: 1950 },
    } as ScorableWatch;
    expect(scoreWatch(tampered, exampleContext).total).toBe(scoreWatch(example, exampleContext).total);
  });
});

/**
 * Pure form validation. Messages say what is wrong and how to fix it.
 */
import type { UserContext } from '../types/watch';

export type FieldErrors<K extends string> = Partial<Record<K, string>>;

// ---------------------------------------------------------------------------
// Add a watch (serial number)
// ---------------------------------------------------------------------------

export const SERIAL_PATTERN = /^[A-Z0-9]{4,20}$/;

/** Removes spaces and dashes and upper-cases, so "ab 12-cd" becomes "AB12CD". */
export function normaliseSerial(serial: string): string {
  return serial.replace(/[\s-]+/g, '').toUpperCase();
}

export function validateSerial(raw: string): { ok: true; value: string } | { ok: false; error: string } {
  const serial = normaliseSerial(raw);
  if (!serial) {
    return { ok: false, error: 'Enter the serial number. It is engraved on the case back, between the lugs or printed on the warranty card.' };
  }
  if (!SERIAL_PATTERN.test(serial)) {
    return {
      ok: false,
      error: 'Serial number must be 4 to 20 letters or numbers, with no symbols. Spaces and dashes are removed for you.',
    };
  }
  return { ok: true, value: serial };
}

// ---------------------------------------------------------------------------
// Preferences (budget and holding period)
// ---------------------------------------------------------------------------

export type ContextField = 'budget' | 'holding_period_years';

export interface ContextFormValues {
  budget: string;
  holding_period_years: string;
}

export const CONTEXT_LIMITS = {
  budgetMin: 100,
  budgetMax: 1_000_000,
  holdingMin: 1,
  holdingMax: 30,
} as const;

function parseNumber(raw: string): number | null {
  const trimmed = raw.trim().replace(/[\s,€]/g, '');
  if (trimmed === '') return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : NaN;
}

export function validateBudget(raw: string): string | undefined {
  const value = parseNumber(raw);
  if (value === null) return 'Enter your budget in euros, for example 6000.';
  if (Number.isNaN(value)) return 'Budget must be a number in euros, for example 6000.';
  if (value < CONTEXT_LIMITS.budgetMin || value > CONTEXT_LIMITS.budgetMax) {
    return `Budget must be between €${CONTEXT_LIMITS.budgetMin} and €${CONTEXT_LIMITS.budgetMax.toLocaleString('en-IE')}.`;
  }
  return undefined;
}

export function validateHoldingPeriod(raw: string): string | undefined {
  const value = parseNumber(raw);
  if (value === null) return 'Enter how many years you plan to keep the watch, for example 5.';
  if (Number.isNaN(value) || !Number.isInteger(value)) {
    return 'Holding period must be a whole number of years, for example 5.';
  }
  if (value < CONTEXT_LIMITS.holdingMin || value > CONTEXT_LIMITS.holdingMax) {
    return `Holding period must be between ${CONTEXT_LIMITS.holdingMin} and ${CONTEXT_LIMITS.holdingMax} years.`;
  }
  return undefined;
}

export function validateContext(values: ContextFormValues):
  | { ok: true; value: UserContext }
  | { ok: false; errors: FieldErrors<ContextField> } {
  const errors: FieldErrors<ContextField> = {};
  const budgetError = validateBudget(values.budget);
  const holdingError = validateHoldingPeriod(values.holding_period_years);
  if (budgetError) errors.budget = budgetError;
  if (holdingError) errors.holding_period_years = holdingError;

  if (budgetError || holdingError) return { ok: false, errors };

  return {
    ok: true,
    value: {
      budget: parseNumber(values.budget) ?? 0,
      holding_period_years: parseNumber(values.holding_period_years) ?? 0,
    },
  };
}

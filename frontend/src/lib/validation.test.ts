import { describe, expect, it } from 'vitest';
import { normaliseSerial, validateContext, validateSerial } from './validation';

describe('validateSerial', () => {
  it('asks for a serial when the field is empty', () => {
    const result = validateSerial('   ');
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toMatch(/^Enter the serial number\. It is engraved on the case back/);
  });

  it('normalises spaces, dashes and case', () => {
    expect(normaliseSerial(' ab 12-cd ')).toBe('AB12CD');
    expect(validateSerial('td58 a2040')).toEqual({ ok: true, value: 'TD58A2040' });
  });

  it('rejects symbols and the wrong length', () => {
    for (const serial of ['AB#12345', 'A1', 'A'.repeat(21)]) {
      const result = validateSerial(serial);
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.error).toMatch(/4 to 20 letters or numbers/);
    }
  });
});

describe('validateContext', () => {
  it('parses valid values', () => {
    expect(validateContext({ budget: '6000', holding_period_years: '5' })).toEqual({
      ok: true,
      value: { budget: 6000, holding_period_years: 5 },
    });
  });

  it('explains missing, out-of-range and fractional values', () => {
    const result = validateContext({ budget: '', holding_period_years: '2.5' });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.budget).toBe('Enter your budget in euros, for example 6000.');
      expect(result.errors.holding_period_years).toMatch(/whole number of years/);
    }
    const range = validateContext({ budget: '50', holding_period_years: '31' });
    expect(range.ok).toBe(false);
    if (!range.ok) {
      expect(range.errors.budget).toMatch(/between €100 and €1,000,000/);
      expect(range.errors.holding_period_years).toMatch(/between 1 and 30 years/);
    }
  });
});

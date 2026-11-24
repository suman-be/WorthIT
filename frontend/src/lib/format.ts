const euroFormatter = new Intl.NumberFormat('en-IE', {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 0,
});

export function formatEuro(value: number): string {
  return euroFormatter.format(Math.round(value));
}

export function formatPercent(value: number, fractionDigits = 0): string {
  return `${value.toFixed(fractionDigits)}%`;
}

/** Formats a fractional trend such as 0.12 as "+12%". */
export function formatTrend(fraction: number): string {
  const pct = Math.round(fraction * 100);
  if (pct === 0) return '0%';
  return `${pct > 0 ? '+' : '−'}${Math.abs(pct)}%`;
}

export function formatYears(value: number): string {
  return value === 1 ? '1 year' : `${value} years`;
}

export function formatWeight(weight: number): string {
  return `${Math.round(weight * 100)}%`;
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('en-IE', { year: 'numeric', month: 'long', day: 'numeric' }).format(date);
}

export function watchName(watch: { brand: string; model: string }): string {
  return `${watch.brand} ${watch.model}`;
}

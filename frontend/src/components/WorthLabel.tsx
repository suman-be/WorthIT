import type { WorthLabel as Label } from '../lib/score';

/** The word label. Colour supports it, but the word carries the meaning. */
export function WorthLabel({ label, size = 'normal' }: { label: Label; size?: 'normal' | 'large' }) {
  return <span className={`worth-label worth-label--${label.toLowerCase()} worth-label--${size}`}>{label}</span>;
}

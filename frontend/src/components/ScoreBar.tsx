/** Thin bar showing a 0 to 100 value. Decorative: always shown next to the number. */
export function ScoreBar({ value }: { value: number }) {
  const width = Math.min(100, Math.max(0, value));
  return (
    <span className="score-bar" aria-hidden="true">
      <span className="score-bar__fill" style={{ width: `${width}%` }} />
    </span>
  );
}

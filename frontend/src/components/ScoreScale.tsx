import { LABEL_THRESHOLDS } from '../lib/score';

/**
 * 0 to 100 scale with the Weak, Fair and Strong bands and a marker at the score.
 * Hidden from assistive technology: the number and word label carry the same information.
 */
export function ScoreScale({ value }: { value: number }) {
  const weak = LABEL_THRESHOLDS.fair;
  const fair = LABEL_THRESHOLDS.strong - LABEL_THRESHOLDS.fair;
  const strong = 100 - LABEL_THRESHOLDS.strong;
  const position = Math.min(100, Math.max(0, value));

  return (
    <div className="score-scale" aria-hidden="true">
      <div className="score-scale__track">
        <span className="score-scale__band score-scale__band--weak" style={{ width: `${weak}%` }} />
        <span className="score-scale__band score-scale__band--fair" style={{ width: `${fair}%` }} />
        <span className="score-scale__band score-scale__band--strong" style={{ width: `${strong}%` }} />
        <span className="score-scale__marker" style={{ left: `${position}%` }} />
      </div>
      <div className="score-scale__labels">
        <span style={{ width: `${weak}%` }}>Weak</span>
        <span style={{ width: `${fair}%` }}>Fair</span>
        <span style={{ width: `${strong}%` }}>Strong</span>
      </div>
    </div>
  );
}

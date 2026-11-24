import { LABEL_THRESHOLDS, type WorthResult } from '../lib/score';
import { formatEuro, formatYears } from '../lib/format';
import type { UserContext } from '../types/watch';
import { ScoreScale } from './ScoreScale';
import { WorthLabel } from './WorthLabel';

interface ScoreSummaryProps {
  result: WorthResult;
  context?: UserContext;
  size?: 'large' | 'medium';
}

/** The Worth Score, shown prominently with its word label and scale. */
export function ScoreSummary({ result, context, size = 'large' }: ScoreSummaryProps) {
  return (
    <div className={`score-summary score-summary--${size}`}>
      <p className="score-summary__caption">Worth Score</p>
      <div className="score-summary__row">
        <p className="score-summary__figure" data-testid="worth-score">
          <span className="visually-hidden">Worth Score: </span>
          <span className="score-summary__number">{result.total}</span>
          <span className="score-summary__unit" aria-hidden="true">
            /100
          </span>
          <span className="visually-hidden"> out of 100</span>
        </p>
        <WorthLabel label={result.label} size="large" />
      </div>
      <ScoreScale value={result.total} />
      <p className="visually-hidden">
        Strong is {LABEL_THRESHOLDS.strong} or more. Fair is {LABEL_THRESHOLDS.fair} to {LABEL_THRESHOLDS.strong - 1}. Weak
        is below {LABEL_THRESHOLDS.fair}.
      </p>
      {context && (
        <p className="score-summary__context">
          For a budget of <span className="num">{formatEuro(context.budget)}</span>, kept for{' '}
          <span className="num">{formatYears(context.holding_period_years)}</span>.
        </p>
      )}
    </div>
  );
}

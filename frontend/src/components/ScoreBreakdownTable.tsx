import type { WorthResult } from '../lib/score';
import { formatWeight } from '../lib/format';
import { ScoreBar } from './ScoreBar';

/** Semantic table of the four scoring groups. */
export function ScoreBreakdownTable({ result, watchName }: { result: WorthResult; watchName: string }) {
  const totalPoints = result.groups.reduce((sum, g) => sum + g.points, 0);

  return (
    <div className="table-wrap" role="region" aria-labelledby="breakdown-caption" tabIndex={0}>
      <table className="data-table breakdown-table">
        <caption id="breakdown-caption">
          How the Worth Score for {watchName} is made up. Each group score (out of 100) is multiplied by its weight; the
          points add up to the Worth Score.
        </caption>
        <thead>
          <tr>
            <th scope="col">Group</th>
            <th scope="col" className="num-col">
              Weight
            </th>
            <th scope="col" className="num-col">
              Score <span className="visually-hidden">(out of 100)</span>
            </th>
            <th scope="col" className="num-col">
              Points
            </th>
            <th scope="col">Why</th>
          </tr>
        </thead>
        <tbody>
          {result.groups.map((group) => (
            <tr key={group.key}>
              <th scope="row">
                {group.label}
                <span className="table-sub">{group.focus}</span>
              </th>
              <td className="num-col">{formatWeight(group.weight)}</td>
              <td className="num-col">
                <span className="score-cell">
                  <ScoreBar value={group.score} />
                  <span className="num-strong">{group.score}</span>
                </span>
              </td>
              <td className="num-col">{group.points.toFixed(1)}</td>
              <td className="reason">{group.reason}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Worth Score</th>
            <td className="num-col">100%</td>
            <td className="num-col" />
            <td className="num-col num-strong">{result.total}</td>
            <td className="reason">
              Sum of points ({totalPoints.toFixed(1)}), rounded.
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

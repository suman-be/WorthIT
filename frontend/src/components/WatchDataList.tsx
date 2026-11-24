import { MATERIAL_LABELS, MOVEMENT_LABELS } from '../lib/score';
import { formatEuro, formatPercent, formatTrend, formatYears } from '../lib/format';
import type { Watch } from '../types/watch';

/** The model data the Worth Score is calculated from. */
export function WatchDataList({ watch }: { watch: Watch }) {
  const rows: [string, string][] = [
    ['Movement', MOVEMENT_LABELS[watch.specs.movement]],
    ['Case size', `${watch.specs.case_mm} mm`],
    ['Case material', MATERIAL_LABELS[watch.specs.material]],
    ['Water resistance', `${watch.specs.water_resistance_m} m`],
    ['Price', formatEuro(watch.market.price)],
    ['Resale retention', formatPercent(watch.market.resale_retention_pct)],
    ['Popularity trend', `${formatTrend(watch.market.popularity_trend)} a year`],
    ['Service interval', formatYears(watch.ownership.service_interval_years)],
    ['Service cost', formatEuro(watch.ownership.service_cost)],
  ];
  return (
    <dl className="detail-list detail-list--columns">
      {rows.map(([term, value]) => (
        <div key={term}>
          <dt>{term}</dt>
          <dd className="num">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

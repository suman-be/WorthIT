import type { WorthResult } from '../lib/score';
import { formatEuro, formatYears } from '../lib/format';

function signedEuro(value: number): string {
  return value < 0 ? `−${formatEuro(Math.abs(value))}` : formatEuro(value);
}

interface CostSummaryProps {
  result: WorthResult;
  price: number;
  serviceCost: number;
  serviceIntervalYears: number;
}

/** How the total cost of ownership is calculated, line by line. */
export function CostSummary({ result, price, serviceCost, serviceIntervalYears }: CostSummaryProps) {
  const gains = result.valueLost < 0;

  return (
    <>
      <p className="formula">Total cost of ownership = (service cycles &times; service cost) + value lost</p>
      <dl className="ledger">
        <div>
          <dt>
            Servicing
            <span className="ledger__note">
              {result.serviceCycles} {result.serviceCycles === 1 ? 'service' : 'services'} &times; {formatEuro(serviceCost)},
              one every {formatYears(serviceIntervalYears)}
            </span>
          </dt>
          <dd className="num">{formatEuro(result.serviceCostTotal)}</dd>
        </div>
        <div>
          <dt>
            {gains ? 'Value gained' : 'Value lost'}
            <span className="ledger__note">
              {formatEuro(price)} paid &minus; {formatEuro(result.estimatedResaleValue)} estimated resale
            </span>
          </dt>
          <dd className="num">{signedEuro(result.valueLost)}</dd>
        </div>
        <div className="ledger__total">
          <dt>Total cost of ownership</dt>
          <dd className="num">{signedEuro(result.totalCostOfOwnership)}</dd>
        </div>
      </dl>
      {gains && <p className="muted">A negative total means the watch is expected to be worth more than it cost to own.</p>}
    </>
  );
}

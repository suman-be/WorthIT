import { formatDate } from '../lib/format';
import type { SerialCheckResult } from '../types/watch';

const AUTHENTICITY_TEXT: Record<SerialCheckResult['authenticity'], string> = {
  consistent: 'Consistent with this model',
  inconsistent: 'Does not match this model',
  unverified: 'Could not be verified',
};

const STOLEN_TEXT: Record<SerialCheckResult['stolenCheck'], string> = {
  clear: 'No theft report found',
  reported: 'Reported stolen',
  unavailable: 'Registry not available',
};

/** Prominent warning shown when the serial is on a stolen-watch register. */
export function StolenWarning({ check }: { check: SerialCheckResult }) {
  if (check.stolenCheck !== 'reported') return null;
  return (
    <div className="warning" role="alert">
      <p className="warning__title">Warning: this serial number has been reported stolen.</p>
      <p>Do not buy this watch. If you already own it, contact your local police with the serial number and proof of purchase.</p>
    </div>
  );
}

/** The key facts from a serial check, as a definition list. */
export function SerialFacts({ check, detailed = false }: { check: SerialCheckResult; detailed?: boolean }) {
  const records = check.serviceHistory.length;
  return (
    <dl className="facts">
      <div className="facts__item">
        <dt>Authenticity</dt>
        <dd>{AUTHENTICITY_TEXT[check.authenticity]}</dd>
      </div>
      <div className={`facts__item${check.stolenCheck === 'reported' ? ' facts__item--alert' : ''}`}>
        <dt>Stolen-watch check</dt>
        <dd>{STOLEN_TEXT[check.stolenCheck]}</dd>
      </div>
      <div className="facts__item">
        <dt>Production year</dt>
        <dd className="num">{check.productionYear ?? 'Unknown'}</dd>
      </div>
      <div className="facts__item">
        <dt>{detailed ? 'Production batch' : 'Service records'}</dt>
        <dd className="num">
          {detailed ? (check.productionBatch ?? 'Unknown') : records === 0 ? 'None found' : `${records} found`}
        </dd>
      </div>
      {detailed && (
        <>
          <div className="facts__item facts__item--wide">
            <dt>Authenticity note</dt>
            <dd>{check.authenticityNote}</dd>
          </div>
          <div className="facts__item">
            <dt>Checked</dt>
            <dd>{formatDate(check.checkedAt)}</dd>
          </div>
        </>
      )}
    </dl>
  );
}

import { useCallback } from 'react';
import { serialApi, USE_MOCK_API } from '../api';
import { useAsync } from '../hooks/useAsync';
import { formatDate, watchName } from '../lib/format';
import { SerialFacts, StolenWarning } from './SerialFacts';
import { StatusView } from './StatusView';

interface SerialCheckSectionProps {
  serial: string;
  watchId: string;
}

/**
 * Serial number check, in its own section. Nothing from here is used by the
 * Worth Score: this component never receives or returns score data.
 */
export function SerialCheckSection({ serial, watchId }: SerialCheckSectionProps) {
  const load = useCallback(() => serialApi.lookupSerial(serial), [serial]);
  const state = useAsync(load);

  return (
    <section aria-labelledby="serial-heading" className="panel-section">
      <h2 id="serial-heading">Serial number check</h2>
      <p className="muted">
        About your specific watch, serial <span className="serial">{serial}</span>. For information only. It does not
        affect the Worth Score.
      </p>
      {state.status === 'loading' && <StatusView kind="loading" title="Checking the serial number" />}
      {state.status === 'error' && (
        <StatusView
          kind="error"
          headingLevel={3}
          title={state.error.code === 'not_found' ? 'Serial number not found' : 'Serial number check failed'}
          message={state.error.message}
          fix={state.error.fix}
          {...(state.error.retryable ? { onRetry: state.retry } : {})}
        />
      )}
      {state.status === 'success' && (
        <>
          {state.data.watch.id !== watchId && (
            <div className="warning" role="alert">
              <p className="warning__title">This serial number belongs to a {watchName(state.data.watch)}.</p>
              <p>It does not match the watch on this page. Check that you entered the serial correctly.</p>
            </div>
          )}
          <StolenWarning check={state.data.check} />
          <SerialFacts check={state.data.check} detailed />
          <h3>Service history</h3>
          {state.data.check.serviceHistory.length === 0 ? (
            <p>No service records were found for this serial number.</p>
          ) : (
            <ol className="timeline">
              {state.data.check.serviceHistory.map((record) => (
                <li key={`${record.date}-${record.description}`}>
                  <span className="timeline__date num">{formatDate(record.date)}</span>
                  <span>
                    {record.description}. {record.servicedBy}.
                  </span>
                </li>
              ))}
            </ol>
          )}
          {USE_MOCK_API && <p className="muted small">Sample data: the serial lookup service is not connected yet.</p>}
        </>
      )}
    </section>
  );
}

import { useCallback, useMemo } from 'react';
import { Link, useLocation } from 'react-router';
import { savedWatchesApi, watchesApi } from '../api';
import { ContextForm } from '../components/ContextForm';
import { CostSummary } from '../components/CostSummary';
import { LiveAnnouncer } from '../components/LiveAnnouncer';
import { SaveWatchButton } from '../components/SaveWatchButton';
import { ScoreBreakdownTable } from '../components/ScoreBreakdownTable';
import { ScoreSummary } from '../components/ScoreSummary';
import { SerialCheckSection } from '../components/SerialCheckSection';
import { StatusView } from '../components/StatusView';
import { WatchDataList } from '../components/WatchDataList';
import { useUserContext } from '../context/UserContextProvider';
import { useAsync } from '../hooks/useAsync';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { formatEuro, formatYears, watchName } from '../lib/format';
import { scoreWatch } from '../lib/score';
import type { UserContext, Watch } from '../types/watch';
import { readSerialState } from './AddWatchPage';

function signedEuro(value: number): string {
  return value < 0 ? `−${formatEuro(Math.abs(value))}` : formatEuro(value);
}

function WatchDetail({ watch, context, serial }: { watch: Watch; context: UserContext; serial: string | undefined }) {
  // Only the watch model and the user's preferences go into the score. The serial never does.
  const result = useMemo(() => scoreWatch(watch, context), [watch, context]);
  const period = formatYears(result.holdingPeriodYears);

  return (
    <div className="detail">
      <LiveAnnouncer message={`Worth Score ${result.total} out of 100, ${result.label}.`} />

      <div className="detail__aside">
        <section aria-labelledby="score-heading" className="score-panel">
          <h2 id="score-heading" className="visually-hidden">
            Worth Score
          </h2>
          <ScoreSummary result={result} />
          <dl className="figures">
            <div>
              <dt>Resale value after {period}</dt>
              <dd className="num" data-testid="resale-value">
                {formatEuro(result.estimatedResaleValue)}
              </dd>
            </div>
            <div>
              <dt>Total cost over {period}</dt>
              <dd className="num" data-testid="total-cost">
                {signedEuro(result.totalCostOfOwnership)}
              </dd>
            </div>
            <div>
              <dt>Price</dt>
              <dd className="num">{formatEuro(watch.market.price)}</dd>
            </div>
          </dl>
          <SaveWatchButton watch={watch} serial={serial} />
        </section>

        <section aria-labelledby="prefs-heading" className="score-panel score-panel--quiet">
          <h2 id="prefs-heading" className="panel-title">
            Your preferences
          </h2>
          <ContextForm idPrefix="detail" summaryHeadingLevel={3} initial={context} compact />
        </section>
      </div>

      <div className="detail__main">
        <section aria-labelledby="breakdown-heading" className="panel-section">
          <h2 id="breakdown-heading">Score breakdown</h2>
          <ScoreBreakdownTable result={result} watchName={watchName(watch)} />
        </section>

        <section aria-labelledby="cost-heading" className="panel-section">
          <h2 id="cost-heading">Cost of ownership over {period}</h2>
          <CostSummary
            result={result}
            price={watch.market.price}
            serviceCost={watch.ownership.service_cost}
            serviceIntervalYears={watch.ownership.service_interval_years}
          />
        </section>

        <section aria-labelledby="data-heading" className="panel-section">
          <h2 id="data-heading">Model data</h2>
          <WatchDataList watch={watch} />
        </section>

        {serial && <SerialCheckSection serial={serial} watchId={watch.id} />}
      </div>
    </div>
  );
}

export function WatchDetailPage({ watchId }: { watchId: string }) {
  const location = useLocation();
  const userContext = useUserContext();

  const loadWatch = useCallback(() => watchesApi.getWatch(watchId), [watchId]);
  const watchState = useAsync(loadWatch);
  const loadSaved = useCallback(() => savedWatchesApi.getSavedWatch(watchId).catch(() => null), [watchId]);
  const savedState = useAsync(loadSaved);

  const savedSerial = savedState.status === 'success' ? savedState.data?.serial : undefined;
  const serial = readSerialState(location.state) || savedSerial;

  const title = watchState.status === 'success' ? watchName(watchState.data) : 'Watch details';
  useDocumentTitle(title);

  let body;
  if (watchState.status === 'loading' || watchState.status === 'idle' || userContext.status === 'loading') {
    body = <StatusView kind="loading" title="Loading watch details" />;
  } else if (watchState.status === 'error') {
    const notFound = watchState.error.code === 'not_found';
    body = (
      <StatusView
        kind="error"
        title={notFound ? 'Watch not found' : 'Watch details could not be loaded'}
        message={watchState.error.message}
        fix={watchState.error.fix}
        {...(watchState.error.retryable ? { onRetry: watchState.retry } : {})}
        action={<Link to="/">Add a watch by serial number</Link>}
      />
    );
  } else if (userContext.status === 'error' || !userContext.context) {
    body = (
      <StatusView
        kind="error"
        title="Your preferences could not be loaded"
        message={userContext.error?.message ?? 'Your budget and holding period are needed to calculate the Worth Score.'}
        fix={userContext.error?.fix}
        onRetry={userContext.retry}
      />
    );
  } else {
    body = <WatchDetail watch={watchState.data} context={userContext.context} serial={serial} />;
  }

  return (
    <>
      <div className="page-head">
        <h1 tabIndex={-1}>{title}</h1>
        {watchState.status === 'success' && (
          <p className="page-head__meta">
            {watchState.data.brand} &middot; Reference <span className="num">{watchState.data.reference}</span>
          </p>
        )}
      </div>
      {body}
    </>
  );
}

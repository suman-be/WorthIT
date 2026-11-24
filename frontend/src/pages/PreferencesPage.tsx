import { Link } from 'react-router';
import { savedWatchesApi, watchesApi } from '../api';
import { ContextForm } from '../components/ContextForm';
import { LiveAnnouncer } from '../components/LiveAnnouncer';
import { ScoreBar } from '../components/ScoreBar';
import { StatusView } from '../components/StatusView';
import { WorthLabel } from '../components/WorthLabel';
import { useUserContext } from '../context/UserContextProvider';
import { useAsync } from '../hooks/useAsync';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { formatEuro, formatYears, watchName } from '../lib/format';
import { scoreWatch } from '../lib/score';
import type { UserContext, Watch } from '../types/watch';

async function loadSavedWatches(): Promise<Watch[]> {
  const saved = await savedWatchesApi.listSavedWatches();
  return watchesApi.getWatches(saved.map((s) => s.watchId));
}

function signedEuro(value: number): string {
  return value < 0 ? `−${formatEuro(Math.abs(value))}` : formatEuro(value);
}

function SavedScores({ context }: { context: UserContext }) {
  const state = useAsync(loadSavedWatches);

  if (state.status === 'loading' || state.status === 'idle') {
    return <StatusView kind="loading" title="Loading your saved watches" />;
  }
  if (state.status === 'error') {
    return (
      <StatusView
        kind="error"
        title="Saved watches could not be loaded"
        message={state.error.message}
        fix={state.error.fix}
        {...(state.error.retryable ? { onRetry: state.retry } : {})}
      />
    );
  }
  if (state.data.length === 0) {
    return (
      <StatusView
        kind="empty"
        title="No saved watches yet"
        message={<p>Save a watch to see here how your budget and holding period change its Worth Score.</p>}
        action={<Link to="/">Add a watch</Link>}
      />
    );
  }

  const scored = state.data.map((watch) => ({ watch, result: scoreWatch(watch, context) }));
  const announcement = `Worth Scores updated. ${scored
    .map(({ watch, result }) => `${watchName(watch)}: ${result.total}, ${result.label}.`)
    .join(' ')}`;

  return (
    <>
      <LiveAnnouncer message={announcement} />
      <h2>Effect on your saved watches</h2>
      <ul className="impact" data-testid="context-scores">
        {scored.map(({ watch, result }) => (
          <li key={watch.id} className="impact__item">
            <div className="impact__head">
              <h3 className="impact__name">
                <Link to={`/watches/${watch.id}`}>{watchName(watch)}</Link>
              </h3>
              <p className="impact__score">
                <span className="num">{result.total}</span>
                <span className="visually-hidden"> out of 100, </span>
                <WorthLabel label={result.label} />
              </p>
            </div>
            <ScoreBar value={result.total} />
            <p className="impact__meta">
              <span>
                Resale after {formatYears(context.holding_period_years)}{' '}
                <span className="num">{formatEuro(result.estimatedResaleValue)}</span>
              </span>
              <span>
                Total cost <span className="num">{signedEuro(result.totalCostOfOwnership)}</span>
              </span>
            </p>
          </li>
        ))}
      </ul>
    </>
  );
}

export function PreferencesPage() {
  useDocumentTitle('Preferences');
  const { status, context, isDefault, error, retry } = useUserContext();

  return (
    <div className="split">
      <div className="split__primary">
        <h1 tabIndex={-1}>Preferences</h1>
        <p className="lead">
          Your budget and how long you plan to keep a watch set its Context score and its total cost of ownership.
        </p>

        {status === 'loading' && <StatusView kind="loading" title="Loading your preferences" />}
        {status === 'error' && (
          <StatusView
            kind="error"
            title="Your preferences could not be loaded"
            message={error?.message ?? 'Something went wrong.'}
            fix={error?.fix}
            onRetry={retry}
          />
        )}
        {status === 'ready' && context && (
          <>
            {isDefault && (
              <div className="notice">
                <p>These are default values. Change them to match your situation.</p>
              </div>
            )}
            <ContextForm idPrefix="preferences" initial={context} />
          </>
        )}
      </div>

      <section className="split__secondary" aria-label="Effect on your saved watches">
        {status === 'ready' && context && <SavedScores context={context} />}
      </section>
    </div>
  );
}

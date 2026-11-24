import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router';
import { savedWatchesApi, toApiError, watchesApi } from '../api';
import { ErrorSummary } from '../components/ErrorSummary';
import { ScoreBar } from '../components/ScoreBar';
import { StatusView } from '../components/StatusView';
import { WorthLabel } from '../components/WorthLabel';
import { useUserContext } from '../context/UserContextProvider';
import { useAsync } from '../hooks/useAsync';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { formatEuro, formatPercent, formatTrend, formatYears, watchName } from '../lib/format';
import { GROUP_META, GROUP_ORDER, MATERIAL_LABELS, MOVEMENT_LABELS, scoreWatch, type WorthResult } from '../lib/score';
import type { SavedWatch, UserContext, Watch } from '../types/watch';

const MIN_COMPARE = 2;
const MAX_COMPARE = 3;
const FIRST_CHECKBOX_ID = 'compare-first';

interface SavedItem {
  saved: SavedWatch;
  watch: Watch;
}

interface ScoredItem extends SavedItem {
  result: WorthResult;
}

async function loadMyWatches(): Promise<SavedItem[]> {
  const saved = await savedWatchesApi.listSavedWatches();
  const watches = await watchesApi.getWatches(saved.map((s) => s.watchId));
  return saved
    .map((entry) => ({ saved: entry, watch: watches.find((w) => w.id === entry.watchId) }))
    .filter((item): item is SavedItem => item.watch !== undefined);
}

function signedEuro(value: number): string {
  return value < 0 ? `−${formatEuro(Math.abs(value))}` : formatEuro(value);
}

function ComparisonTable({ items, context }: { items: ScoredItem[]; context: UserContext }) {
  const period = formatYears(context.holding_period_years);
  const rows: { label: string; cell: (item: ScoredItem) => ReactNode }[] = [
    {
      label: 'Worth Score (out of 100)',
      cell: ({ result }) => (
        <span className="compare-score">
          <span className="num num-strong">{result.total}</span> <WorthLabel label={result.label} />
        </span>
      ),
    },
    ...GROUP_ORDER.map((key) => ({
      label: `${GROUP_META[key].label} score`,
      cell: ({ result }: ScoredItem) => {
        const score = result.groups.find((g) => g.key === key)?.score ?? 0;
        return (
          <span className="score-cell">
            <ScoreBar value={score} />
            <span className="num">{score}</span>
          </span>
        );
      },
    })),
    { label: 'Price', cell: ({ watch }) => formatEuro(watch.market.price) },
    { label: `Resale value after ${period}`, cell: ({ result }) => formatEuro(result.estimatedResaleValue) },
    { label: `Total cost over ${period}`, cell: ({ result }) => signedEuro(result.totalCostOfOwnership) },
    { label: 'Resale retention', cell: ({ watch }) => formatPercent(watch.market.resale_retention_pct) },
    { label: 'Popularity trend (a year)', cell: ({ watch }) => formatTrend(watch.market.popularity_trend) },
    { label: 'Movement', cell: ({ watch }) => MOVEMENT_LABELS[watch.specs.movement] },
    { label: 'Case', cell: ({ watch }) => `${watch.specs.case_mm} mm ${MATERIAL_LABELS[watch.specs.material]}` },
    { label: 'Water resistance', cell: ({ watch }) => `${watch.specs.water_resistance_m} m` },
    {
      label: 'Servicing',
      cell: ({ watch }) =>
        `${formatEuro(watch.ownership.service_cost)} every ${formatYears(watch.ownership.service_interval_years)}`,
    },
  ];

  return (
    <div className="table-wrap" role="region" aria-labelledby="comparison-caption" tabIndex={0}>
      <table className="data-table comparison-table">
        <caption id="comparison-caption">
          Comparison of {items.length} watches for a budget of {formatEuro(context.budget)}, kept for {period}
        </caption>
        <thead>
          <tr>
            <td />
            {items.map(({ watch }) => (
              <th key={watch.id} scope="col">
                {watchName(watch)}
                <span className="table-sub num">{watch.reference}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.label}</th>
              {items.map((item) => (
                <td key={item.watch.id} className="num">
                  {row.cell(item)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SavedList({
  items,
  context,
  onRemoved,
}: {
  items: SavedItem[];
  context: UserContext;
  onRemoved: (watchId: string, name: string) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [compared, setCompared] = useState<string[]>([]);
  const [selectionError, setSelectionError] = useState<string | undefined>();
  const [submitCount, setSubmitCount] = useState(0);
  const [removeError, setRemoveError] = useState<string | undefined>();
  const comparisonHeading = useRef<HTMLHeadingElement>(null);
  const [focusComparison, setFocusComparison] = useState(0);

  const scored: ScoredItem[] = items.map((item) => ({ ...item, result: scoreWatch(item.watch, context) }));
  const ids = new Set(items.map((i) => i.watch.id));
  const activeSelected = selected.filter((id) => ids.has(id));
  const comparedItems = compared
    .filter((id) => ids.has(id))
    .map((id) => scored.find((s) => s.watch.id === id))
    .filter((s): s is ScoredItem => s !== undefined);
  const period = formatYears(context.holding_period_years);

  useEffect(() => {
    if (focusComparison > 0) comparisonHeading.current?.focus();
  }, [focusComparison]);

  function toggle(watchId: string, checked: boolean) {
    const next = checked ? [...selected, watchId] : selected.filter((id) => id !== watchId);
    setSelected(next);
    if (selectionError && next.length >= MIN_COMPARE && next.length <= MAX_COMPARE) setSelectionError(undefined);
  }

  function handleCompare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitCount((n) => n + 1);
    const count = activeSelected.length;
    if (count < MIN_COMPARE) {
      setSelectionError(
        count === 0
          ? 'Select two or three watches to compare. You have not selected any.'
          : 'Select at least one more watch. You need two or three watches to compare.',
      );
      return;
    }
    if (count > MAX_COMPARE) {
      setSelectionError(`Select no more than three watches. You have selected ${count}; clear ${count - MAX_COMPARE}.`);
      return;
    }
    setSelectionError(undefined);
    setCompared(activeSelected);
    setFocusComparison((n) => n + 1);
  }

  async function remove(watchId: string, name: string) {
    setRemoveError(undefined);
    try {
      await savedWatchesApi.removeSavedWatch(watchId);
      setSelected((s) => s.filter((id) => id !== watchId));
      onRemoved(watchId, name);
    } catch (error) {
      const apiError = toApiError(error);
      setRemoveError(`${name} could not be removed. ${apiError.message} ${apiError.fix}`);
    }
  }

  const canCompare = items.length >= MIN_COMPARE;
  const errorId = `${FIRST_CHECKBOX_ID}-error`;

  return (
    <>
      {removeError && (
        <p className="inline-error" role="alert">
          {removeError}
        </p>
      )}
      <form noValidate onSubmit={handleCompare}>
        <ErrorSummary
          title="The comparison could not be shown"
          errors={selectionError ? [{ fieldId: FIRST_CHECKBOX_ID, message: selectionError }] : []}
          focusKey={submitCount}
        />
        <fieldset
          className={`fieldset${selectionError ? ' field--error' : ''}`}
          aria-describedby={selectionError ? `compare-hint ${errorId}` : 'compare-hint'}
        >
          <legend className="visually-hidden">Saved watches</legend>
          <div className="list-toolbar">
            <p id="compare-hint" className="list-toolbar__hint">
              {canCompare
                ? 'Select two or three watches to compare them side by side.'
                : 'Save at least two watches to compare them side by side.'}
            </p>
            {canCompare && (
              <div className="list-toolbar__actions">
                <span className="muted num" aria-hidden="true">
                  {activeSelected.length} of {MAX_COMPARE} selected
                </span>
                <button type="submit" className="button">
                  Compare selected
                </button>
              </div>
            )}
          </div>
          {selectionError && (
            <p id={errorId} className="field__error">
              <span className="visually-hidden">Error: </span>
              {selectionError}
            </p>
          )}
          <ul className="rows">
            {scored.map(({ watch, saved, result }, index) => {
              const name = watchName(watch);
              const checkboxId = index === 0 ? FIRST_CHECKBOX_ID : `compare-${watch.id}`;
              return (
                <li key={watch.id} className="row">
                  <div className="row__watch">
                    {canCompare ? (
                      <label className="checkbox" htmlFor={checkboxId}>
                        <input
                          id={checkboxId}
                          type="checkbox"
                          name="compare"
                          value={watch.id}
                          checked={selected.includes(watch.id)}
                          aria-invalid={selectionError ? true : undefined}
                          onChange={(e) => toggle(watch.id, e.target.checked)}
                        />
                        <span className="checkbox__label">{name}</span>
                      </label>
                    ) : (
                      <p className="row__name">{name}</p>
                    )}
                    <p className="row__meta">
                      <span className="num">{watch.reference}</span>
                      {saved.serial && (
                        <span>
                          Serial <span className="serial">{saved.serial}</span>
                        </span>
                      )}
                    </p>
                  </div>
                  <div className="row__score">
                    <p className="row__score-value">
                      <span className="num">{result.total}</span>
                      <span className="visually-hidden"> out of 100, </span>
                      <WorthLabel label={result.label} />
                    </p>
                    <ScoreBar value={result.total} />
                  </div>
                  <dl className="row__figures">
                    <div>
                      <dt>Price</dt>
                      <dd className="num">{formatEuro(watch.market.price)}</dd>
                    </div>
                    <div>
                      <dt>Resale after {period}</dt>
                      <dd className="num">{formatEuro(result.estimatedResaleValue)}</dd>
                    </div>
                    <div>
                      <dt>Total cost</dt>
                      <dd className="num">{signedEuro(result.totalCostOfOwnership)}</dd>
                    </div>
                  </dl>
                  <div className="row__actions">
                    <Link
                      to={`/watches/${watch.id}`}
                      state={saved.serial ? { serial: saved.serial } : undefined}
                      className="button button--secondary"
                    >
                      Details <span className="visually-hidden">for {name}</span>
                    </Link>
                    <button type="button" className="button button--ghost" onClick={() => remove(watch.id, name)}>
                      Remove <span className="visually-hidden">{name}</span>
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        </fieldset>
      </form>

      {comparedItems.length >= MIN_COMPARE && (
        <section aria-labelledby="comparison-heading" className="panel-section">
          <h2 id="comparison-heading" ref={comparisonHeading} tabIndex={-1}>
            Comparison
          </h2>
          <ComparisonTable items={comparedItems} context={context} />
        </section>
      )}
    </>
  );
}

export function MyWatchesPage() {
  useDocumentTitle('My watches');
  const state = useAsync(loadMyWatches);
  const userContext = useUserContext();
  const [removed, setRemoved] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const statusRef = useRef<HTMLParagraphElement>(null);

  // The Remove button disappears with its row, so move focus to the confirmation.
  useEffect(() => {
    if (removed.length > 0) statusRef.current?.focus();
  }, [removed.length]);

  const items = state.status === 'success' ? state.data.filter((item) => !removed.includes(item.watch.id)) : [];

  let body;
  if (state.status === 'loading' || state.status === 'idle' || userContext.status === 'loading') {
    body = <StatusView kind="loading" title="Loading your watches" />;
  } else if (state.status === 'error') {
    body = (
      <StatusView
        kind="error"
        title="Your watches could not be loaded"
        message={state.error.message}
        fix={state.error.fix}
        {...(state.error.retryable ? { onRetry: state.retry } : {})}
      />
    );
  } else if (userContext.status === 'error' || !userContext.context) {
    body = (
      <StatusView
        kind="error"
        title="Your preferences could not be loaded"
        message={userContext.error?.message ?? 'Your budget and holding period are needed to calculate Worth Scores.'}
        fix={userContext.error?.fix}
        onRetry={userContext.retry}
      />
    );
  } else if (items.length === 0) {
    body = (
      <StatusView
        kind="empty"
        title="No saved watches yet"
        message={<p>Look up a watch by its serial number and choose Save watch. It will appear here.</p>}
        action={
          <Link to="/" className="button">
            Add a watch
          </Link>
        }
      />
    );
  } else {
    body = (
      <SavedList
        items={items}
        context={userContext.context}
        onRemoved={(watchId, name) => {
          setRemoved((r) => [...r, watchId]);
          setMessage(`${name} was removed from My watches.`);
        }}
      />
    );
  }

  return (
    <>
      <div className="page-head page-head--with-action">
        <div>
          <h1 tabIndex={-1}>My watches</h1>
          <p className="page-head__meta">
            {items.length > 0
              ? `${items.length} saved, scored with your current preferences.`
              : 'Watches you have saved, scored with your current preferences.'}
          </p>
        </div>
        {items.length > 0 && (
          <Link to="/" className="button button--secondary">
            Add a watch
          </Link>
        )}
      </div>
      <p role="status" className="status-line" ref={statusRef} tabIndex={-1}>
        {message}
      </p>
      {body}
    </>
  );
}

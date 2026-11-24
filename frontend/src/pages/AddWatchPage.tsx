import { useMemo, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { serialApi, USE_MOCK_API } from '../api';
import { MOCK_SAMPLE_SERIALS } from '../api/serial';
import { ErrorSummary } from '../components/ErrorSummary';
import { LiveAnnouncer } from '../components/LiveAnnouncer';
import { Field } from '../components/Field';
import { SaveWatchButton } from '../components/SaveWatchButton';
import { ScoreSummary } from '../components/ScoreSummary';
import { SerialFacts, StolenWarning } from '../components/SerialFacts';
import { StatusView } from '../components/StatusView';
import { useUserContext } from '../context/UserContextProvider';
import { useAsync } from '../hooks/useAsync';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { watchName } from '../lib/format';
import { MATERIAL_LABELS, MOVEMENT_LABELS, scoreWatch } from '../lib/score';
import { normaliseSerial, SERIAL_PATTERN, validateSerial } from '../lib/validation';
import type { SerialLookupResult } from '../types/watch';

const SERIAL_ID = 'serial';

/** History state used to carry the serial number. It is personal data, so it never goes in the URL. */
export interface SerialLocationState {
  serial?: string;
}

export function readSerialState(state: unknown): string {
  if (typeof state === 'object' && state !== null && 'serial' in state) {
    const serial = (state as SerialLocationState).serial;
    if (typeof serial === 'string' && SERIAL_PATTERN.test(normaliseSerial(serial))) return normaliseSerial(serial);
  }
  return '';
}

const CHECKS = [
  ['Model', 'Brand, model and reference, which the Worth Score is calculated from.'],
  ['Production', 'Year and batch the watch was made in.'],
  ['Authenticity', 'Whether the serial is consistent with the model.'],
  ['History', 'Service records and stolen-watch registers.'],
] as const;

function IdlePanel() {
  return (
    <div className="result-idle">
      <h2>What the lookup returns</h2>
      <dl className="checklist">
        {CHECKS.map(([term, text]) => (
          <div key={term}>
            <dt>{term}</dt>
            <dd>{text}</dd>
          </div>
        ))}
      </dl>
      <p className="muted">
        The Worth Score uses only the model and your preferences. Details about your specific watch, such as its
        production year or history, never change it.
      </p>
    </div>
  );
}

function LookupResult({ result }: { result: SerialLookupResult }) {
  const { context } = useUserContext();
  const { watch, check } = result;
  // Score from the model data and preferences only; the serial check is not passed in.
  const score = context ? scoreWatch(watch, context) : null;
  const name = watchName(watch);

  return (
    <article className="lookup" aria-labelledby="lookup-heading">
      <p className="lookup__kicker">
        Identified from serial <span className="serial">{check.serial}</span>
      </p>
      <h2 id="lookup-heading" className="lookup__title">
        {name}
      </h2>
      <p className="lookup__meta">
        <span>
          Reference <span className="num">{watch.reference}</span>
        </span>
        <span>{MOVEMENT_LABELS[watch.specs.movement]}</span>
        <span className="num">{watch.specs.case_mm} mm</span>
        <span>{MATERIAL_LABELS[watch.specs.material]}</span>
      </p>

      <StolenWarning check={check} />

      {score && context && <ScoreSummary result={score} context={context} size="medium" />}

      <h3 className="lookup__subhead">Serial check</h3>
      <SerialFacts check={check} />

      <div className="actions">
        <Link to={`/watches/${watch.id}`} state={{ serial: check.serial } satisfies SerialLocationState} className="button">
          See full breakdown
        </Link>
        <SaveWatchButton watch={watch} serial={check.serial} />
      </div>
    </article>
  );
}

export function AddWatchPage() {
  useDocumentTitle('Add a watch');
  const location = useLocation();
  const navigate = useNavigate();

  // The submitted serial lives in history state, so Back from a watch returns here with its result.
  const submitted = readSerialState(location.state);
  const [value, setValue] = useState(submitted);
  const [clientError, setClientError] = useState<string | undefined>();
  const [submitCount, setSubmitCount] = useState(0);

  const lookupKey = location.key;
  const load = useMemo(
    () => (submitted ? () => serialApi.lookupSerial(submitted) : null),
    // location.key changes on every submit, so the same serial can be looked up again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [submitted, lookupKey],
  );
  const lookup = useAsync(load);

  // A 400 or 422 from the server is about the field, so show it there.
  const serverFieldError =
    lookup.status === 'error' && lookup.error.code === 'invalid_request'
      ? `${lookup.error.message} ${lookup.error.fix}`
      : undefined;
  const fieldError = clientError ?? serverFieldError;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitCount((n) => n + 1);
    const result = validateSerial(value);
    if (!result.ok) {
      setClientError(result.error);
      return;
    }
    setClientError(undefined);
    setValue(result.value);
    void navigate('/', { state: { serial: result.value } satisfies SerialLocationState });
  }

  function handleChange(next: string) {
    setValue(next);
    if (clientError) {
      const result = validateSerial(next);
      setClientError(result.ok ? undefined : result.error);
    }
  }

  const announcement =
    lookup.status === 'success'
      ? `Watch identified: ${watchName(lookup.data.watch)}.${lookup.data.check.stolenCheck === 'reported' ? ' Warning: reported stolen.' : ''}`
      : '';

  let panel;
  if (lookup.status === 'idle' || (lookup.status === 'error' && lookup.error.code === 'invalid_request')) {
    panel = <IdlePanel />;
  } else if (lookup.status === 'loading') {
    panel = <StatusView kind="loading" title={`Looking up serial ${submitted}`} />;
  } else if (lookup.status === 'error' && lookup.error.code === 'not_found') {
    panel = (
      <StatusView
        kind="empty"
        title="No watch found"
        message={
          <>
            <p>
              {lookup.error.message} You entered <span className="serial">{submitted}</span>.
            </p>
            <p>{lookup.error.fix}</p>
          </>
        }
      />
    );
  } else if (lookup.status === 'error') {
    panel = (
      <StatusView
        kind="error"
        title={lookup.error.code === 'rate_limited' ? 'Too many lookups' : 'The lookup did not complete'}
        message={lookup.error.message}
        fix={lookup.error.fix}
        {...(lookup.error.retryable ? { onRetry: lookup.retry } : {})}
      />
    );
  } else {
    panel = <LookupResult result={lookup.data} />;
  }

  return (
    <div className="split">
      <div className="split__primary">
        <h1 tabIndex={-1}>Add a watch</h1>
        <p className="lead">Enter the serial number. We identify the model and check this watch&rsquo;s history.</p>

        <form className="form" noValidate onSubmit={handleSubmit}>
          <ErrorSummary
            title="The serial number could not be looked up"
            errors={clientError ? [{ fieldId: SERIAL_ID, message: clientError }] : []}
            focusKey={submitCount}
          />
          <Field
            id={SERIAL_ID}
            name="serial"
            label="Serial number"
            hint="Engraved on the case back or between the lugs, or printed on the warranty card. It does not affect the Worth Score."
            type="text"
            className="input--serial"
            autoComplete="off"
            autoCapitalize="characters"
            autoCorrect="off"
            spellCheck={false}
            maxLength={40}
            value={value}
            error={fieldError}
            onChange={(e) => handleChange(e.target.value)}
          />
          <div className="actions">
            <button type="submit" className="button button--large" disabled={lookup.status === 'loading'}>
              Look up serial
            </button>
          </div>
        </form>

        {USE_MOCK_API && (
          <div className="samples">
            <h2 className="samples__title">Sample serials</h2>
            <p className="muted small">The lookup service is not connected yet. These return sample responses.</p>
            <ul className="samples__list">
              {MOCK_SAMPLE_SERIALS.map((sample) => (
                <li key={sample.serial}>
                  <button
                    type="button"
                    className="chip"
                    onClick={() => {
                      setValue(sample.serial);
                      setClientError(undefined);
                    }}
                  >
                    <span className="serial">{sample.serial}</span>
                    <span className="chip__note">{sample.note}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <section className="split__secondary" aria-label="Lookup result">
        {panel}
      </section>
      <LiveAnnouncer message={announcement} />
    </div>
  );
}

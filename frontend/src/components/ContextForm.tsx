import { useState, type FormEvent } from 'react';
import { useUserContext } from '../context/UserContextProvider';
import { formatEuro, formatYears } from '../lib/format';
import {
  CONTEXT_LIMITS,
  type ContextField,
  type ContextFormValues,
  type FieldErrors,
  validateContext,
} from '../lib/validation';
import type { UserContext } from '../types/watch';
import { ErrorSummary } from './ErrorSummary';
import { Field } from './Field';

interface ContextFormProps {
  /** Prefix for element IDs, so the form can appear on more than one screen. */
  idPrefix: string;
  /** Heading level of the validation summary. */
  summaryHeadingLevel?: 2 | 3;
  /** The context to start from. Must be loaded before the form renders. */
  initial: UserContext;
  /** Compact layout for side panels: shorter hints. */
  compact?: boolean;
}

function toValues(context: UserContext): ContextFormValues {
  return { budget: String(context.budget), holding_period_years: String(context.holding_period_years) };
}

/**
 * Budget and holding period. Valid changes are applied immediately to the
 * shared user context, so every Worth Score updates as the user types.
 */
export function ContextForm({ idPrefix, summaryHeadingLevel = 2, initial, compact = false }: ContextFormProps) {
  const { updateContext } = useUserContext();
  const [values, setValues] = useState<ContextFormValues>(() => toValues(initial));
  const [touched, setTouched] = useState<Partial<Record<ContextField, boolean>>>({});
  const [submitCount, setSubmitCount] = useState(0);
  const [summaryErrors, setSummaryErrors] = useState<FieldErrors<ContextField>>({});
  const [savedMessage, setSavedMessage] = useState('');

  const ids = {
    budget: `${idPrefix}-budget`,
    holding_period_years: `${idPrefix}-holding`,
  } satisfies Record<ContextField, string>;

  const validation = validateContext(values);
  const errors: FieldErrors<ContextField> = validation.ok ? {} : validation.errors;
  const visibleError = (field: ContextField) => (touched[field] || submitCount > 0 ? errors[field] : undefined);

  function handleChange(field: ContextField, raw: string) {
    const next = { ...values, [field]: raw };
    setValues(next);
    setSavedMessage('');
    const result = validateContext(next);
    if (result.ok) {
      updateContext(result.value);
      // Clear the summary once everything is fixed.
      setSummaryErrors({});
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitCount((n) => n + 1);
    const result = validateContext(values);
    if (!result.ok) {
      setSummaryErrors(result.errors);
      setSavedMessage('');
      return;
    }
    setSummaryErrors({});
    updateContext(result.value);
    setSavedMessage(
      `Preferences saved: budget ${formatEuro(result.value.budget)}, holding period ${formatYears(result.value.holding_period_years)}.`,
    );
  }

  // The summary appears after a failed submit and then tracks the current errors.
  const showSummary = Object.keys(summaryErrors).length > 0;
  const summaryList = showSummary
    ? (Object.keys(ids) as ContextField[])
        .filter((field) => errors[field])
        .map((field) => ({ fieldId: ids[field], message: errors[field] ?? '' }))
    : [];

  return (
    <form className={`form${compact ? ' form--compact' : ''}`} noValidate onSubmit={handleSubmit} aria-describedby={`${idPrefix}-form-hint`}>
      <ErrorSummary
        title="Your preferences could not be saved"
        errors={summaryList}
        focusKey={submitCount}
        headingLevel={summaryHeadingLevel}
      />
      <p id={`${idPrefix}-form-hint`} className="form__hint">
        Changes apply straight away to every Worth Score.
      </p>
      <div className="form__row">
        <Field
          id={ids.budget}
          name="budget"
          label="Budget (€)"
          hint={
            compact
              ? 'The most you would spend.'
              : `The most you would spend on a watch, in euros. Between €${CONTEXT_LIMITS.budgetMin} and €${CONTEXT_LIMITS.budgetMax.toLocaleString('en-IE')}.`
          }
          type="number"
          inputMode="numeric"
          min={CONTEXT_LIMITS.budgetMin}
          max={CONTEXT_LIMITS.budgetMax}
          step={100}
          autoComplete="transaction-amount"
          value={values.budget}
          error={visibleError('budget')}
          onChange={(e) => handleChange('budget', e.target.value)}
          onBlur={() => setTouched((t) => ({ ...t, budget: true }))}
        />
        <Field
          id={ids.holding_period_years}
          name="holding_period_years"
          label="Holding period (years)"
          hint={
            compact
              ? 'How long you will keep it.'
              : `How long you plan to keep the watch. Whole years from ${CONTEXT_LIMITS.holdingMin} to ${CONTEXT_LIMITS.holdingMax}.`
          }
          type="number"
          inputMode="numeric"
          min={CONTEXT_LIMITS.holdingMin}
          max={CONTEXT_LIMITS.holdingMax}
          step={1}
          autoComplete="off"
          value={values.holding_period_years}
          error={visibleError('holding_period_years')}
          onChange={(e) => handleChange('holding_period_years', e.target.value)}
          onBlur={() => setTouched((t) => ({ ...t, holding_period_years: true }))}
        />
      </div>
      <div className="form__actions">
        <button type="submit" className="button">
          Save preferences
        </button>
        <p role="status" className="form__status">
          {savedMessage}
        </p>
      </div>
    </form>
  );
}

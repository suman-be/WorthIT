import { useEffect, useId, useRef, type MouseEvent } from 'react';

export interface SummaryError {
  /** ID of the field to move focus to. */
  fieldId: string;
  message: string;
}

interface ErrorSummaryProps {
  title: string;
  errors: SummaryError[];
  /** Change this number (for example, the submit count) to move focus to the summary. */
  focusKey: number;
  headingLevel?: 2 | 3;
}

/** Validation summary shown at the top of a form after a failed submit. */
export function ErrorSummary({ title, errors, focusKey, headingLevel = 2 }: ErrorSummaryProps) {
  const ref = useRef<HTMLDivElement>(null);
  const headingId = useId();
  const Heading = headingLevel === 3 ? 'h3' : 'h2';
  const hasErrors = errors.length > 0;

  useEffect(() => {
    if (hasErrors && focusKey > 0) ref.current?.focus();
  }, [focusKey, hasErrors]);

  if (!hasErrors) return null;

  function focusField(event: MouseEvent<HTMLAnchorElement>, fieldId: string) {
    const field = document.getElementById(fieldId);
    if (!field) return;
    event.preventDefault();
    field.focus();
    field.scrollIntoView?.({ block: 'center' });
  }

  return (
    <div ref={ref} className="error-summary" tabIndex={-1} role="alert" aria-labelledby={headingId}>
      <Heading id={headingId} className="error-summary__title">
        {title}
      </Heading>
      <ul className="error-summary__list">
        {errors.map((error) => (
          <li key={error.fieldId}>
            <a href={`#${error.fieldId}`} onClick={(event) => focusField(event, error.fieldId)}>
              {error.message}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

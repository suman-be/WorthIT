import type { InputHTMLAttributes, ReactNode } from 'react';

interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id' | 'aria-describedby' | 'aria-invalid'> {
  id: string;
  label: ReactNode;
  hint?: ReactNode;
  error?: string | undefined;
  /** Extra IDs to describe the input, for example a group-level hint. */
  describedBy?: string;
}

/** Labelled input with optional hint and inline error, wired up with aria-describedby. */
export function Field({ id, label, hint, error, describedBy, className, ...inputProps }: FieldProps) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedByIds = [describedBy, hintId, errorId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={`field${error ? ' field--error' : ''}`}>
      <label htmlFor={id} className="field__label">
        {label}
      </label>
      {hint && (
        <p id={hintId} className="field__hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="field__error">
          <span className="visually-hidden">Error: </span>
          {error}
        </p>
      )}
      <input
        id={id}
        className={`input${className ? ` ${className}` : ''}`}
        aria-describedby={describedByIds}
        aria-invalid={error ? true : undefined}
        {...inputProps}
      />
    </div>
  );
}

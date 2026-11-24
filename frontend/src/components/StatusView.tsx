import { useEffect, useRef, type ReactNode } from 'react';

type HeadingLevel = 2 | 3;

interface BaseProps {
  /** Heading level for the empty and error titles, so heading order stays correct. */
  headingLevel?: HeadingLevel;
}

interface LoadingProps extends BaseProps {
  kind: 'loading';
  /** Short description of what is loading, for example "Loading your watches". */
  title: string;
}

interface EmptyProps extends BaseProps {
  kind: 'empty';
  title: string;
  message: ReactNode;
  action?: ReactNode;
}

interface ErrorProps extends BaseProps {
  kind: 'error';
  title: string;
  /** What went wrong. */
  message: ReactNode;
  /** How the user can fix it. */
  fix?: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
  action?: ReactNode;
}

export type StatusViewProps = LoadingProps | EmptyProps | ErrorProps;

/**
 * One component for loading, empty and retryable error states.
 *
 * After "Try again", the retry button disappears; focus is moved to this
 * view's container so keyboard and screen reader users are not dropped back
 * to the top of the page.
 */
export function StatusView(props: StatusViewProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const retried = useRef(false);
  const Heading = props.headingLevel === 3 ? 'h3' : 'h2';

  useEffect(() => {
    if (retried.current && props.kind !== 'error') {
      retried.current = false;
      const active = document.activeElement;
      if (!active || active === document.body) rootRef.current?.focus();
    }
  }, [props.kind]);

  let content: ReactNode;
  switch (props.kind) {
    case 'loading':
      content = (
        <div role="status" className="status-view__loading">
          <span className="spinner" aria-hidden="true" />
          <p>{props.title}&hellip;</p>
        </div>
      );
      break;
    case 'empty':
      content = (
        <>
          <Heading className="status-view__title">{props.title}</Heading>
          <div className="status-view__message">{props.message}</div>
          {props.action && <div className="status-view__actions">{props.action}</div>}
        </>
      );
      break;
    case 'error': {
      const { onRetry } = props;
      content = (
        <div role="alert">
          <Heading className="status-view__title">{props.title}</Heading>
          <div className="status-view__message">{props.message}</div>
          {props.fix && <div className="status-view__message">{props.fix}</div>}
          {(onRetry || props.action) && (
            <div className="status-view__actions">
              {onRetry && (
                <button
                  type="button"
                  className="button button--secondary"
                  onClick={() => {
                    retried.current = true;
                    onRetry();
                  }}
                >
                  {props.retryLabel ?? 'Try again'}
                </button>
              )}
              {props.action}
            </div>
          )}
        </div>
      );
      break;
    }
  }

  return (
    <div ref={rootRef} tabIndex={-1} className={`status-view status-view--${props.kind}`}>
      {content}
    </div>
  );
}

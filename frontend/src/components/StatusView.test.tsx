import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { StatusView } from './StatusView';

describe('StatusView', () => {
  it('announces loading politely', () => {
    render(<StatusView kind="loading" title="Loading your watches" />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading your watches…');
  });

  it('shows what went wrong, how to fix it, and retries', async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    render(
      <StatusView
        kind="error"
        title="Search failed"
        message="The service did not respond."
        fix="Check your connection, then select Try again."
        onRetry={retry}
      />,
    );
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('The service did not respond.');
    expect(alert).toHaveTextContent('Check your connection, then select Try again.');
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it('keeps focus in the view after a retry', async () => {
    const user = userEvent.setup();
    function Harness() {
      const [kind, setKind] = useState<'error' | 'loading'>('error');
      return kind === 'error' ? (
        <StatusView kind="error" title="Failed" message="It failed." onRetry={() => setKind('loading')} />
      ) : (
        <StatusView kind="loading" title="Loading" />
      );
    }
    const { container } = render(<Harness />);
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(container.querySelector('.status-view')).toHaveFocus();
  });

  it('renders an empty state with a heading at the given level', () => {
    render(<StatusView kind="empty" headingLevel={3} title="No watches found" message={<p>Try fewer fields.</p>} />);
    expect(screen.getByRole('heading', { level: 3, name: 'No watches found' })).toBeInTheDocument();
  });
});

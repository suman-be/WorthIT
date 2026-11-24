import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { savedWatchesApi, userContextApi } from '../api';
import { MOCK_WATCHES } from '../api/mockWatches';
import { scoreWatch } from '../lib/score';
import { renderApp } from '../test/render';

const rolex = MOCK_WATCHES.find((w) => w.id === 'rolex-submariner-124060');
if (!rolex) throw new Error('Mock watch missing');

describe('Preferences', () => {
  it('validates fields and shows a summary when saving fails', async () => {
    const user = userEvent.setup();
    renderApp(['/preferences']);

    const budget = await screen.findByLabelText('Budget (€)');
    expect(budget).toHaveAttribute('type', 'number');
    expect(budget).toHaveAttribute('autocomplete', 'transaction-amount');

    await user.clear(budget);
    await user.type(budget, '50');
    await user.tab();
    expect(budget).toHaveAccessibleDescription(/Error:\s*Budget must be between €100 and €1,000,000\./);

    await user.click(screen.getByRole('button', { name: 'Save preferences' }));
    const summary = screen.getByRole('alert', { name: 'Your preferences could not be saved' });
    expect(summary).toHaveFocus();
    expect(within(summary).getAllByRole('link')).toHaveLength(1);

    await user.clear(budget);
    await user.type(budget, '8000');
    expect(screen.queryByRole('alert', { name: 'Your preferences could not be saved' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Save preferences' }));
    expect(screen.getByText('Preferences saved: budget €8,000, holding period 5 years.')).toBeInTheDocument();
    expect((await userContextApi.getUserContext()).context).toEqual({ budget: 8000, holding_period_years: 5 });
  });

  it('updates saved watch scores live and announces them', async () => {
    const user = userEvent.setup();
    await savedWatchesApi.saveWatch(rolex.id);
    renderApp(['/preferences']);

    const list = await screen.findByTestId('context-scores');
    const before = scoreWatch(rolex, { budget: 6000, holding_period_years: 5 });
    expect(within(list).getByText(String(before.total))).toBeInTheDocument();

    const budget = screen.getByLabelText('Budget (€)');
    await user.clear(budget);
    await user.type(budget, '12000');

    const after = scoreWatch(rolex, { budget: 12000, holding_period_years: 5 });
    expect(after.total).not.toBe(before.total);
    expect(within(list).getByText(String(after.total))).toBeInTheDocument();
    expect(screen.getByTestId('live-announcer')).toHaveTextContent(
      `Worth Scores updated. Rolex Submariner: ${after.total}, ${after.label}.`,
    );
  });

  it('says when default values are being used', async () => {
    renderApp(['/preferences']);
    expect(await screen.findByText(/These are default values/)).toBeInTheDocument();
  });
});

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MOCK_WATCHES } from '../api/mockWatches';
import { DEFAULT_CONTEXT } from '../api/userContext';
import { scoreWatch } from '../lib/score';
import { renderApp } from '../test/render';

const tudor = MOCK_WATCHES.find((w) => w.id === 'tudor-black-bay-58-m79030n');
if (!tudor) throw new Error('Mock watch missing');
const path = `/watches/${tudor.id}`;

function shownScore(): string {
  return screen.getByTestId('worth-score').querySelector('.score-summary__number')?.textContent ?? '';
}

describe('Watch detail', () => {
  it('shows the Worth Score, label, breakdown and costs', async () => {
    renderApp([path]);
    const expected = scoreWatch(tudor, DEFAULT_CONTEXT);

    expect(await screen.findByRole('heading', { level: 1, name: 'Tudor Black Bay Fifty-Eight' })).toBeInTheDocument();
    expect(shownScore()).toBe(String(expected.total));
    expect(screen.getByTestId('worth-score')).toHaveTextContent(`Worth Score: ${expected.total}/100 out of 100`);
    expect(screen.getByRole('heading', { level: 2, name: 'Score breakdown' })).toBeInTheDocument();
    expect(screen.getAllByText(expected.label).length).toBeGreaterThan(0);

    const table = screen.getByRole('table', { name: /how the worth score for tudor black bay fifty-eight is made up/i });
    for (const name of ['Group', 'Weight', 'Score (out of 100)', 'Points', 'Why']) {
      expect(within(table).getByRole('columnheader', { name })).toHaveAttribute('scope', 'col');
    }
    for (const group of expected.groups) {
      const row = within(table).getByRole('rowheader', { name: new RegExp(`^${group.label}`) });
      expect(row).toHaveAttribute('scope', 'row');
      expect(within(table).getByText(group.reason)).toBeInTheDocument();
    }
    const weights = within(table)
      .getAllByRole('row')
      .slice(1, 5)
      .map((row) => within(row).getAllByRole('cell')[0]?.textContent);
    expect(weights).toEqual(['25%', '30%', '20%', '25%']);

    expect(screen.getByTestId('resale-value')).toHaveTextContent('€3,191');
    expect(screen.getByTestId('total-cost')).toHaveTextContent('€799');
  });

  it('updates the Worth Score live when the context changes, and announces it', async () => {
    const user = userEvent.setup();
    renderApp([path]);
    await screen.findByRole('heading', { level: 1, name: 'Tudor Black Bay Fifty-Eight' });

    const before = scoreWatch(tudor, DEFAULT_CONTEXT);
    expect(shownScore()).toBe(String(before.total));
    expect(screen.getByTestId('live-announcer')).toHaveTextContent('');
    expect(screen.getByTestId('live-announcer')).toHaveAttribute('aria-live', 'polite');

    const budget = screen.getByLabelText('Budget (€)');
    await user.clear(budget);
    await user.type(budget, '2500');

    const after = scoreWatch(tudor, { ...DEFAULT_CONTEXT, budget: 2500 });
    expect(after.total).not.toBe(before.total);
    expect(shownScore()).toBe(String(after.total));
    expect(screen.getByTestId('live-announcer')).toHaveTextContent(
      `Worth Score ${after.total} out of 100, ${after.label}.`,
    );

    const holding = screen.getByLabelText('Holding period (years)');
    await user.clear(holding);
    await user.type(holding, '12');
    const later = scoreWatch(tudor, { budget: 2500, holding_period_years: 12 });
    expect(shownScore()).toBe(String(later.total));
    expect(screen.getByTestId('resale-value')).toHaveTextContent(
      `€${later.estimatedResaleValue.toLocaleString('en-IE')}`,
    );
  });

  it('shares preferences with the Preferences screen', async () => {
    const user = userEvent.setup();
    renderApp(['/preferences']);

    const holding = await screen.findByLabelText('Holding period (years)');
    await user.clear(holding);
    await user.type(holding, '10');

    await user.click(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'Add a watch' }));
    await user.type(screen.getByLabelText('Serial number'), 'TD58A2040');
    await user.click(screen.getByRole('button', { name: 'Look up serial' }));
    await user.click(await screen.findByRole('link', { name: 'See full breakdown' }));

    await screen.findByRole('heading', { level: 1, name: 'Tudor Black Bay Fifty-Eight' });
    expect(screen.getByLabelText('Holding period (years)')).toHaveValue(10);
    expect(shownScore()).toBe(String(scoreWatch(tudor, { ...DEFAULT_CONTEXT, holding_period_years: 10 }).total));
  });

  it('does not change the score for invalid context values and explains the problem', async () => {
    const user = userEvent.setup();
    renderApp([path]);
    await screen.findByRole('heading', { level: 1, name: 'Tudor Black Bay Fifty-Eight' });
    const before = shownScore();

    const holding = screen.getByLabelText('Holding period (years)');
    await user.clear(holding);
    await user.click(screen.getByRole('button', { name: 'Save preferences' }));

    const summary = screen.getByRole('alert', { name: 'Your preferences could not be saved' });
    expect(summary).toHaveFocus();
    expect(within(summary).getByRole('link', { name: /enter how many years/i })).toHaveAttribute(
      'href',
      '#detail-holding',
    );
    expect(holding).toHaveAttribute('aria-invalid', 'true');
    expect(holding).toHaveAccessibleDescription(/Error:\s*Enter how many years you plan to keep the watch/);
    expect(shownScore()).toBe(before);
  });

  it('shows serial results in their own section and the score does not change', async () => {
    renderApp([{ pathname: path, state: { serial: 'TD58A2040' } }]);
    await screen.findByRole('heading', { level: 1, name: 'Tudor Black Bay Fifty-Eight' });
    const withSerial = shownScore();

    const section = screen.getByRole('region', { name: 'Serial number check' });
    expect(within(section).getByText(/does not affect the Worth Score/)).toBeInTheDocument();
    expect(await within(section).findByText('Production year')).toBeInTheDocument();
    expect(within(section).getByText('No theft report found')).toBeInTheDocument();

    expect(withSerial).toBe(String(scoreWatch(tudor, DEFAULT_CONTEXT).total));
  });

  it('warns clearly when a serial number is reported stolen, without changing the score', async () => {
    renderApp([{ pathname: path, state: { serial: 'TD58A2099' } }]);
    await screen.findByRole('heading', { level: 1, name: 'Tudor Black Bay Fifty-Eight' });
    expect(await screen.findByText(/this serial number has been reported stolen/i)).toBeInTheDocument();
    expect(screen.queryByText(/This serial number belongs to/)).not.toBeInTheDocument();
    expect(shownScore()).toBe(String(scoreWatch(tudor, DEFAULT_CONTEXT).total));
  });

  it('flags a serial that belongs to a different model', async () => {
    renderApp([{ pathname: path, state: { serial: 'R7Q41188' } }]);
    expect(await screen.findByText('This serial number belongs to a Rolex Submariner.')).toBeInTheDocument();
    expect(shownScore()).toBe(String(scoreWatch(tudor, DEFAULT_CONTEXT).total));
  });

  it('has no serial section when no serial number was given', async () => {
    renderApp([path]);
    await screen.findByRole('heading', { level: 1, name: 'Tudor Black Bay Fifty-Eight' });
    expect(screen.queryByRole('region', { name: 'Serial number check' })).not.toBeInTheDocument();
  });

  it('explains how to fix a missing watch', async () => {
    renderApp(['/watches/does-not-exist']);
    expect(await screen.findByRole('heading', { name: 'Watch not found' })).toBeInTheDocument();
    expect(screen.getByText(/add the watch again using its serial number/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Add a watch by serial number' })).toHaveAttribute('href', '/');
  });

  it('saves the watch to My watches', async () => {
    const user = userEvent.setup();
    renderApp([path]);
    await user.click(await screen.findByRole('button', { name: 'Save watch' }));
    expect(await screen.findByText('Tudor Black Bay Fifty-Eight is saved to My watches.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove from My watches' })).toBeInTheDocument();
  });
});

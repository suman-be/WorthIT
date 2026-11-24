import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { savedWatchesApi } from '../api';
import { renderApp } from '../test/render';

async function saveThree() {
  await savedWatchesApi.saveWatch('rolex-submariner-124060');
  await savedWatchesApi.saveWatch('tudor-black-bay-58-m79030n', 'A1B2C3D4');
  await savedWatchesApi.saveWatch('grand-seiko-sbga211');
}

describe('My watches', () => {
  it('shows an empty state with a way forward', async () => {
    renderApp(['/my-watches']);
    expect(await screen.findByRole('heading', { name: 'No saved watches yet' })).toBeInTheDocument();
    expect(within(screen.getByRole('main')).getByRole('link', { name: 'Add a watch' })).toHaveAttribute('href', '/');
  });

  it('asks for at least two watches before comparing', async () => {
    const user = userEvent.setup();
    await saveThree();
    renderApp(['/my-watches']);

    await user.click(await screen.findByLabelText('Rolex Submariner'));
    await user.click(screen.getByRole('button', { name: 'Compare selected' }));

    const summary = screen.getByRole('alert', { name: 'The comparison could not be shown' });
    expect(summary).toHaveFocus();
    expect(within(summary).getByRole('link')).toHaveTextContent(/select at least one more watch/i);
    expect(screen.getByRole('group', { name: 'Saved watches' })).toHaveAccessibleDescription(
      /Error:\s*Select at least one more watch/,
    );
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('compares two or three watches in a semantic table', async () => {
    const user = userEvent.setup();
    await saveThree();
    renderApp(['/my-watches']);

    await user.click(await screen.findByLabelText('Rolex Submariner'));
    await user.click(screen.getByLabelText('Tudor Black Bay Fifty-Eight'));
    await user.click(screen.getByLabelText('Grand Seiko Snowflake'));
    await user.click(screen.getByRole('button', { name: 'Compare selected' }));

    expect(screen.getByRole('heading', { level: 2, name: 'Comparison' })).toHaveFocus();
    const table = screen.getByRole('table', { name: /comparison of 3 watches/i });
    const cols = within(table).getAllByRole('columnheader');
    expect(cols.map((c) => c.firstChild?.textContent)).toEqual([
      'Rolex Submariner',
      'Tudor Black Bay Fifty-Eight',
      'Grand Seiko Snowflake',
    ]);
    expect(cols[0]).toHaveTextContent('124060');
    cols.forEach((c) => expect(c).toHaveAttribute('scope', 'col'));
    const scoreRow = within(table).getByRole('rowheader', { name: 'Worth Score (out of 100)' });
    expect(scoreRow).toHaveAttribute('scope', 'row');
  });

  it('removes a saved watch and confirms it', async () => {
    const user = userEvent.setup();
    await saveThree();
    renderApp(['/my-watches']);

    await user.click(await screen.findByRole('button', { name: 'Remove Grand Seiko Snowflake' }));
    expect(await screen.findByText('Grand Seiko Snowflake was removed from My watches.')).toHaveFocus();
    expect(screen.queryByLabelText('Grand Seiko Snowflake')).not.toBeInTheDocument();
    expect(await savedWatchesApi.listSavedWatches()).toHaveLength(2);
  });
});

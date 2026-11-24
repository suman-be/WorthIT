import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/errors';
import type * as SerialModule from '../api/serial';
import { MOCK_WATCHES } from '../api/mockWatches';
import { DEFAULT_CONTEXT } from '../api/userContext';
import { scoreWatch } from '../lib/score';
import { renderApp } from '../test/render';

const mocks = vi.hoisted(() => ({
  lookupSerial: vi.fn(),
  actual: null as null | typeof SerialModule.lookupSerial,
}));

vi.mock('../api/serial', async (importOriginal) => {
  const actual = await importOriginal<typeof SerialModule>();
  mocks.actual = actual.lookupSerial;
  return { ...actual, lookupSerial: mocks.lookupSerial };
});

beforeEach(() => {
  mocks.lookupSerial.mockReset();
  if (mocks.actual) mocks.lookupSerial.mockImplementation(mocks.actual);
});

const rolex = MOCK_WATCHES.find((w) => w.id === 'rolex-submariner-124060');
if (!rolex) throw new Error('Mock watch missing');

async function lookUp(serial: string) {
  const user = userEvent.setup();
  renderApp(['/']);
  await user.type(screen.getByLabelText('Serial number'), serial);
  await user.click(screen.getByRole('button', { name: 'Look up serial' }));
  return user;
}

describe('Add a watch by serial number', () => {
  it('has one serial field whose hint says it does not affect the Worth Score', () => {
    renderApp(['/']);
    expect(screen.getAllByRole('textbox')).toHaveLength(1);
    const field = screen.getByLabelText('Serial number');
    expect(field).toHaveAttribute('autocomplete', 'off');
    expect(field).toHaveAccessibleDescription(/case back.*does not affect the Worth Score/);
  });

  it('shows a validation summary and inline error when the field is empty', async () => {
    const user = userEvent.setup();
    renderApp(['/']);
    await user.click(screen.getByRole('button', { name: 'Look up serial' }));

    const summary = screen.getByRole('alert', { name: 'The serial number could not be looked up' });
    expect(summary).toHaveFocus();
    const link = within(summary).getByRole('link', { name: /enter the serial number/i });
    expect(link).toHaveAttribute('href', '#serial');

    const field = screen.getByLabelText('Serial number');
    expect(field).toHaveAttribute('aria-invalid', 'true');
    expect(field).toHaveAccessibleDescription(/Error:\s*Enter the serial number/);
    await user.click(link);
    expect(field).toHaveFocus();
  });

  it('explains an invalid serial and clears the error once fixed', async () => {
    const user = await lookUp('AB#1');
    const field = screen.getByLabelText('Serial number');
    expect(field).toHaveAccessibleDescription(/4 to 20 letters or numbers/);

    await user.clear(field);
    await user.type(field, 'R7Q41188');
    expect(field).not.toHaveAttribute('aria-invalid');
  });

  it('shows the identified watch, its Worth Score and the serial check', async () => {
    await lookUp('r7q 41188');
    const result = await screen.findByRole('article', { name: 'Rolex Submariner' });
    expect(within(result).getByText('R7Q41188')).toBeInTheDocument();
    expect(within(result).getByTestId('worth-score')).toHaveTextContent(
      String(scoreWatch(rolex, DEFAULT_CONTEXT).total),
    );
    expect(within(result).getByText('No theft report found')).toBeInTheDocument();
    expect(within(result).getByRole('link', { name: 'See full breakdown' })).toHaveAttribute(
      'href',
      '/watches/rolex-submariner-124060',
    );
    expect(within(result).getByRole('button', { name: 'Save watch' })).toBeInTheDocument();
    expect(screen.getByTestId('live-announcer')).toHaveTextContent('Watch identified: Rolex Submariner.');
  });

  it('warns when the serial is reported stolen, without changing the score', async () => {
    await lookUp('TD58A2099');
    expect(await screen.findByText('Warning: this serial number has been reported stolen.')).toBeInTheDocument();
    const tudor = MOCK_WATCHES.find((w) => w.id === 'tudor-black-bay-58-m79030n');
    if (!tudor) throw new Error('Mock watch missing');
    expect(screen.getByTestId('worth-score')).toHaveTextContent(String(scoreWatch(tudor, DEFAULT_CONTEXT).total));
  });

  it('handles a not-found response with a way to fix it', async () => {
    await lookUp('00004417');
    expect(await screen.findByRole('heading', { name: 'No watch found' })).toBeInTheDocument();
    expect(screen.getByText(/Check the serial on the case back/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });

  it('shows server validation errors next to the field', async () => {
    mocks.lookupSerial.mockRejectedValue(
      new ApiError('invalid_request', 'This serial format is not used by any brand we know.', 'Check it and try again.', {
        field: 'serial',
      }),
    );
    await lookUp('ZZZZ1111');
    const field = screen.getByLabelText('Serial number');
    expect(await screen.findByText(/This serial format is not used by any brand we know/)).toBeInTheDocument();
    expect(field).toHaveAttribute('aria-invalid', 'true');
  });

  it('offers a retry for rate limits and server errors', async () => {
    mocks.lookupSerial.mockRejectedValueOnce(
        new ApiError('rate_limited', 'Too many requests were sent in a short time.', 'Wait 30 seconds, then select Try again.'),
      );
    const user = await lookUp('R7Q41188');
    expect(await screen.findByRole('heading', { name: 'Too many lookups' })).toBeInTheDocument();
    expect(screen.getByText('Wait 30 seconds, then select Try again.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('article', { name: 'Rolex Submariner' })).toBeInTheDocument();
  });

  it('fills the field from a sample serial', async () => {
    const user = userEvent.setup();
    renderApp(['/']);
    await user.click(screen.getByRole('button', { name: /OM5512903/ }));
    expect(screen.getByLabelText('Serial number')).toHaveValue('OM5512903');
  });
});

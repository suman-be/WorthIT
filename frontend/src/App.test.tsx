import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { resetStorageForTests } from './api/storage';
import { renderApp } from './test/render';

describe('App shell', () => {
  it('has landmarks, a skip link and exactly one h1', () => {
    renderApp(['/']);
    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveAttribute('href', '#main');
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main');
    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('moves focus to the new h1 and updates the title on route change', async () => {
    const user = userEvent.setup();
    renderApp(['/']);
    expect(document.title).toBe('Add a watch – WorthIT');

    const nav = screen.getByRole('navigation', { name: 'Main' });
    await user.click(within(nav).getByRole('link', { name: 'My watches' }));
    const h1 = screen.getByRole('heading', { level: 1, name: 'My watches' });
    expect(h1).toHaveFocus();
    expect(h1).toHaveAttribute('tabindex', '-1');
    expect(document.title).toBe('My watches – WorthIT');
    expect(within(nav).getByRole('link', { name: 'My watches' })).toHaveAttribute('aria-current', 'page');

    await user.click(within(nav).getByRole('link', { name: 'Preferences' }));
    expect(screen.getByRole('heading', { level: 1, name: 'Preferences' })).toHaveFocus();
    expect(document.title).toBe('Preferences – WorthIT');
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('keeps working when browser storage is blocked', async () => {
    const user = userEvent.setup();
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Blocked', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('Blocked', 'SecurityError');
    });
    resetStorageForTests();

    renderApp(['/watches/tudor-black-bay-58-m79030n']);
    expect(await screen.findByText(/Your browser is not letting WorthIT store data/)).toBeInTheDocument();

    await user.click(await screen.findByRole('button', { name: 'Save watch' }));
    expect(await screen.findByText('Tudor Black Bay Fifty-Eight is saved to My watches.')).toBeInTheDocument();

    await user.click(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'My watches' }));
    // The saved watch is still listed for this session, kept in memory.
    expect(await screen.findByText('Tudor Black Bay Fifty-Eight', { selector: '.row__name' })).toBeInTheDocument();
  });

  it('redirects the old /context address to Preferences', async () => {
    renderApp(['/context']);
    expect(await screen.findByRole('heading', { level: 1, name: 'Preferences' })).toBeInTheDocument();
  });

  it('shows a not found page with a way back', () => {
    renderApp(['/nowhere']);
    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument();
    expect(document.title).toBe('Page not found – WorthIT');
  });
});

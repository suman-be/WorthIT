import { render } from '@testing-library/react';
import { MemoryRouter, type InitialEntry } from 'react-router';
import { AppRoutes } from '../App';
import { UserContextProvider } from '../context/UserContextProvider';

/** Render the full app at a given route, with all providers. */
export function renderApp(initialEntries: InitialEntry[] = ['/']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <UserContextProvider>
        <AppRoutes />
      </UserContextProvider>
    </MemoryRouter>,
  );
}

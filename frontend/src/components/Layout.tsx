import { useEffect, useRef } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router';
import { useUserContext } from '../context/UserContextProvider';
import { useStoragePersistent } from '../hooks/useStoragePersistent';
import { formatEuro, formatYears } from '../lib/format';

/** The preferences every Worth Score is based on, always visible in the sidebar. */
function PreferencesSummary() {
  const { context } = useUserContext();
  if (!context) return null;
  return (
    <div className="sidebar__prefs">
      <p className="sidebar__prefs-title">Scores are based on</p>
      <dl className="sidebar__prefs-list">
        <div>
          <dt>Budget</dt>
          <dd className="num">{formatEuro(context.budget)}</dd>
        </div>
        <div>
          <dt>Holding period</dt>
          <dd className="num">{formatYears(context.holding_period_years)}</dd>
        </div>
      </dl>
    </div>
  );
}

/**
 * App shell: skip link, sidebar header with navigation, main landmark, footer.
 * On every route change, focus moves to the new screen's <h1>.
 */
export function Layout() {
  const { pathname } = useLocation();
  const previousPath = useRef(pathname);
  const persistent = useStoragePersistent();

  useEffect(() => {
    if (previousPath.current === pathname) return;
    previousPath.current = pathname;
    document.querySelector<HTMLElement>('main h1')?.focus();
  }, [pathname]);

  return (
    <div className="shell">
      <a href="#main" className="skip-link">
        Skip to main content
      </a>
      <header className="sidebar">
        <Link to="/" className="wordmark">
          Worth<span className="wordmark__accent">IT</span>
        </Link>
        <nav aria-label="Main" className="sidebar__nav">
          <ul>
            <li>
              <NavLink to="/" end>
                Add a watch
              </NavLink>
            </li>
            <li>
              <NavLink to="/my-watches">My watches</NavLink>
            </li>
            <li>
              <NavLink to="/preferences">Preferences</NavLink>
            </li>
          </ul>
        </nav>
        <PreferencesSummary />
      </header>
      <div className="shell__body">
        <main id="main" tabIndex={-1} className="main">
          {!persistent && (
            <div className="notice" role="note">
              <p>
                Your browser is not letting WorthIT store data, so saved watches and preferences will be lost when you
                close this tab. To keep them, allow site data for this site in your browser settings.
              </p>
            </div>
          )}
          <Outlet />
        </main>
        <footer className="footer">
          <p>Worth Scores and valuations are estimates to support your decision, not financial advice.</p>
        </footer>
      </div>
    </div>
  );
}

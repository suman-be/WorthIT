import { Link } from 'react-router';
import { useDocumentTitle } from '../hooks/useDocumentTitle';

export function NotFoundPage() {
  useDocumentTitle('Page not found');
  return (
    <>
      <h1 tabIndex={-1}>Page not found</h1>
      <p>There is no page at this address. Check the address for typing errors, or use one of these links.</p>
      <ul className="plain-list">
        <li>
          <Link to="/">Add a watch</Link>
        </li>
        <li>
          <Link to="/my-watches">My watches</Link>
        </li>
      </ul>
    </>
  );
}

import { Navigate, Route, Routes, useParams } from 'react-router';
import { Layout } from './components/Layout';
import { AddWatchPage } from './pages/AddWatchPage';
import { MyWatchesPage } from './pages/MyWatchesPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { PreferencesPage } from './pages/PreferencesPage';
import { WatchDetailPage } from './pages/WatchDetailPage';

function WatchDetailRoute() {
  const { watchId = '' } = useParams();
  // Keyed so all per-watch state resets when moving between watches.
  return <WatchDetailPage key={watchId} watchId={watchId} />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<AddWatchPage />} />
        <Route path="watches/:watchId" element={<WatchDetailRoute />} />
        <Route path="preferences" element={<PreferencesPage />} />
        {/* Earlier name of the preferences screen. */}
        <Route path="context" element={<Navigate to="/preferences" replace />} />
        <Route path="my-watches" element={<MyWatchesPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

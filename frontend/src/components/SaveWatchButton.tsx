import { useCallback, useState } from 'react';
import { Link } from 'react-router';
import { type ApiError, savedWatchesApi, toApiError } from '../api';
import { useAsync } from '../hooks/useAsync';
import { watchName } from '../lib/format';
import type { SavedWatch, Watch } from '../types/watch';

type Status = { kind: 'idle' } | { kind: 'busy' } | { kind: 'done'; message: string } | { kind: 'error'; error: ApiError };

/** Save or remove a watch from My watches, with a status message. */
export function SaveWatchButton({ watch, serial }: { watch: Watch; serial: string | undefined }) {
  const load = useCallback(() => savedWatchesApi.getSavedWatch(watch.id).catch(() => null), [watch.id]);
  const loaded = useAsync(load);
  const [override, setOverride] = useState<{ value: SavedWatch | null } | null>(null);
  const [status, setStatus] = useState<Status>({ kind: 'idle' });

  const saved = override ? override.value : loaded.status === 'success' ? loaded.data : null;
  const name = watchName(watch);
  const busy = status.kind === 'busy' || loaded.status === 'loading';

  async function run(action: () => Promise<SavedWatch | null>, message: string) {
    setStatus({ kind: 'busy' });
    try {
      setOverride({ value: await action() });
      setStatus({ kind: 'done', message });
    } catch (error) {
      setStatus({ kind: 'error', error: toApiError(error) });
    }
  }

  return (
    <div className="save-control">
      {saved ? (
        <button
          type="button"
          className="button button--secondary"
          disabled={busy}
          onClick={() =>
            run(async () => {
              await savedWatchesApi.removeSavedWatch(watch.id);
              return null;
            }, `${name} was removed from My watches.`)
          }
        >
          Remove from My watches
        </button>
      ) : (
        <button
          type="button"
          className="button"
          disabled={busy}
          onClick={() => run(() => savedWatchesApi.saveWatch(watch.id, serial), `${name} is saved to My watches.`)}
        >
          Save watch
        </button>
      )}
      <p role="status" className="save-control__status">
        {status.kind === 'busy' && 'Saving…'}
        {status.kind === 'done' && (
          <>
            {status.message} {saved && <Link to="/my-watches">Open My watches</Link>}
          </>
        )}
      </p>
      {status.kind === 'error' && (
        <p className="inline-error" role="alert">
          {status.error.message} {status.error.fix}
        </p>
      )}
    </div>
  );
}

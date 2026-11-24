import { useSyncExternalStore } from 'react';
import { isStoragePersistent, subscribeToStorageStatus } from '../api';

/** True while browser storage is available; false when the app has fallen back to memory. */
export function useStoragePersistent(): boolean {
  return useSyncExternalStore(subscribeToStorageStatus, isStoragePersistent, () => true);
}

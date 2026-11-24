/**
 * Single entry point for all data access. Components import from here only.
 */
export * as watchesApi from './watches';
export * as serialApi from './serial';
export * as savedWatchesApi from './savedWatches';
export * as userContextApi from './userContext';
export { ApiError, toApiError } from './errors';
export { USE_MOCK_API } from './config';
export { isStoragePersistent, subscribeToStorageStatus } from './storage';

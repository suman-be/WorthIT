import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { type ApiError, userContextApi } from '../api';
import { useAsync } from '../hooks/useAsync';
import type { UserContext } from '../types/watch';

interface UserContextValue {
  status: 'loading' | 'ready' | 'error';
  /** Null until loaded. */
  context: UserContext | null;
  /** True when the defaults are in use because nothing has been saved yet. */
  isDefault: boolean;
  error: ApiError | null;
  retry: () => void;
  /** Apply a validated context immediately and persist it. */
  updateContext: (context: UserContext) => void;
}

const UserContextContext = createContext<UserContextValue | null>(null);

export function UserContextProvider({ children }: { children: ReactNode }) {
  const loaded = useAsync(userContextApi.getUserContext);
  const [override, setOverride] = useState<UserContext | null>(null);

  const updateContext = useCallback((next: UserContext) => {
    setOverride(next);
    void userContextApi.saveUserContext(next);
  }, []);

  const base = { retry: loaded.retry, updateContext };
  let value: UserContextValue;
  if (override) {
    value = { ...base, status: 'ready', context: override, isDefault: false, error: null };
  } else if (loaded.status === 'success') {
    value = { ...base, status: 'ready', context: loaded.data.context, isDefault: loaded.data.isDefault, error: null };
  } else if (loaded.status === 'error') {
    value = { ...base, status: 'error', context: null, isDefault: false, error: loaded.error };
  } else {
    value = { ...base, status: 'loading', context: null, isDefault: false, error: null };
  }

  return <UserContextContext.Provider value={value}>{children}</UserContextContext.Provider>;
}

export function useUserContext(): UserContextValue {
  const value = useContext(UserContextContext);
  if (!value) throw new Error('useUserContext must be used inside <UserContextProvider>.');
  return value;
}

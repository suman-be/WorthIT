import { useEffect } from 'react';

export const APP_NAME = 'WorthIT';

/** Sets document.title to "<title> – WorthIT". */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} – ${APP_NAME}`;
  }, [title]);
}

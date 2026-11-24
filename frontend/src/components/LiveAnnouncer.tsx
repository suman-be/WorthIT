import { useState } from 'react';

/**
 * Visually hidden aria-live="polite" region.
 * Announces `message` only when it changes after the first render, so screen
 * readers are not interrupted on page load.
 */
export function LiveAnnouncer({ message }: { message: string }) {
  const [previous, setPrevious] = useState(message);
  const [announcement, setAnnouncement] = useState('');

  if (message !== previous) {
    setPrevious(message);
    setAnnouncement(message);
  }

  return (
    <div className="visually-hidden" aria-live="polite" aria-atomic="true" data-testid="live-announcer">
      {announcement}
    </div>
  );
}

'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { API_BASE } from '@/lib/api';

/**
 * Keep-alive ping every 4 minutes so Railway free-tier never goes to sleep.
 * Uses the lightweight /api/ping endpoint (no GEE call needed).
 */
function KeepAlive() {
  useEffect(() => {
    // Ping immediately on mount so Railway wakes up ASAP
    fetch(`${API_BASE}/api/ping`).catch(() => {});

    // Then ping every 4 minutes (Railway sleeps after ~30 min idle)
    const interval = setInterval(() => {
      fetch(`${API_BASE}/api/ping`).catch(() => {});
    }, 4 * 60 * 1000);

    return () => clearInterval(interval);
  }, []);

  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={client}>
      <KeepAlive />
      {children}
    </QueryClientProvider>
  );
}

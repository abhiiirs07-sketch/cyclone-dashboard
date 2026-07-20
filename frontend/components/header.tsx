'use client';

import { useEffect, useState } from 'react';
import { Search, Download, User, Sun, Moon } from 'lucide-react';
import type { CycloneInfo } from '@/lib/api';
import { useBackendHealth } from '@/lib/api';

export function Header({
  cyclones,
  selected,
  onSelect,
  activeCycloneInfo,
}: {
  cyclones: CycloneInfo[];
  selected: string | null;
  onSelect: (id: string) => void;
  activeCycloneInfo?: CycloneInfo;
}) {
  const health = useBackendHealth();
  const [dark, setDark] = useState(true);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
  }, [dark]);

  const isLoading   = health.isLoading || health.isFetching || health.fetchStatus === 'fetching';
  const connected    = health.data?.earthEngine === 'connected';
  const failed       = health.isError && !isLoading;          // all retries exhausted

  return (
    <header className="flex h-14 items-center gap-3 border-b border-[var(--border-subtle)] bg-[var(--surface-1)]/80 px-4 backdrop-blur-md">
      <div className="flex items-center gap-2">
        <svg width="22" height="22" viewBox="0 0 24 24" className="shrink-0 text-[var(--accent-cyan)]">
          <path
            fill="currentColor"
            d="M12 2a10 10 0 100 20 10 10 0 000-20zm0 3a7 7 0 016.3 4H12a3 3 0 00-3 3c0 1.5 1 2.6 2.3 2.9A7 7 0 1112 5z"
          />
        </svg>
        <div className="leading-tight">
          <p className="font-semibold tracking-tight">Cyclone Intelligence &amp; Impact Assessment</p>
          <p className="hidden text-[10px] text-[var(--text-tertiary)] md:block">
            Google Earth Engine powered disaster monitoring system
          </p>
        </div>
      </div>

      <select
        className="ml-4 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-2 py-1.5 text-sm"
        value={selected ?? ''}
        onChange={(e) => onSelect(e.target.value)}
      >
        {cyclones.length === 0 && <option>Loading cyclones…</option>}
        {cyclones.map((c) => (
          <option key={c.id} value={c.id}>
            {c.label} — {c.landfall}
          </option>
        ))}
      </select>

      {activeCycloneInfo && (
        <span className="hidden rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-2 py-1 font-mono text-xs text-[var(--text-secondary)] lg:inline">
          Event window: {activeCycloneInfo.dates.evtS} → {activeCycloneInfo.dates.evtE}
        </span>
      )}

      <div className="relative ml-auto hidden items-center sm:flex">
        <Search className="pointer-events-none absolute left-2 h-3.5 w-3.5 text-[var(--text-tertiary)]" />
        <input
          disabled
          placeholder="Search (coming soon)"
          className="w-40 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] py-1.5 pl-7 pr-2 text-xs text-[var(--text-tertiary)] placeholder:text-[var(--text-tertiary)]"
        />
      </div>

      <button
        onClick={() => setDark((d) => !d)}
        title="Toggle theme"
        className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] p-1.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
      >
        {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </button>

      <button
        onClick={() => window.print()}
        title="Export Dashboard to PDF / Print"
        className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] p-1.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition"
      >
        <Download className="h-4 w-4" />
      </button>

      <button
        disabled
        title="User accounts aren't part of this phase"
        className="cursor-not-allowed rounded-full border border-[var(--border-subtle)] bg-[var(--surface-2)] p-1.5 text-[var(--text-tertiary)]"
      >
        <User className="h-4 w-4" />
      </button>

      <div className="flex items-center gap-1.5 text-[11px]" title={health.data?.detail ?? (isLoading ? 'Waking up Railway backend…' : 'Could not reach backend')}>
        <span className={`h-2 w-2 rounded-full transition-colors duration-500 ${
          connected ? 'bg-emerald-400 shadow-[0_0_6px_#34d399]'
          : isLoading ? 'animate-pulse bg-amber-400'
          : 'bg-red-400'
        }`} />
        <span className="hidden text-[var(--text-tertiary)] xl:inline">
          {connected ? 'Earth Engine connected'
           : isLoading ? 'Connecting to Earth Engine…'
           : 'Earth Engine not connected'}
        </span>
      </div>
    </header>
  );
}

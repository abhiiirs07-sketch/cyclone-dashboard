'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import type { TrackLayersResponse } from '@/lib/api';

interface TrackFeature {
  geometry: { coordinates: [number, number] };
  properties: { ISO_TIME?: string; USA_WIND?: number; USA_PRES?: number; USA_STATUS?: string };
}

interface Props {
  trackLayers?: TrackLayersResponse;
  evtStart?: string;  // YYYY-MM-DD — landfall window start
  evtEnd?: string;    // YYYY-MM-DD — landfall window end
  onFrame: (index: number, floodProgress: number) => void;
}

const SPEEDS = [0.5, 1, 2, 4] as const;

export function TimeSliderPanel({ trackLayers, evtStart, evtEnd, onFrame }: Props) {
  const features: TrackFeature[] = (trackLayers?.trackPoints?.features as any[]) ?? [];
  const timestamps = features.map(f => new Date(f.properties?.ISO_TIME ?? '').getTime()).filter(Boolean);
  const total = timestamps.length;

  const [index, setIndex]       = useState(0);
  const [playing, setPlaying]   = useState(false);
  const [speed, setSpeed]       = useState<0.5 | 1 | 2 | 4>(1);
  const intervalRef             = useRef<ReturnType<typeof setInterval> | null>(null);

  // Derived flood progress (0-1) based on current timestamp vs event window
  const floodProgress = useCallback((i: number): number => {
    if (!evtStart || !evtEnd || total === 0) return 0;
    const t  = timestamps[i];
    const t0 = new Date(evtStart).getTime();
    const t1 = new Date(evtEnd).getTime();
    if (t <= t0) return 0;
    if (t >= t1) return 1;
    return (t - t0) / (t1 - t0);
  }, [timestamps, evtStart, evtEnd, total]);

  // Fire onFrame whenever index changes
  useEffect(() => {
    if (total === 0) return;
    onFrame(index, floodProgress(index));
  }, [index, total, floodProgress, onFrame]);

  // Playback loop
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (!playing || total === 0) return;

    const ms = 600 / speed;   // base 600 ms per step at 1×
    intervalRef.current = setInterval(() => {
      setIndex(prev => {
        if (prev >= total - 1) {
          setPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, ms);

    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [playing, speed, total]);

  if (total === 0) return null;

  const feat      = features[index];
  const wind      = feat?.properties?.USA_WIND ?? 0;
  const pres      = feat?.properties?.USA_PRES ?? 0;
  const status    = feat?.properties?.USA_STATUS ?? '';
  const timeLabel = feat?.properties?.ISO_TIME
    ? new Date(feat.properties.ISO_TIME).toLocaleString('en-IN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' }) + ' UTC'
    : '';
  const fp        = floodProgress(index);
  const windColor =
    wind >= 137 ? '#800026' : wind >= 113 ? '#BD0026' : wind >= 96 ? '#E31A1C' :
    wind >= 83  ? '#FC4E2A' : wind >= 64  ? '#FD8D3C' : wind >= 34 ? '#FEB24C' : '#2C7FB8';

  return (
    <div className="absolute bottom-2 left-1/2 -translate-x-1/2 z-20 w-[640px] max-w-[calc(100vw-2rem)]
                    rounded-xl border border-white/10 bg-black/75 px-4 py-3 backdrop-blur-md shadow-2xl">
      {/* Storm info row */}
      <div className="mb-2 flex items-center justify-between gap-3 text-xs">
        <span className="font-mono text-[var(--text-tertiary)]">{timeLabel}</span>
        <div className="flex items-center gap-3">
          <span style={{ color: windColor }} className="font-bold">{wind} kt wind</span>
          <span className="text-[var(--text-secondary)]">{pres ? `${pres} hPa` : ''}</span>
          {status && <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)] uppercase">{status}</span>}
          {fp > 0 && fp < 1 && (
            <span className="rounded bg-blue-900/60 px-1.5 py-0.5 text-[10px] text-blue-300">
              🌊 Flooding {Math.round(fp * 100)}%
            </span>
          )}
          {fp >= 1 && (
            <span className="rounded bg-blue-900/60 px-1.5 py-0.5 text-[10px] text-blue-300">🌊 Post-flood</span>
          )}
        </div>
      </div>

      {/* Timeline scrubber */}
      <div className="mb-2 relative">
        <input
          type="range" min={0} max={total - 1} value={index}
          onChange={e => { setPlaying(false); setIndex(Number(e.target.value)); }}
          className="w-full h-1.5 accent-orange-500 cursor-pointer"
        />
        {/* Landfall zone indicator */}
        {evtStart && evtEnd && (
          (() => {
            const t0 = new Date(evtStart).getTime();
            const t1 = new Date(evtEnd).getTime();
            const pct0 = Math.max(0, timestamps.findIndex(t => t >= t0)) / (total - 1) * 100;
            const pct1 = Math.min(100, timestamps.findIndex(t => t >= t1)) / (total - 1) * 100;
            const width = Math.max(2, pct1 - pct0);
            return (
              <div
                className="absolute top-0 h-1.5 rounded bg-orange-500/50 pointer-events-none"
                style={{ left: `${pct0}%`, width: `${width}%` }}
                title="Event window (landfall)"
              />
            );
          })()
        )}
      </div>

      {/* Controls row */}
      <div className="flex items-center gap-2">
        {/* Step back */}
        <button
          onClick={() => { setPlaying(false); setIndex(i => Math.max(0, i - 1)); }}
          className="rounded p-1 text-[var(--text-secondary)] hover:text-white hover:bg-white/10 transition"
          title="Step back"
        >⏮</button>

        {/* Play / Pause */}
        <button
          onClick={() => {
            if (index >= total - 1) setIndex(0);
            setPlaying(p => !p);
          }}
          className="flex h-8 w-8 items-center justify-center rounded-full bg-orange-600 text-white shadow hover:bg-orange-500 transition"
        >
          {playing ? '⏸' : '▶'}
        </button>

        {/* Step forward */}
        <button
          onClick={() => { setPlaying(false); setIndex(i => Math.min(total - 1, i + 1)); }}
          className="rounded p-1 text-[var(--text-secondary)] hover:text-white hover:bg-white/10 transition"
          title="Step forward"
        >⏭</button>

        {/* Reset */}
        <button
          onClick={() => { setPlaying(false); setIndex(0); }}
          className="rounded p-1 text-[var(--text-secondary)] hover:text-white hover:bg-white/10 transition text-xs"
          title="Reset"
        >↺</button>

        {/* Progress text */}
        <span className="flex-1 text-center text-xs font-mono text-[var(--text-tertiary)]">
          {index + 1} / {total}
        </span>

        {/* Speed */}
        <div className="flex items-center gap-1 text-xs">
          <span className="text-[var(--text-tertiary)]">Speed</span>
          {SPEEDS.map(s => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              className={`rounded px-1.5 py-0.5 transition ${
                speed === s ? 'bg-orange-600 text-white' : 'text-[var(--text-tertiary)] hover:bg-white/10'
              }`}
            >{s}×</button>
          ))}
        </div>
      </div>
    </div>
  );
}

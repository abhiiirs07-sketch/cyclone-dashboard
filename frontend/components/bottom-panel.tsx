'use client';

import { useEffect, useRef, useState } from 'react';
import type { TrackLayersResponse } from '@/lib/api';

interface LogEntry {
  time: string;
  message: string;
}

function windColor(kts: number): string {
  if (kts >= 137) return '#ff1744';
  if (kts >= 113) return '#ff5252';
  if (kts >= 96)  return '#ff7d47';
  if (kts >= 83)  return '#ff9100';
  if (kts >= 64)  return '#ffc400';
  if (kts >= 34)  return '#ffea00';
  return '#00e5ff';
}

export function BottomPanel({
  activeCyclone,
  studyAreaStatus,
  trackLayersStatus,
  floodLayersStatus,
  hazardLayersStatus,
  vegLayersStatus,
  lulcLayersStatus,
  popLayersStatus,
  mhLayersStatus,
  valLayersStatus,
  reportSummaryStatus,
  trackLayers,
  evtStart,
  evtEnd,
  animationFrame,
  setAnimationFrame,
  setFloodProgress,
}: {
  activeCyclone: string | null;
  studyAreaStatus: 'pending' | 'error' | 'success';
  trackLayersStatus?: 'pending' | 'error' | 'success';
  floodLayersStatus?: 'pending' | 'error' | 'success';
  hazardLayersStatus?: 'pending' | 'error' | 'success';
  vegLayersStatus?: 'pending' | 'error' | 'success';
  lulcLayersStatus?: 'pending' | 'error' | 'success';
  popLayersStatus?: 'pending' | 'error' | 'success';
  mhLayersStatus?: 'pending' | 'error' | 'success';
  valLayersStatus?: 'pending' | 'error' | 'success';
  reportSummaryStatus?: 'pending' | 'error' | 'success';
  trackLayers?: TrackLayersResponse;
  evtStart?: string;
  evtEnd?: string;
  animationFrame?: number | null;
  setAnimationFrame?: React.Dispatch<React.SetStateAction<number | null>>;
  setFloodProgress?: (progress: number) => void;
}) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const lastLogged = useRef<Record<string, string>>({});

  // Defaults for optional props to bypass compiler caching issues
  const _animationFrame    = animationFrame ?? null;
  const _setAnimationFrame = setAnimationFrame ?? (() => {});
  const _setFloodProgress  = setFloodProgress ?? (() => {});

  // Timeline / Playback state
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed]     = useState<0.5 | 1 | 2 | 4>(1);
  const intervalRef           = useRef<ReturnType<typeof setInterval> | null>(null);

  const features = (trackLayers?.trackPoints?.features as any[]) ?? [];
  const timestamps = features.map(f => new Date(f.properties?.ISO_TIME ?? '').getTime()).filter(Boolean);
  const total = timestamps.length;

  // Logger helper
  function addLog(key: string, message: string) {
    if (lastLogged.current[key] === message) return;
    lastLogged.current[key] = message;
    setLogs((prev) => [...prev.slice(-49), { time: new Date().toLocaleTimeString(), message }]);
  }

  // Derive flood progress (0-1) based on current timestamp vs event window
  const getFloodProgress = (i: number): number => {
    if (!evtStart || !evtEnd || total === 0) return 0;
    const t  = timestamps[i];
    const t0 = new Date(evtStart).getTime();
    const t1 = new Date(evtEnd).getTime();
    if (t <= t0) return 0;
    if (t >= t1) return 1;
    return (t - t0) / (t1 - t0);
  };

  // Synchronize floodProgress value to page state whenever index changes
  useEffect(() => {
    if (total === 0) return;
    const currentFrame = _animationFrame ?? 0;
    _setFloodProgress(getFloodProgress(currentFrame));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [_animationFrame, total]);

  // Handle activeCyclone change: reset timeline player
  useEffect(() => {
    setPlaying(false);
    _setAnimationFrame(null);
    _setFloodProgress(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCyclone]);

  // Auto-stop playback when reaching the end of the track
  useEffect(() => {
    if (_animationFrame !== null && _animationFrame >= total - 1) {
      setPlaying(false);
    }
  }, [_animationFrame, total]);

  // Timer loop for autoplay
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (!playing || total === 0) return;

    const ms = 600 / speed;
    intervalRef.current = setInterval(() => {
      _setAnimationFrame((prev) => {
        const current = prev ?? 0;
        if (current >= total - 1) {
          return current;
        }
        return current + 1;
      });
    }, ms);

    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, speed, total]);

  // Activity log hooks
  useEffect(() => {
    if (!activeCyclone) return;
    if (studyAreaStatus === 'pending')
      addLog('m1', `Requesting Module 1 (study area) for ${activeCyclone}…`);
    else if (studyAreaStatus === 'success')
      addLog('m1', `✅ Module 1 study area loaded for ${activeCyclone}`);
    else if (studyAreaStatus === 'error')
      addLog('m1', `❌ Module 1 failed for ${activeCyclone}`);
  }, [activeCyclone, studyAreaStatus]);

  useEffect(() => {
    if (!activeCyclone || !trackLayersStatus) return;
    if (trackLayersStatus === 'pending')
      addLog('m3', `Fetching Module 3 IBTrACS track for ${activeCyclone}…`);
    else if (trackLayersStatus === 'success')
      addLog('m3', `✅ Module 3 cyclone track loaded for ${activeCyclone}`);
    else if (trackLayersStatus === 'error')
      addLog('m3', `❌ Module 3 track failed for ${activeCyclone}`);
  }, [activeCyclone, trackLayersStatus]);

  useEffect(() => {
    if (!activeCyclone || !floodLayersStatus) return;
    if (floodLayersStatus === 'pending')
      addLog('m5', `Fetching Module 5 SAR flood layers for ${activeCyclone}…`);
    else if (floodLayersStatus === 'success')
      addLog('m5', `✅ Module 5 flood extent loaded for ${activeCyclone}`);
    else if (floodLayersStatus === 'error')
      addLog('m5', `❌ Module 5 flood mapping failed for ${activeCyclone}`);
  }, [activeCyclone, floodLayersStatus]);

  useEffect(() => {
    if (!activeCyclone || !hazardLayersStatus) return;
    if (hazardLayersStatus === 'pending')
      addLog('m6', `Fetching Module 6 hazard/surge layers for ${activeCyclone}…`);
    else if (hazardLayersStatus === 'success')
      addLog('m6', `✅ Module 6 composite hazard index loaded for ${activeCyclone}`);
    else if (hazardLayersStatus === 'error')
      addLog('m6', `❌ Module 6 hazard index failed for ${activeCyclone}`);
  }, [activeCyclone, hazardLayersStatus]);

  useEffect(() => {
    if (!activeCyclone || !vegLayersStatus) return;
    if (vegLayersStatus === 'pending')
      addLog('m7', `Fetching Module 7 Sentinel-2 vegetation layers for ${activeCyclone}…`);
    else if (vegLayersStatus === 'success')
      addLog('m7', `✅ Module 7 vegetation damage loaded for ${activeCyclone}`);
    else if (vegLayersStatus === 'error')
      addLog('m7', `❌ Module 7 vegetation damage failed for ${activeCyclone}`);
  }, [activeCyclone, vegLayersStatus]);

  useEffect(() => {
    if (!activeCyclone || !lulcLayersStatus) return;
    if (lulcLayersStatus === 'pending')
      addLog('m8', `Fetching Module 8 ESA WorldCover LULC layers for ${activeCyclone}…`);
    else if (lulcLayersStatus === 'success')
      addLog('m8', `✅ Module 8 LULC impact layers loaded for ${activeCyclone}`);
    else if (lulcLayersStatus === 'error')
      addLog('m8', `❌ Module 8 LULC impact failed for ${activeCyclone}`);
  }, [activeCyclone, lulcLayersStatus]);

  useEffect(() => {
    if (!activeCyclone || !popLayersStatus) return;
    if (popLayersStatus === 'pending')
      addLog('m9', `Fetching Module 9 population exposure layers for ${activeCyclone}…`);
    else if (popLayersStatus === 'success')
      addLog('m9', `✅ Module 9 population exposure loaded for ${activeCyclone}`);
    else if (popLayersStatus === 'error')
      addLog('m9', `❌ Module 9 population exposure failed for ${activeCyclone}`);
  }, [activeCyclone, popLayersStatus]);

  useEffect(() => {
    if (!activeCyclone || !mhLayersStatus) return;
    if (mhLayersStatus === 'pending')
      addLog('m10', `Fetching Module 10 multi-hazard composite layers for ${activeCyclone}…`);
    else if (mhLayersStatus === 'success')
      addLog('m10', `✅ Module 10 multi-hazard index loaded for ${activeCyclone}`);
    else if (mhLayersStatus === 'error')
      addLog('m10', `❌ Module 10 multi-hazard failed for ${activeCyclone}`);
  }, [activeCyclone, mhLayersStatus]);

  useEffect(() => {
    if (!activeCyclone || !valLayersStatus) return;
    if (valLayersStatus === 'pending')
      addLog('m11', `Fetching Module 11 validation layers for ${activeCyclone}…`);
    else if (valLayersStatus === 'success')
      addLog('m11', `✅ Module 11 validation layers loaded for ${activeCyclone}`);
    else if (valLayersStatus === 'error')
      addLog('m11', `❌ Module 11 validation failed for ${activeCyclone}`);
  }, [activeCyclone, valLayersStatus]);

  useEffect(() => {
    if (!activeCyclone || !reportSummaryStatus) return;
    if (reportSummaryStatus === 'pending')
      addLog('m12', `Generating Module 12 report for ${activeCyclone}…`);
    else if (reportSummaryStatus === 'success')
      addLog('m12', `✅ Module 12 report ready for ${activeCyclone}`);
    else if (reportSummaryStatus === 'error')
      addLog('m12', `❌ Module 12 report generation failed for ${activeCyclone}`);
  }, [activeCyclone, reportSummaryStatus]);

  return (
    <div className="flex h-32 shrink-0 border-t border-[var(--border-subtle)] bg-[var(--surface-1)]/80 text-xs backdrop-blur-md">
      {/* Dynamic play scrubber panel */}
      <div className="flex-1 flex flex-col justify-between p-3 border-r border-[var(--border-subtle)] select-none">
        {total === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-[var(--text-tertiary)] gap-1">
            <span className="text-sm">⏳ Timeline Inactive</span>
            <span>Select a cyclone and load Track layers to enable time animations.</span>
          </div>
        ) : (
          <>
            {/* Top Row: Timestamps & Storm stats */}
            <div className="flex items-center justify-between">
              <div>
                <span className="font-semibold text-[var(--text-secondary)] uppercase text-[10px] tracking-wider mr-2">
                  Active Timeline:
                </span>
                <span className="font-mono text-[11px] text-cyan-400 font-semibold">
                  {_animationFrame !== null && features[_animationFrame]?.properties?.ISO_TIME
                    ? new Date(features[_animationFrame].properties.ISO_TIME).toLocaleString('en-IN', {
                        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC'
                      }) + ' UTC'
                    : 'Timeline stopped'}
                </span>
              </div>
              <div className="flex items-center gap-2.5">
                {_animationFrame !== null && (
                  <>
                    <span style={{ color: windColor(features[_animationFrame]?.properties?.USA_WIND ?? 0) }} className="font-bold">
                      {features[_animationFrame]?.properties?.USA_WIND ?? 0} kt wind
                    </span>
                    <span className="text-[var(--text-secondary)] font-mono">
                      {features[_animationFrame]?.properties?.USA_PRES ? `${features[_animationFrame].properties.USA_PRES} hPa` : ''}
                    </span>
                    {features[_animationFrame]?.properties?.USA_STATUS && (
                      <span className="rounded bg-white/10 px-1 py-0.5 text-[8px] text-[var(--text-secondary)] font-bold uppercase tracking-wider">
                        {features[_animationFrame].properties.USA_STATUS}
                      </span>
                    )}
                    {getFloodProgress(_animationFrame) > 0 && (
                      <span className="rounded bg-blue-950/60 border border-blue-900 px-1 py-0.5 text-[8px] text-blue-300 font-bold uppercase tracking-wider">
                        🌊 Flood Crossfade: {Math.round(getFloodProgress(_animationFrame) * 100)}%
                      </span>
                    )}
                  </>
                )}
              </div>
            </div>

            {/* Middle Row: Timeline track slider bar */}
            <div className="relative my-2">
              <input
                type="range" min={0} max={total - 1} value={_animationFrame ?? 0}
                onChange={e => {
                  setPlaying(false);
                  _setAnimationFrame(Number(e.target.value));
                }}
                className="w-full h-1.5 accent-cyan-500 cursor-pointer bg-[var(--surface-2)] rounded-lg appearance-none"
              />
              {/* Event (landfall) highlight on timeline track */}
              {evtStart && evtEnd && (
                (() => {
                  const t0 = new Date(evtStart).getTime();
                  const t1 = new Date(evtEnd).getTime();
                  const idx0 = timestamps.findIndex(t => t >= t0);
                  const idx1 = timestamps.findIndex(t => t >= t1);
                  if (idx0 !== -1 && idx1 !== -1) {
                    const pct0 = (idx0 / (total - 1)) * 100;
                    const pct1 = (idx1 / (total - 1)) * 100;
                    return (
                      <div
                        className="absolute top-0 h-1.5 rounded bg-orange-500/25 pointer-events-none"
                        style={{ left: `${pct0}%`, width: `${pct1 - pct0}%` }}
                      />
                    );
                  }
                  return null;
                })()
              )}
            </div>

            {/* Bottom Row: Controls play, speed and frames */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => { setPlaying(false); _setAnimationFrame(prev => Math.max(0, (prev ?? 0) - 1)); }}
                  className="rounded bg-[var(--surface-2)] hover:bg-[var(--surface-3)] p-1 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition"
                  title="Step frame back"
                >
                  ⏮
                </button>
                <button
                  onClick={() => {
                    if (_animationFrame === null || _animationFrame >= total - 1) {
                      _setAnimationFrame(0);
                    }
                    setPlaying(p => !p);
                  }}
                  className="rounded bg-cyan-600 hover:bg-cyan-500 px-3 py-1 font-bold text-white transition flex items-center gap-1"
                >
                  {playing ? '⏸ PAUSE' : '▶ PLAY'}
                </button>
                <button
                  onClick={() => { setPlaying(false); _setAnimationFrame(prev => Math.min(total - 1, (prev ?? 0) + 1)); }}
                  className="rounded bg-[var(--surface-2)] hover:bg-[var(--surface-3)] p-1 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition"
                  title="Step frame forward"
                >
                  ⏭
                </button>
                <button
                  onClick={() => { setPlaying(false); _setAnimationFrame(null); }}
                  className="rounded bg-red-950/40 border border-red-900/60 px-2 py-1 text-red-400 hover:bg-red-900 hover:text-white transition font-bold"
                  title="Reset track animation"
                >
                  ✕ STOP
                </button>
              </div>

              <span className="font-mono text-[10px] text-[var(--text-tertiary)]">
                Frame {_animationFrame !== null ? _animationFrame + 1 : 0} / {total}
              </span>

              <div className="flex items-center gap-1">
                <span className="text-[var(--text-tertiary)] mr-1">Speed:</span>
                {([0.5, 1, 2, 4] as const).map(s => (
                  <button
                    key={s}
                    onClick={() => setSpeed(s)}
                    className={`rounded px-2 py-0.5 text-[10px] font-mono transition ${
                      speed === s ? 'bg-cyan-600 text-white font-bold' : 'bg-[var(--surface-2)] text-[var(--text-tertiary)] hover:bg-[var(--surface-3)]'
                    }`}
                  >{s}×</button>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Logs Console */}
      <div className="w-80 shrink-0 overflow-y-auto p-2 font-mono border-l border-[var(--border-subtle)]">
        {logs.length === 0 && <p className="text-[var(--text-tertiary)]">Waiting for activity logs…</p>}
        {logs.map((l, i) => (
          <p key={i} className="text-[var(--text-secondary)] leading-normal">
            <span className="text-[var(--text-tertiary)]">[{l.time}]</span> {l.message}
          </p>
        ))}
      </div>
    </div>
  );
}

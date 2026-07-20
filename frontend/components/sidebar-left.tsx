'use client';

import { useState } from 'react';
import { API_BASE } from '@/lib/api';
import type {
  StudyAreaLayerKey, StudyAreaResponse, CycloneInfo,
  MeteorologyLayersResponse, TrackLayersResponse,
  FloodLayersResponse, HazardLayersResponse,
  VegLayersResponse, LulcLayersResponse, PopLayersResponse,
  MHLayersResponse, ValidationLayersResponse,
} from '@/lib/api';
import type { BasemapId, PhaseId } from '@/lib/map-types';

// ── Layer definitions ────────────────────────────────────────────────────────

const MODULE1_LAYERS:  Array<{ key: StudyAreaLayerKey; label: string }> = [
  { key: 'studyArea',         label: 'Study buffer (250 km)' },
  { key: 'affectedDistricts', label: 'Affected districts' },
  { key: 'landfall',          label: 'Landfall point' },
  { key: 'india',             label: 'India (outline)' },
  { key: 'reportingArea',     label: 'Reporting area' },
  { key: 'states',            label: 'States (outline)' },
  { key: 'districts',         label: 'Districts (outline)' },
];
const METEOROLOGY_LAYERS = [
  { key: 'peakWind', label: 'Peak Wind Speed' }, { key: 'tempAnomaly', label: 'Temperature Anomaly' },
  { key: 'humidity', label: 'Relative Humidity' }, { key: 'eventRainfall', label: 'Event Rainfall' },
  { key: 'rainSeverity', label: 'Rainfall Severity' }, { key: 'heavyRain', label: 'Heavy Rain (>100 mm)' },
  { key: 'vHeavyRain', label: 'V. Heavy Rain (>150 mm)' },
];
const TRACK_LAYERS = [
  { key: 'cycloneTrack', label: 'Cyclone Track' }, { key: 'corridor50km', label: 'Storm Surge (50 km)' },
  { key: 'corridor100km', label: 'Multi-Hazard (100 km)' }, { key: 'corridor250km', label: 'Rainfall/Flood (250 km)' },
  { key: 'rainfallFootprint', label: 'Rainfall Footprint' },
];
const FLOOD_LAYERS = [
  { key: 'floodExtent', label: 'Flood Extent (SAR)' }, { key: 'floodDepth', label: 'Flood Depth Proxy' },
  { key: 'sarPre', label: 'SAR Pre-event' }, { key: 'sarPost', label: 'SAR Post-event' }, { key: 'sarDiff', label: 'SAR Backscatter Diff' },
];
const HAZARD_LAYERS = [
  { key: 'hazardIndex', label: '🔴 Composite Hazard Index' }, { key: 'hazardClass', label: '🔴 Hazard Class (1-5)' },
  { key: 'surgeIndex', label: '🟠 Storm Surge Index' }, { key: 'surgeClass', label: '🟠 Surge Class (1-5)' },
  { key: 'coastalZone', label: '🔵 Coastal Zone (40 km)' }, { key: 'baseCoastalRisk', label: 'Base Coastal Risk' },
  { key: 'coastDistance', label: 'Distance to Coast' }, { key: 'elevation', label: 'Elevation (DEM)' },
  { key: 'slope', label: 'Slope' }, { key: 'hillshade', label: 'Hillshade' },
  { key: 'eventFactor', label: 'Event Factor' }, { key: 'rainRisk', label: 'Rainfall Risk' },
  { key: 'populationRisk', label: 'Population Risk' }, { key: 'landCoverRisk', label: 'Land Cover Risk' },
];
const VEG_LAYERS = [
  { key: 'damageClass', label: '🌿 Damage Class (1-4)' }, { key: 'dNDVI', label: '🌿 ΔNDVI (Veg Change)' },
  { key: 'dNBR', label: 'ΔNBR (Burn Ratio)' }, { key: 'preNDVI', label: 'NDVI Pre-event' }, { key: 'postNDVI', label: 'NDVI Post-event' },
];
const LULC_LAYERS = [
  { key: 'landCover', label: '🗺 Land Cover (ESA WorldCover)' }, { key: 'lulcImpactScore', label: '🗺 LULC Impact Score' },
  { key: 'impactType', label: '🗺 Impact Type (flood/veg/both)' }, { key: 'floodedLULC', label: 'Flooded Land Cover' },
  { key: 'damagedLULC', label: 'Veg-Damaged Land Cover' },
];
const POP_LAYERS = [
  { key: 'popDensity', label: '👥 Population Density' }, { key: 'popVuln', label: '👥 Vulnerability Index' },
  { key: 'popFlooded', label: '👥 Population Flooded' }, { key: 'popHighHaz', label: '👥 Pop in High Hazard Zone' },
  { key: 'popVegDmg', label: 'Pop — Veg Damage Zone' }, { key: 'popCount', label: 'Population Count (GPW)' },
];
const MH_LAYERS = [
  { key: 'mhIndex', label: '⚠️ Multi-Hazard Index (Composite)' }, { key: 'mhClass', label: '⚠️ Multi-Hazard Class (1-5)' },
  { key: 'floodRisk', label: 'Flood Risk Component' }, { key: 'vegRisk', label: 'Vegetation Risk Component' },
  { key: 'popRisk', label: 'Population Risk Component' },
];
const VAL_LAYERS = [
  { key: 'confusionMap', label: '✅ Confusion Map (TP/FP/FN/TN)' }, { key: 'optFlood', label: '✅ Optical Flood (Landsat MNDWI)' },
  { key: 'mndwi', label: 'MNDWI (Landsat post-event)' }, { key: 'lsDNDVI', label: 'Landsat dNDVI (Validation)' },
  { key: 'vegAgreement', label: 'Veg Agreement (S-2 vs L-8)' },
];

// Analysis panel: module → layer keys
const MODULE_ANALYSIS = [
  { label: 'M1 Study Area',    keys: ['studyArea','affectedDistricts','landfall','india','reportingArea','states','districts'] },
  { label: 'M2 Meteorology',   keys: ['peakWind','tempAnomaly','humidity','eventRainfall','rainSeverity','heavyRain','vHeavyRain'] },
  { label: 'M3 Track',         keys: ['cycloneTrack','corridor50km','corridor100km','corridor250km','rainfallFootprint'] },
  { label: 'M5 Flood',         keys: ['floodExtent','floodDepth','sarPre','sarPost','sarDiff'] },
  { label: 'M6 Hazard',        keys: ['hazardIndex','hazardClass','surgeIndex','surgeClass','elevation','slope','hillshade'] },
  { label: 'M7 Vegetation',    keys: ['damageClass','dNDVI','dNBR','preNDVI','postNDVI'] },
  { label: 'M8 LULC',          keys: ['landCover','lulcImpactScore','impactType','floodedLULC','damagedLULC'] },
  { label: 'M9 Population',    keys: ['popDensity','popVuln','popFlooded','popHighHaz','popVegDmg','popCount'] },
  { label: 'M10 Multi-Hazard', keys: ['mhIndex','mhClass','floodRisk','vegRisk','popRisk'] },
  { label: 'M11 Validation',   keys: ['confusionMap','optFlood','mndwi','lsDNDVI','vegAgreement'] },
];

const DEFAULT_VISIBLE = new Set(['india', 'landfall', 'affectedDistricts', 'studyArea']);
const ALL_KEYS = MODULE_ANALYSIS.flatMap(m => m.keys);

// ── Component ────────────────────────────────────────────────────────────────

export function SidebarLeft({
  studyArea, isLoading, visibleLayers, onToggleLayer,
  meteorologyLayers, meteorologyLayersLoading,
  trackLayers, trackLayersLoading,
  floodLayers, floodLayersLoading,
  hazardLayers, hazardLayersLoading,
  vegLayers, vegLayersLoading,
  lulcLayers, lulcLayersLoading,
  popLayers, popLayersLoading,
  mhLayers, mhLayersLoading,
  valLayers, valLayersLoading,
  reportReady, reportLoading,
  activeCyclone, activeCycloneInfo,
  basemap, onBasemapChange,
  rasterOpacity, onOpacityChange,
  phase, onPhaseChange,
  onResetLayers,
  showLegend, onShowLegendChange,
}: {
  studyArea?: StudyAreaResponse; isLoading: boolean;
  visibleLayers: Set<string>; onToggleLayer: (key: string) => void;
  meteorologyLayers?: MeteorologyLayersResponse; meteorologyLayersLoading?: boolean;
  trackLayers?: TrackLayersResponse;             trackLayersLoading?: boolean;
  floodLayers?: FloodLayersResponse;             floodLayersLoading?: boolean;
  hazardLayers?: HazardLayersResponse;           hazardLayersLoading?: boolean;
  vegLayers?: VegLayersResponse;                 vegLayersLoading?: boolean;
  lulcLayers?: LulcLayersResponse;               lulcLayersLoading?: boolean;
  popLayers?: PopLayersResponse;                 popLayersLoading?: boolean;
  mhLayers?: MHLayersResponse;                   mhLayersLoading?: boolean;
  valLayers?: ValidationLayersResponse;          valLayersLoading?: boolean;
  reportReady?: boolean;                         reportLoading?: boolean;
  activeCyclone?: string | null;
  activeCycloneInfo?: CycloneInfo;
  basemap?: BasemapId;        onBasemapChange?: (b: BasemapId) => void;
  rasterOpacity?: number;     onOpacityChange?: (v: number) => void;
  phase?: PhaseId;            onPhaseChange?: (p: PhaseId) => void;
  onResetLayers?: () => void;
  showLegend?: boolean;       onShowLegendChange?: (show: boolean) => void;
}) {
  const [openSection, setOpenSection] = useState<string>('Layers');

  // Defaults for optional map control props
  const _basemap       = basemap       ?? 'dark';
  const _rasterOpacity = rasterOpacity ?? 0.85;
  const _phase         = phase         ?? 'all';
  const _showLegend    = showLegend    ?? false;
  const _onBasemap     = onBasemapChange ?? (() => {});
  const _onOpacity     = onOpacityChange ?? (() => {});
  const _onPhase       = onPhaseChange   ?? (() => {});
  const _onReset       = onResetLayers   ?? (() => {});
  const _onLegend      = onShowLegendChange ?? (() => {});

  const totalActive = ALL_KEYS.filter(k => visibleLayers.has(k)).length;
  const dates       = activeCycloneInfo?.dates;

  function clearAllLayers() { ALL_KEYS.forEach(k => { if (visibleLayers.has(k)) onToggleLayer(k); }); }
  function resetLayers()    { _onReset(); }
  function toggleModule(keys: string[], visible: boolean) {
    keys.forEach(k => { const is = visibleLayers.has(k); if (visible && !is) onToggleLayer(k); if (!visible && is) onToggleLayer(k); });
  }

  return (
    <aside className="w-72 shrink-0 overflow-y-auto border-r border-[var(--border-subtle)] bg-[var(--surface-1)]/60 p-3 text-sm backdrop-blur-md">
      {/* Study area summary */}
      <Section title="Study area" open={openSection === 'Study area'} onToggle={t => setOpenSection(t ? 'Study area' : '')}>
        {isLoading && <SkeletonLines n={3} />}
        {studyArea?.stats && (
          <dl className="space-y-1.5">
            <Stat label="Landfall"       value={`${studyArea.stats.landfall ?? '—'}, ${studyArea.stats.landfallDate ?? ''}`} />
            <Stat label="Study area"     value={`${(studyArea.stats.studyArea_km2 ?? 0).toFixed(1)} km²`} />
            <Stat label="Reporting area" value={`${(studyArea.stats.reportingArea_km2 ?? 0).toFixed(1)} km²`} />
            <Stat label="Districts"      value={String(studyArea.stats.districtCount ?? 0)} />
          </dl>
        )}
        {!studyArea && !isLoading && <p className="text-xs text-[var(--text-tertiary)]">Select a cyclone to begin.</p>}
      </Section>

      {/* Layers */}
      <Section title="Layers" open={openSection === 'Layers'} onToggle={t => setOpenSection(t ? 'Layers' : '')}>
        <LayerGroup title="Module 1 — Study Area" accent="cyan">
          {MODULE1_LAYERS.map(({ key, label }) => (
            <LayerRow key={key} layerKey={key} label={label} checked={visibleLayers.has(key)} disabled={!studyArea} onToggle={onToggleLayer} />
          ))}
        </LayerGroup>
        <LayerGroup title="Module 2 — Meteorology" accent="sky" loading={meteorologyLayersLoading} ready={!!meteorologyLayers} idle={!meteorologyLayersLoading && !meteorologyLayers}>
          {METEOROLOGY_LAYERS.map(({ key, label }) => (
            <LayerRow key={key} layerKey={key} label={label} checked={visibleLayers.has(key)} onToggle={onToggleLayer} />
          ))}
        </LayerGroup>
        <LayerGroup title="Module 3 — Track & Corridors" accent="yellow" loading={trackLayersLoading} ready={!!trackLayers} idle={!trackLayersLoading && !trackLayers}>
          {TRACK_LAYERS.map(({ key, label }) => (
            <LayerRow key={key} layerKey={key} label={label} checked={visibleLayers.has(key)} onToggle={onToggleLayer} />
          ))}
        </LayerGroup>
        <LayerGroup title="Module 5 — Flood Mapping (SAR)" accent="blue" loading={floodLayersLoading} ready={!!floodLayers} idle={!floodLayersLoading && !floodLayers}>
          {FLOOD_LAYERS.map(({ key, label }) => (
            <LayerRow key={key} layerKey={key} label={label} checked={visibleLayers.has(key)} onToggle={onToggleLayer} />
          ))}
        </LayerGroup>
        <LayerGroup title="Module 6 — Hazard Index" accent="red" loading={hazardLayersLoading} ready={!!hazardLayers} idle={!hazardLayersLoading && !hazardLayers}>
          {HAZARD_LAYERS.map(({ key, label }) => (
            <LayerRow key={key} layerKey={key} label={label} checked={visibleLayers.has(key)} onToggle={onToggleLayer} />
          ))}
        </LayerGroup>
        <LayerGroup title="Module 7 — Vegetation Damage" accent="green" loading={vegLayersLoading} ready={!!vegLayers} idle={!vegLayersLoading && !vegLayers}>
          {VEG_LAYERS.map(({ key, label }) => (
            <LayerRow key={key} layerKey={key} label={label} checked={visibleLayers.has(key)} onToggle={onToggleLayer} />
          ))}
        </LayerGroup>
        <LayerGroup title="Module 8 — LULC Impact" accent="purple" loading={lulcLayersLoading} ready={!!lulcLayers} idle={!lulcLayersLoading && !lulcLayers}>
          {LULC_LAYERS.map(({ key, label }) => (
            <LayerRow key={key} layerKey={key} label={label} checked={visibleLayers.has(key)} onToggle={onToggleLayer} />
          ))}
        </LayerGroup>
        <LayerGroup title="Module 9 — Population Exposure" accent="orange" loading={popLayersLoading} ready={!!popLayers} idle={!popLayersLoading && !popLayers}>
          {POP_LAYERS.map(({ key, label }) => (
            <LayerRow key={key} layerKey={key} label={label} checked={visibleLayers.has(key)} onToggle={onToggleLayer} />
          ))}
        </LayerGroup>
        <LayerGroup title="Module 10 — Multi-Hazard Summary" accent="rose" loading={mhLayersLoading} ready={!!mhLayers} idle={!mhLayersLoading && !mhLayers}>
          {MH_LAYERS.map(({ key, label }) => (
            <LayerRow key={key} layerKey={key} label={label} checked={visibleLayers.has(key)} onToggle={onToggleLayer} />
          ))}
        </LayerGroup>
        <LayerGroup title="Module 11 — Validation & Accuracy" accent="teal" loading={valLayersLoading} ready={!!valLayers} idle={!valLayersLoading && !valLayers}>
          {VAL_LAYERS.map(({ key, label }) => (
            <LayerRow key={key} layerKey={key} label={label} checked={visibleLayers.has(key)} onToggle={onToggleLayer} />
          ))}
        </LayerGroup>
      </Section>

      {/* Reports & Export */}
      <Section title="Reports & Export" open={openSection === 'Reports & Export'} onToggle={t => setOpenSection(t ? 'Reports & Export' : '')}>
        {reportLoading && !reportReady && <p className="text-xs text-[var(--text-tertiary)] animate-pulse">⏳ Generating report…</p>}
        {reportReady && <p className="text-xs text-emerald-400">✅ Report ready — see right panel.</p>}
        {!reportReady && !reportLoading && <p className="text-xs text-[var(--text-tertiary)]">Will auto-generate after study area loads.</p>}
      </Section>

      {/* ── Analysis ── */}
      <Section title="Analysis" open={openSection === 'Analysis'} onToggle={t => setOpenSection(t ? 'Analysis' : '')}>
        <div className="space-y-2">
          {/* Active layer count badge */}
          <div className="flex items-center justify-between rounded bg-[var(--surface-2)] px-2 py-1.5">
            <span className="text-[var(--text-secondary)]">Active layers</span>
            <span className="rounded-full bg-cyan-600 px-2 py-0.5 text-xs font-bold text-white">{totalActive}</span>
          </div>
          {/* Quick actions */}
          <div className="flex gap-1.5">
            <button
              onClick={resetLayers}
              className="flex-1 rounded bg-[var(--surface-2)] px-2 py-1 text-xs text-[var(--text-secondary)] hover:bg-cyan-900/40 hover:text-cyan-300 transition"
            >↺ Reset</button>
            <button
              onClick={clearAllLayers}
              className="flex-1 rounded bg-[var(--surface-2)] px-2 py-1 text-xs text-[var(--text-secondary)] hover:bg-red-900/30 hover:text-red-400 transition"
            >✕ Clear all</button>
          </div>
          {/* Per-module breakdown */}
          <div className="space-y-1 pt-1">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">By module</p>
            {MODULE_ANALYSIS.map(mod => {
              const active = mod.keys.filter(k => visibleLayers.has(k)).length;
              const total  = mod.keys.length;
              const pct    = total > 0 ? (active / total) * 100 : 0;
              return (
                <div key={mod.label} className="group flex items-center gap-1.5 text-[10px]">
                  <span className="w-28 shrink-0 text-[var(--text-tertiary)]">{mod.label}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--surface-2)]">
                    <div className="h-full rounded-full bg-cyan-600 transition-all" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="w-8 text-right font-mono text-[var(--text-tertiary)]">{active}/{total}</span>
                  {/* all/none quick toggle */}
                  <button
                    onClick={() => toggleModule(mod.keys, active < total)}
                    className="opacity-0 group-hover:opacity-100 text-[8px] text-cyan-400 hover:underline transition"
                  >{active < total ? 'all' : 'off'}</button>
                </div>
              );
            })}
          </div>
        </div>
      </Section>

      {/* ── Time Slider ── */}
      <Section title="Time slider" open={openSection === 'Time slider'} onToggle={t => setOpenSection(t ? 'Time slider' : '')}>
        {!dates ? (
          <p className="text-xs text-[var(--text-tertiary)]">Select a cyclone to see date windows.</p>
        ) : (
          <div className="space-y-3">
            {/* Phase filter buttons */}
            <div>
              <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">Phase filter</p>
              <div className="flex gap-1">
                {(['all', 'pre', 'post'] as PhaseId[]).map(p => (
                  <button
                    key={p}
                    onClick={() => _onPhase(p)}
                    className={`flex-1 rounded py-1 text-xs font-medium capitalize transition ${
                      _phase === p
                        ? 'bg-cyan-600 text-white'
                        : 'bg-[var(--surface-2)] text-[var(--text-secondary)] hover:bg-cyan-900/40 hover:text-cyan-300'
                    }`}
                  >{p === 'all' ? 'All' : p === 'pre' ? 'Pre-event' : 'Post-event'}</button>
                ))}
              </div>
              {_phase !== 'all' && (
                <p className="mt-1.5 text-[10px] text-[var(--text-tertiary)]">
                  {_phase === 'pre'
                    ? '⚡ Showing pre-event baseline layers only'
                    : '⚡ Showing post-event impact layers only'}
                </p>
              )}
            </div>
            {/* Date timeline */}
            <div className="space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">Date windows</p>
              <DateRange accent="sky"    icon="📡" label="Pre-event"    start={dates.preS} end={dates.preE} />
              <DateRange accent="yellow" icon="🌀" label="Event window" start={dates.evtS} end={dates.evtE} />
              <DateRange accent="green"  icon="🛰" label="Post-event"   start={dates.postS} end={dates.postE} />
            </div>
            {/* Visual timeline bar */}
            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">Timeline</p>
              <div className="relative flex h-5 w-full items-center gap-0.5 rounded overflow-hidden text-[8px]">
                <div className="flex-1 bg-sky-800/60 flex items-center justify-center text-sky-300">PRE</div>
                <div className="w-6 bg-yellow-600/80 flex items-center justify-center text-yellow-100">EVT</div>
                <div className="flex-1 bg-emerald-800/60 flex items-center justify-center text-emerald-300">POST</div>
              </div>
              <div className="mt-0.5 flex justify-between text-[9px] text-[var(--text-tertiary)]">
                <span>{dates.preS.slice(0, 7)}</span>
                <span>{dates.evtS.slice(5, 10)}</span>
                <span>{dates.postE.slice(0, 7)}</span>
              </div>
            </div>
          </div>
        )}
      </Section>

      {/* ── Downloads ── */}
      <Section title="Downloads" open={openSection === 'Downloads'} onToggle={t => setOpenSection(t ? 'Downloads' : '')}>
        {!activeCyclone ? (
          <p className="text-xs text-[var(--text-tertiary)]">Select a cyclone to enable downloads.</p>
        ) : (
          <div className="space-y-1.5">
            <DownloadLink
              href={`${API_BASE}/api/modules/12/reports/${activeCyclone}/summary`}
              icon="📋" label="Report JSON" desc="Summary stats for all modules"
            />
            <DownloadLink
              href={`${API_BASE}/api/modules/12/reports/${activeCyclone}/export`}
              icon="📊" label="District CSV" desc="Hazard · flood · population metrics"
            />
            <DownloadLink
              href={`${API_BASE}/api/modules/1/study-area/${activeCyclone}`}
              icon="🗺" label="Study Area JSON" desc="District list + tile URLs"
            />
            <DownloadLink
              href={`${API_BASE}/docs`}
              icon="📖" label="API Docs (Swagger)" desc="All 24 endpoints, interactive"
              external
            />
            <div className="rounded border border-dashed border-[var(--border-subtle)] p-2 text-[10px] text-[var(--text-tertiary)]">
              💡 GeoTIFF exports — open any layer URL in GEE Code Editor or use the Python EE client.
            </div>
          </div>
        )}
      </Section>

      {/* ── Settings ── */}
      <Section title="Settings" open={openSection === 'Settings'} onToggle={t => setOpenSection(t ? 'Settings' : '')}>
        <div className="space-y-4">
          {/* Basemap */}
          <div>
            <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">Basemap</p>
            <div className="grid grid-cols-3 gap-1">
              {([
                { id: 'dark',      icon: '🌑', label: 'Dark' },
                { id: 'satellite', icon: '🛰',  label: 'Satellite' },
                { id: 'streets',   icon: '🗺',  label: 'Streets' },
              ] as { id: BasemapId; icon: string; label: string }[]).map(b => (
                <button
                  key={b.id}
                  onClick={() => _onBasemap(b.id)}
                  className={`rounded py-1.5 text-[11px] font-medium transition ${
                    _basemap === b.id
                      ? 'bg-cyan-600 text-white ring-1 ring-cyan-400'
                      : 'bg-[var(--surface-2)] text-[var(--text-secondary)] hover:bg-[var(--surface-2)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  <span className="block text-base leading-none">{b.icon}</span>
                  {b.label}
                </button>
              ))}
            </div>
          </div>
          {/* Raster opacity */}
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">Layer Opacity</p>
              <span className="font-mono text-xs text-cyan-400">{Math.round(_rasterOpacity * 100)}%</span>
            </div>
            <input
              type="range" min={0} max={1} step={0.05} value={_rasterOpacity}
              onChange={e => _onOpacity(parseFloat(e.target.value))}
              className="w-full accent-cyan-500"
            />
            <div className="mt-0.5 flex justify-between text-[9px] text-[var(--text-tertiary)]">
              <span>0%</span><span>50%</span><span>100%</span>
            </div>
          </div>
        </div>
      </Section>
    </aside>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

const ACCENT_COLORS: Record<string, string> = {
  cyan: 'text-cyan-400', sky: 'text-sky-400', yellow: 'text-yellow-400',
  blue: 'text-blue-400', red: 'text-red-400', green: 'text-green-400',
  purple: 'text-purple-400', orange: 'text-orange-400', rose: 'text-rose-400', teal: 'text-teal-400',
};

function Section({ title, open, onToggle, children }: {
  title: string; open: boolean; onToggle: (open: boolean) => void; children: React.ReactNode;
}) {
  return (
    <div className="mb-2 border-b border-[var(--border-subtle)]">
      <button
        onClick={() => onToggle(!open)}
        className="flex w-full items-center justify-between py-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition"
      >
        {title}
        <span className="text-[10px] text-[var(--text-tertiary)]">{open ? '▲' : '▼'}</span>
      </button>
      {open && <div className="pb-3">{children}</div>}
    </div>
  );
}

function LayerGroup({ title, accent = 'cyan', loading, ready, idle, children }: {
  title: string; accent?: string; loading?: boolean; ready?: boolean; idle?: boolean; children: React.ReactNode;
}) {
  return (
    <div className="mt-3 border-t border-[var(--border-subtle)] pt-2">
      <p className={`mb-1 text-xs uppercase tracking-wide font-semibold ${ACCENT_COLORS[accent] ?? 'text-[var(--text-secondary)]'}`}>{title}</p>
      {idle  && !loading && !ready && (
        <p className="mb-1 text-[10px] text-[var(--text-tertiary)] italic">☁ Enable a layer below to load from Earth Engine</p>
      )}
      {loading && !ready && (
        <p className="mb-1 text-xs text-amber-400 animate-pulse">⏳ Fetching from Earth Engine…</p>
      )}
      {children}
    </div>
  );
}

function LayerRow({ layerKey, label, checked, disabled, onToggle }: {
  layerKey: string; label: string; checked: boolean; disabled?: boolean; onToggle: (k: string) => void;
}) {
  return (
    <li className="flex items-center gap-2 py-0.5">
      <input type="checkbox" checked={checked} onChange={() => onToggle(layerKey)} disabled={disabled} className="accent-[var(--accent-cyan)] shrink-0" />
      <span className={`text-xs ${disabled ? 'text-[var(--text-tertiary)]' : 'text-[var(--text-secondary)]'}`}>{label}</span>
    </li>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-xs text-[var(--text-tertiary)]">{label}</dt>
      <dd className="text-right text-xs font-mono text-[var(--text-primary)]">{value}</dd>
    </div>
  );
}

function SkeletonLines({ n }: { n: number }) {
  return (
    <div className="space-y-1.5">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="h-3 animate-pulse rounded bg-[var(--surface-2)]" />
      ))}
    </div>
  );
}

function DateRange({ icon, label, start, end, accent }: {
  icon: string; label: string; start: string; end: string; accent: string;
}) {
  const accentBg: Record<string, string> = { sky: 'bg-sky-900/30', yellow: 'bg-yellow-900/30', green: 'bg-emerald-900/30' };
  const accentTxt: Record<string, string> = { sky: 'text-sky-300', yellow: 'text-yellow-300', green: 'text-emerald-300' };
  return (
    <div className={`rounded p-1.5 ${accentBg[accent] ?? 'bg-[var(--surface-2)]'}`}>
      <p className={`text-[10px] font-semibold ${accentTxt[accent] ?? 'text-[var(--text-secondary)]'}`}>{icon} {label}</p>
      <p className="font-mono text-[9px] text-[var(--text-tertiary)]">{start} → {end}</p>
    </div>
  );
}

function DownloadLink({ href, icon, label, desc, external }: {
  href: string; icon: string; label: string; desc: string; external?: boolean;
}) {
  return (
    <a
      href={href}
      download={!external}
      target={external ? '_blank' : undefined}
      rel="noopener noreferrer"
      className="flex items-center gap-2 rounded bg-[var(--surface-2)] px-2 py-2 transition hover:bg-cyan-900/30 hover:text-cyan-300"
    >
      <span className="text-base">{icon}</span>
      <div className="min-w-0">
        <p className="text-xs font-semibold text-[var(--text-primary)]">{label}</p>
        <p className="truncate text-[10px] text-[var(--text-tertiary)]">{desc}</p>
      </div>
      <span className="ml-auto text-[10px] text-[var(--text-tertiary)]">{external ? '↗' : '⬇'}</span>
    </a>
  );
}

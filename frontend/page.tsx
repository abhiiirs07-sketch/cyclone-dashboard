'use client';

import { useState, useCallback, useEffect } from 'react';
import { Header }       from '@/components/header';
import { SidebarLeft }  from '@/components/sidebar-left';
import { SidebarRight } from '@/components/sidebar-right';
import { BottomPanel }  from '@/components/bottom-panel';
import { MapView }      from '@/components/map-view';
import type { BasemapId, PhaseId } from '@/lib/map-types';
import {
  useCyclones,
  useStudyArea,
  useMeteorologyLayers, useMeteorologyStats,
  useTrackLayers,       useTrackStats,
  useFloodLayers,       useFloodStats,
  useHazardLayers,      useHazardStats,
  useVegLayers,         useVegStats,
  useLulcLayers,        useLulcStats,
  usePopLayers,         usePopStats,
  useMHLayers,          useMHStats,
  useValidationLayers,  useValidationStats,
  useReportSummary,
} from '@/lib/api';

// M1 loads always — they're the base map (lightweight GEE calls)
const DEFAULT_VISIBLE_LAYERS = ['india', 'landfall', 'affectedDistricts', 'studyArea'];

// Layer keys that belong to each module — used to decide when to fetch
const M2_KEYS  = ['peakWind','tempAnomaly','humidity','eventRainfall','rainSeverity','heavyRain','vHeavyRain'];
const M3_KEYS  = ['cycloneTrack','corridor50km','corridor100km','corridor250km','rainfallFootprint'];
const M5_KEYS  = ['floodExtent','floodDepth','sarPre','sarPost','sarDiff'];
const M6_KEYS  = ['hazardIndex','hazardClass','surgeIndex','surgeClass','coastalZone','baseCoastalRisk','coastDistance','elevation','slope','hillshade','eventFactor','rainRisk','populationRisk','landCoverRisk'];
const M7_KEYS  = ['damageClass','dNDVI','dNBR','preNDVI','postNDVI'];
const M8_KEYS  = ['landCover','lulcImpactScore','impactType','floodedLULC','damagedLULC'];
const M9_KEYS  = ['popDensity','popVuln','popFlooded','popHighHaz','popVegDmg','popCount'];
const M10_KEYS = ['mhIndex','mhClass','floodRisk','vegRisk','popRisk'];
const M11_KEYS = ['confusionMap','optFlood','mndwi','lsDNDVI','vegAgreement'];

/** Returns true if any of the given keys are currently visible (module is "active") */
function useModuleActive(visibleLayers: Set<string>, keys: string[]): boolean {
  return keys.some(k => visibleLayers.has(k));
}

/**
 * LOADING STRATEGY — 3 phases:
 *
 * Phase 0 (immediate): M1 Study Area — always loads, base map.
 * Phase 1 (on-demand): Layer URLs only when user enables that module's layers.
 * Phase 2 (15s delay): Stats for enabled modules (heavy GEE operations).
 *
 * This means: opening the dashboard shows the base map instantly.
 * Each module's tiles load only when you enable them — no wasted GEE calls.
 */
export default function DashboardPage() {
  const { data: cyclones } = useCyclones();
  const [selected,      setSelected]      = useState<string | null>(null);
  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(new Set(DEFAULT_VISIBLE_LAYERS));
  const [basemap,       setBasemap]       = useState<BasemapId>('dark');
  const [rasterOpacity, setRasterOpacity] = useState(0.90);
  const [phase,         setPhase]         = useState<PhaseId>('all');
  const [showLegend,    setShowLegend]    = useState(true);
  const [animFrame,     setAnimFrame]     = useState<number | null>(null);
  const [floodProgress, setFloodProgress] = useState(0);

  // Stats load 15s after page opens — gives layers time to appear first
  const [statsEnabled, setStatsEnabled] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setStatsEnabled(true), 15_000);
    return () => clearTimeout(t);
  }, []);

  const activeCyclone     = selected ?? cyclones?.[0]?.id ?? null;
  const activeCycloneInfo = cyclones?.find(c => c.id === activeCyclone);

  // ── Determine which modules are active (user has enabled at least one layer) ──
  const m2Active  = useModuleActive(visibleLayers, M2_KEYS);
  const m3Active  = useModuleActive(visibleLayers, M3_KEYS);
  const m5Active  = useModuleActive(visibleLayers, M5_KEYS);
  const m6Active  = useModuleActive(visibleLayers, M6_KEYS);
  const m7Active  = useModuleActive(visibleLayers, M7_KEYS);
  const m8Active  = useModuleActive(visibleLayers, M8_KEYS);
  const m9Active  = useModuleActive(visibleLayers, M9_KEYS);
  const m10Active = useModuleActive(visibleLayers, M10_KEYS);
  const m11Active = useModuleActive(visibleLayers, M11_KEYS);

  // ── Phase 0: M1 Study Area — always loads (base map) ─────────────────────
  const studyArea = useStudyArea(activeCyclone);

  // ── Phase 1: Layer URLs — LAZY, only when module is active ───────────────
  const metLayers    = useMeteorologyLayers(m2Active  ? activeCyclone : null);
  const trackLayers  = useTrackLayers(       m3Active  ? activeCyclone : null);
  const floodLayers  = useFloodLayers(       m5Active  ? activeCyclone : null);
  const hazardLayers = useHazardLayers(      m6Active  ? activeCyclone : null);
  const vegLayers    = useVegLayers(         m7Active  ? activeCyclone : null);
  const lulcLayers   = useLulcLayers(        m8Active  ? activeCyclone : null);
  const popLayers    = usePopLayers(         m9Active  ? activeCyclone : null);
  const mhLayers     = useMHLayers(          m10Active ? activeCyclone : null);
  const valLayers    = useValidationLayers(  m11Active ? activeCyclone : null);
  const reportSummary = useReportSummary(activeCyclone);

  // ── Phase 2: Stats — deferred 15s AND only when module is active ─────────
  const met2   = statsEnabled && m2Active;
  const met3   = statsEnabled && m3Active;
  const met5   = statsEnabled && m5Active;
  const met6   = statsEnabled && m6Active;
  const met7   = statsEnabled && m7Active;
  const met8   = statsEnabled && m8Active;
  const met9   = statsEnabled && m9Active;
  const met10  = statsEnabled && m10Active;
  const met11  = statsEnabled && m11Active;

  const metStats   = useMeteorologyStats(met2  ? activeCyclone : null);
  const trackStats = useTrackStats(      met3  ? activeCyclone : null);
  const floodStats = useFloodStats(      met5  ? activeCyclone : null);
  const hazardStats= useHazardStats(     met6  ? activeCyclone : null);
  const vegStats   = useVegStats(        met7  ? activeCyclone : null);
  const lulcStats  = useLulcStats(       met8  ? activeCyclone : null);
  const popStats   = usePopStats(        met9  ? activeCyclone : null);
  const mhStats    = useMHStats(         met10 ? activeCyclone : null);
  const valStats   = useValidationStats( met11 ? activeCyclone : null);

  // ── Helpers ───────────────────────────────────────────────────────────────
  const toggleLayer = useCallback((key: string) => {
    setVisibleLayers(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }, []);

  const resetLayers = useCallback(() => {
    setVisibleLayers(new Set(DEFAULT_VISIBLE_LAYERS));
  }, []);

  return (
    <div className="flex h-screen flex-col bg-[var(--surface-0)] text-[var(--text-primary)]">
      <Header
        cyclones={cyclones ?? []}
        selected={activeCyclone}
        onSelect={setSelected}
        activeCycloneInfo={activeCycloneInfo}
      />

      <div className="flex flex-1 overflow-hidden">
        <SidebarLeft
          studyArea={studyArea.data}
          isLoading={studyArea.isLoading}
          visibleLayers={visibleLayers}
          onToggleLayer={toggleLayer}
          meteorologyLayers={metLayers.data}
          meteorologyLayersLoading={m2Active && metLayers.isLoading}
          trackLayers={trackLayers.data}
          trackLayersLoading={m3Active && trackLayers.isLoading}
          floodLayers={floodLayers.data}
          floodLayersLoading={m5Active && floodLayers.isLoading}
          hazardLayers={hazardLayers.data}
          hazardLayersLoading={m6Active && hazardLayers.isLoading}
          vegLayers={vegLayers.data}
          vegLayersLoading={m7Active && vegLayers.isLoading}
          lulcLayers={lulcLayers.data}
          lulcLayersLoading={m8Active && lulcLayers.isLoading}
          popLayers={popLayers.data}
          popLayersLoading={m9Active && popLayers.isLoading}
          mhLayers={mhLayers.data}
          mhLayersLoading={m10Active && mhLayers.isLoading}
          valLayers={valLayers.data}
          valLayersLoading={m11Active && valLayers.isLoading}
          reportReady={!!reportSummary.data}
          reportLoading={reportSummary.isLoading}
          activeCyclone={activeCyclone}
          activeCycloneInfo={activeCycloneInfo}
          basemap={basemap}
          onBasemapChange={setBasemap}
          rasterOpacity={rasterOpacity}
          onOpacityChange={setRasterOpacity}
          phase={phase}
          onPhaseChange={setPhase}
          onResetLayers={resetLayers}
          showLegend={showLegend}
          onShowLegendChange={setShowLegend}
        />

        <main className="relative flex-1">
          <MapView
            cyclone={activeCycloneInfo}
            studyArea={studyArea.data}
            visibleLayers={visibleLayers}
            meteorologyLayers={metLayers.data}
            trackLayers={trackLayers.data}
            floodLayers={floodLayers.data}
            hazardLayers={hazardLayers.data}
            vegLayers={vegLayers.data}
            lulcLayers={lulcLayers.data}
            popLayers={popLayers.data}
            mhLayers={mhLayers.data}
            valLayers={valLayers.data}
            basemap={basemap}
            rasterOpacity={rasterOpacity}
            phase={phase}
            animationFrame={animFrame}
            floodProgress={floodProgress}
            showLegend={showLegend}
          />
        </main>

        <SidebarRight
          studyArea={studyArea.data}
          isLoading={studyArea.isLoading}
          error={studyArea.error}
          meteorologyStats={metStats.data}
          meteorologyStatsLoading={metStats.isLoading}
          meteorologyLayersReady={!!metLayers.data}
          trackStats={trackStats.data}
          trackStatsLoading={trackStats.isLoading}
          trackLayersReady={!!trackLayers.data}
          floodStats={floodStats.data}
          floodStatsLoading={floodStats.isLoading}
          floodLayersReady={!!floodLayers.data}
          hazardStats={hazardStats.data}
          hazardStatsLoading={hazardStats.isLoading}
          hazardLayersReady={!!hazardLayers.data}
          vegStats={vegStats.data}
          vegStatsLoading={vegStats.isLoading}
          vegLayersReady={!!vegLayers.data}
          lulcStats={lulcStats.data}
          lulcStatsLoading={lulcStats.isLoading}
          lulcLayersReady={!!lulcLayers.data}
          popStats={popStats.data}
          popStatsLoading={popStats.isLoading}
          popLayersReady={!!popLayers.data}
          mhStats={mhStats.data}
          mhStatsLoading={mhStats.isLoading}
          mhLayersReady={!!mhLayers.data}
          valStats={valStats.data}
          valStatsLoading={valStats.isLoading}
          valLayersReady={!!valLayers.data}
          reportSummary={reportSummary.data}
          reportLoading={reportSummary.isLoading}
          activeCyclone={activeCyclone}
        />
      </div>

      <BottomPanel
        activeCyclone={activeCyclone}
        studyAreaStatus={studyArea.status}
        trackLayersStatus={trackLayers.status}
        floodLayersStatus={floodLayers.status}
        hazardLayersStatus={hazardLayers.status}
        vegLayersStatus={vegLayers.status}
        lulcLayersStatus={lulcLayers.status}
        popLayersStatus={popLayers.status}
        mhLayersStatus={mhLayers.status}
        valLayersStatus={valLayers.status}
        reportSummaryStatus={reportSummary.status}
        trackLayers={trackLayers.data}
        evtStart={activeCycloneInfo?.dates?.evtS}
        evtEnd={activeCycloneInfo?.dates?.evtE}
        animationFrame={animFrame}
        setAnimationFrame={setAnimFrame}
        setFloodProgress={setFloodProgress}
      />
    </div>
  );
}

'use client';

import { useState, useCallback } from 'react';
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

const DEFAULT_VISIBLE_LAYERS = ['india', 'landfall', 'affectedDistricts', 'studyArea'];

export default function DashboardPage() {
  // ── State ──────────────────────────────────────────────────────────────────
  const { data: cyclones } = useCyclones();
  const [selected,      setSelected]      = useState<string | null>(null);
  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(new Set(DEFAULT_VISIBLE_LAYERS));
  const [basemap,       setBasemap]       = useState<BasemapId>('dark');
  const [rasterOpacity, setRasterOpacity] = useState(0.85);
  const [phase,         setPhase]         = useState<PhaseId>('all');
  const [showLegend,    setShowLegend]    = useState(true);
  const [animFrame,     setAnimFrame]     = useState<number | null>(null);
  const [floodProgress, setFloodProgress] = useState(0);

  const activeCyclone     = selected ?? cyclones?.[0]?.id ?? null;
  const activeCycloneInfo = cyclones?.find(c => c.id === activeCyclone);

  // ── Module 1 — Study Area ──────────────────────────────────────────────────
  const studyArea = useStudyArea(activeCyclone);

  // ── Module 2 — Meteorology ─────────────────────────────────────────────────
  const metLayers = useMeteorologyLayers(activeCyclone);
  const metStats  = useMeteorologyStats(activeCyclone);

  // ── Module 3 — Cyclone Track ───────────────────────────────────────────────
  const trackLayers = useTrackLayers(activeCyclone);
  const trackStats  = useTrackStats(activeCyclone);

  // ── Module 5 — Flood Mapping (SAR) ────────────────────────────────────────
  const floodLayers = useFloodLayers(activeCyclone);
  const floodStats  = useFloodStats(activeCyclone);

  // ── Module 6 — Terrain, Storm Surge & Hazard ──────────────────────────────
  const hazardLayers = useHazardLayers(activeCyclone);
  const hazardStats  = useHazardStats(activeCyclone);

  // ── Module 7 — Vegetation Damage ──────────────────────────────────────────
  const vegLayers = useVegLayers(activeCyclone);
  const vegStats  = useVegStats(activeCyclone);

  // ── Module 8 — LULC Impact ────────────────────────────────────────────────
  const lulcLayers = useLulcLayers(activeCyclone);
  const lulcStats  = useLulcStats(activeCyclone);

  // ── Module 9 — Population Exposure ───────────────────────────────────────
  const popLayers = usePopLayers(activeCyclone);
  const popStats  = usePopStats(activeCyclone);

  // ── Module 10 — Multi-Hazard Summary ─────────────────────────────────────
  const mhLayers = useMHLayers(activeCyclone);
  const mhStats  = useMHStats(activeCyclone);

  // ── Module 11 — Validation ────────────────────────────────────────────────
  const valLayers = useValidationLayers(activeCyclone);
  const valStats  = useValidationStats(activeCyclone);

  // ── Module 12 — Reports ───────────────────────────────────────────────────
  const reportSummary = useReportSummary(activeCyclone);

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
        {/* ── LEFT SIDEBAR ── */}
        <SidebarLeft
          studyArea={studyArea.data}
          isLoading={studyArea.isLoading}
          visibleLayers={visibleLayers}
          onToggleLayer={toggleLayer}
          meteorologyLayers={metLayers.data}
          meteorologyLayersLoading={metLayers.isLoading}
          trackLayers={trackLayers.data}
          trackLayersLoading={trackLayers.isLoading}
          floodLayers={floodLayers.data}
          floodLayersLoading={floodLayers.isLoading}
          hazardLayers={hazardLayers.data}
          hazardLayersLoading={hazardLayers.isLoading}
          vegLayers={vegLayers.data}
          vegLayersLoading={vegLayers.isLoading}
          lulcLayers={lulcLayers.data}
          lulcLayersLoading={lulcLayers.isLoading}
          popLayers={popLayers.data}
          popLayersLoading={popLayers.isLoading}
          mhLayers={mhLayers.data}
          mhLayersLoading={mhLayers.isLoading}
          valLayers={valLayers.data}
          valLayersLoading={valLayers.isLoading}
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

        {/* ── MAP ── */}
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

        {/* ── RIGHT SIDEBAR ── */}
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

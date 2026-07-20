'use client';

import { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { Header } from '@/components/header';
import { SidebarLeft } from '@/components/sidebar-left';
import { SidebarRight } from '@/components/sidebar-right';
import { BottomPanel } from '@/components/bottom-panel';
import { TimeSliderPanel } from '@/components/time-slider-panel';
import type { BasemapId, PhaseId } from '@/lib/map-types';

const MapView = dynamic(
  () => import('@/components/map-view').then((mod) => mod.MapView),
  {
    ssr: false,
    loading: () => (
      <div className="flex flex-1 items-center justify-center bg-[#0d1117] text-cyan-400 font-mono text-xs select-none">
        <span className="animate-pulse">🗺️ Initializing Interactive Map Engine…</span>
      </div>
    ),
  }
);
import {
  useCyclones, useStudyArea,
  useMeteorologyLayers, useMeteorologyStats,
  useTrackLayers, useTrackStats,
  useFloodLayers, useFloodStats,
  useHazardLayers, useHazardStats,
  useVegLayers, useVegStats,
  useLulcLayers, useLulcStats,
  usePopLayers, usePopStats,
  useMHLayers, useMHStats,
  useValidationLayers, useValidationStats,
  useReportSummary,
} from '@/lib/api';

const DEFAULT_VISIBLE_LAYERS = new Set(['india', 'landfall', 'affectedDistricts', 'studyArea']);

export default function DashboardPage() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  const { data: cyclones } = useCyclones();
  const [selected, setSelected]           = useState<string | null>(null);
  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(new Set(DEFAULT_VISIBLE_LAYERS));

  // Map controls state
  const [basemap, setBasemap]               = useState<BasemapId>('dark');
  const [rasterOpacity, setRasterOpacity]   = useState(0.85);
  const [phase, setPhase]                   = useState<PhaseId>('all');

  // Animation states (Module 3 track + Module 5 flood)
  const [animationFrame, setAnimationFrame] = useState<number | null>(null);
  const [floodProgress, setFloodProgress]   = useState(0);

  const activeCyclone     = selected ?? cyclones?.[0]?.id ?? null;
  const studyArea         = useStudyArea(activeCyclone);
  const metLayers         = useMeteorologyLayers(activeCyclone);
  const metStats          = useMeteorologyStats(activeCyclone);
  const trackLyrs         = useTrackLayers(activeCyclone);
  const trackStats        = useTrackStats(activeCyclone);
  const floodLyrs         = useFloodLayers(activeCyclone);
  const floodStats        = useFloodStats(activeCyclone);
  const hazardLyrs        = useHazardLayers(activeCyclone);
  const hazardStats       = useHazardStats(activeCyclone);
  const vegLyrs           = useVegLayers(activeCyclone);
  const vegStats          = useVegStats(activeCyclone);
  const lulcLyrs          = useLulcLayers(activeCyclone);
  const lulcStats         = useLulcStats(activeCyclone);
  const popLyrs           = usePopLayers(activeCyclone);
  const popStats          = usePopStats(activeCyclone);
  const mhLyrs            = useMHLayers(activeCyclone);
  const mhStats           = useMHStats(activeCyclone);
  const valLyrs           = useValidationLayers(activeCyclone);
  const valStats          = useValidationStats(activeCyclone);
  const reportSummary     = useReportSummary(activeCyclone);
  const activeCycloneInfo = cyclones?.find((c) => c.id === activeCyclone);

  function toggleLayer(key: string) {
    setVisibleLayers(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  function resetLayers() {
    setVisibleLayers(new Set(DEFAULT_VISIBLE_LAYERS));
  }

  if (!mounted) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#0a0e14] text-cyan-400 font-mono text-xs select-none">
        <span className="animate-pulse">⏳ Loading Dashboard modules…</span>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-[var(--surface-0)] text-[var(--text-primary)]">
      <Header cyclones={cyclones ?? []} selected={activeCyclone} onSelect={setSelected} activeCycloneInfo={activeCycloneInfo} />
      <div className="flex flex-1 overflow-hidden">
        <SidebarLeft
          studyArea={studyArea.data}
          isLoading={studyArea.isLoading}
          visibleLayers={visibleLayers}
          onToggleLayer={toggleLayer}
          meteorologyLayers={metLayers.data}
          meteorologyLayersLoading={metLayers.isLoading}
          trackLayers={trackLyrs.data}
          trackLayersLoading={trackLyrs.isLoading}
          floodLayers={floodLyrs.data}
          floodLayersLoading={floodLyrs.isLoading}
          hazardLayers={hazardLyrs.data}
          hazardLayersLoading={hazardLyrs.isLoading}
          vegLayers={vegLyrs.data}
          vegLayersLoading={vegLyrs.isLoading}
          lulcLayers={lulcLyrs.data}
          lulcLayersLoading={lulcLyrs.isLoading}
          popLayers={popLyrs.data}
          popLayersLoading={popLyrs.isLoading}
          mhLayers={mhLyrs.data}
          mhLayersLoading={mhLyrs.isLoading}
          valLayers={valLyrs.data}
          valLayersLoading={valLyrs.isLoading}
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
        />
        <main className="relative flex-1">
          <MapView
            cyclone={activeCycloneInfo}
            studyArea={studyArea.data}
            visibleLayers={visibleLayers}
            meteorologyLayers={metLayers.data}
            trackLayers={trackLyrs.data}
            floodLayers={floodLyrs.data}
            hazardLayers={hazardLyrs.data}
            vegLayers={vegLyrs.data}
            lulcLayers={lulcLyrs.data}
            popLayers={popLyrs.data}
            mhLayers={mhLyrs.data}
            valLayers={valLyrs.data}
            basemap={basemap}
            rasterOpacity={rasterOpacity}
            phase={phase}
            animationFrame={animationFrame}
            floodProgress={floodProgress}
          />
        </main>
        <SidebarRight
          studyArea={studyArea.data} isLoading={studyArea.isLoading} error={studyArea.error}
          meteorologyStats={metStats.data}   meteorologyStatsLoading={metStats.isLoading}   meteorologyLayersReady={!!metLayers.data}
          trackStats={trackStats.data}       trackStatsLoading={trackStats.isLoading}       trackLayersReady={!!trackLyrs.data}
          floodStats={floodStats.data}       floodStatsLoading={floodStats.isLoading}       floodLayersReady={!!floodLyrs.data}
          hazardStats={hazardStats.data}     hazardStatsLoading={hazardStats.isLoading}     hazardLayersReady={!!hazardLyrs.data}
          vegStats={vegStats.data}           vegStatsLoading={vegStats.isLoading}           vegLayersReady={!!vegLyrs.data}
          lulcStats={lulcStats.data}         lulcStatsLoading={lulcStats.isLoading}         lulcLayersReady={!!lulcLyrs.data}
          popStats={popStats.data}           popStatsLoading={popStats.isLoading}           popLayersReady={!!popLyrs.data}
          mhStats={mhStats.data}             mhStatsLoading={mhStats.isLoading}             mhLayersReady={!!mhLyrs.data}
          valStats={valStats.data}           valStatsLoading={valStats.isLoading}           valLayersReady={!!valLyrs.data}
          reportSummary={reportSummary.data} reportLoading={reportSummary.isLoading}        activeCyclone={activeCyclone}
        />
      </div>
      <BottomPanel
        activeCyclone={activeCyclone}
        studyAreaStatus={studyArea.status}
        trackLayersStatus={trackLyrs.status}
        floodLayersStatus={floodLyrs.status}
        hazardLayersStatus={hazardLyrs.status}
        vegLayersStatus={vegLyrs.status}
        lulcLayersStatus={lulcLyrs.status}
        popLayersStatus={popLyrs.status}
        mhLayersStatus={mhLyrs.status}
        valLayersStatus={valLyrs.status}
        reportSummaryStatus={reportSummary.status}
        trackLayers={trackLyrs.data}
        evtStart={activeCycloneInfo?.dates.evtS}
        evtEnd={activeCycloneInfo?.dates.evtE}
        animationFrame={animationFrame}
        setAnimationFrame={setAnimationFrame}
        setFloodProgress={setFloodProgress}
      />
    </div>
  );
}

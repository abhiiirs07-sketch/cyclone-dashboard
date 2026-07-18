'use client';

import { useState } from 'react';
import { Header } from '@/components/header';
import { SidebarLeft } from '@/components/sidebar-left';
import { SidebarRight } from '@/components/sidebar-right';
import { BottomPanel } from '@/components/bottom-panel';
import { MapView } from '@/components/map-view';
import { useCyclones, useStudyArea, useMeteorologyLayers, useMeteorologyStats } from '@/lib/api';

// Matches the shown/hidden defaults from section 6 "MAP SETUP" in the
// source script: india/landfall/affectedDistricts/studyArea default
// visible; reportingArea/states/districts default hidden.
const DEFAULT_VISIBLE_LAYERS = ['india', 'landfall', 'affectedDistricts', 'studyArea'];

export default function DashboardPage() {
  const { data: cyclones } = useCyclones();
  const [selected, setSelected] = useState<string | null>(null);
  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(new Set(DEFAULT_VISIBLE_LAYERS));

  const activeCyclone = selected ?? cyclones?.[0]?.id ?? null;
  const studyArea = useStudyArea(activeCyclone);
  // Fast: loads tile URLs in ~5 s — drives map layers + sidebar checkboxes
  const metLayers = useMeteorologyLayers(activeCyclone);
  // Slow: loads stats + charts in background — does NOT block the map
  const metStats = useMeteorologyStats(activeCyclone);
  const activeCycloneInfo = cyclones?.find((c) => c.id === activeCyclone);

  function toggleLayer(key: string) {
    setVisibleLayers((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

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
          meteorologyLayersLoading={metLayers.isLoading}
        />
        <main className="relative flex-1">
          <MapView
            cyclone={activeCycloneInfo}
            studyArea={studyArea.data}
            visibleLayers={visibleLayers}
            meteorologyLayers={metLayers.data}
          />
        </main>
        <SidebarRight
          studyArea={studyArea.data}
          isLoading={studyArea.isLoading}
          error={studyArea.error}
          meteorologyStats={metStats.data}
          meteorologyStatsLoading={metStats.isLoading}
          meteorologyLayersReady={!!metLayers.data}
        />
      </div>
      <BottomPanel activeCyclone={activeCyclone} studyAreaStatus={studyArea.status} />
    </div>
  );
}

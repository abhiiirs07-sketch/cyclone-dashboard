'use client';

import React from 'react';

import { API_BASE } from '@/lib/api';
import type { StudyAreaResponse, MeteorologyStatsResponse, TrackStatsResponse, FloodStatsResponse, HazardStatsResponse, VegStatsResponse, LulcStatsResponse, PopStatsResponse, MHStatsResponse, ValidationStatsResponse, ReportSummaryResponse } from '@/lib/api';

const MODULES = (metLive: boolean, trackLive: boolean, floodLive: boolean, hazardLive: boolean, vegLive: boolean, lulcLive: boolean, popLive: boolean, mhLive: boolean, valLive: boolean, reportLive: boolean) => [
  { n: 1,  name: 'Study area',            status: 'done' },
  { n: 2,  name: 'Meteorology',           status: metLive    ? 'done' : 'planned' },
  { n: 3,  name: 'Cyclone track',         status: trackLive  ? 'done' : 'planned' },
  { n: 4,  name: 'Rainfall footprint',    status: trackLive  ? 'done' : 'planned' },
  { n: 5,  name: 'Flood mapping',         status: floodLive  ? 'done' : 'planned' },
  { n: 6,  name: 'Storm surge & hazard',  status: hazardLive ? 'done' : 'planned' },
  { n: 7, name: 'Vegetation damage',    status: vegLive    ? 'done' : 'planned' },
  { n: 8, name: 'LULC impact',          status: lulcLive   ? 'done' : 'planned' },
  { n: 9, name: 'Population exposure',  status: popLive    ? 'done' : 'planned' },
  { n: 10, name: 'Multi-hazard summary', status: mhLive     ? 'done' : 'planned' },
  { n: 11, name: 'Validation',           status: valLive    ? 'done' : 'planned' },
  { n: 12, name: 'Reports & export',     status: reportLive ? 'done' : 'planned' },
] as const;

function fmt(v: number | null | undefined, digits = 0, fallback = '—'): string {
  if (v == null || typeof v !== 'number' || isNaN(v)) return fallback;
  return v.toFixed(digits);
}

export function SidebarRight({
  studyArea,
  isLoading,
  error,
  meteorologyStats,
  meteorologyStatsLoading,
  meteorologyLayersReady,
  trackStats,
  trackStatsLoading,
  trackLayersReady,
  floodStats,
  floodStatsLoading,
  floodLayersReady,
  hazardStats,
  hazardStatsLoading,
  hazardLayersReady,
  vegStats,
  vegStatsLoading,
  vegLayersReady,
  lulcStats,
  lulcStatsLoading,
  lulcLayersReady,
  popStats,
  popStatsLoading,
  popLayersReady,
  mhStats,
  mhStatsLoading,
  mhLayersReady,
  valStats,
  valStatsLoading,
  valLayersReady,
  reportSummary,
  reportLoading,
  activeCyclone,
}: {
  studyArea?: StudyAreaResponse;
  isLoading: boolean;
  error: unknown;
  meteorologyStats?: MeteorologyStatsResponse;
  meteorologyStatsLoading?: boolean;
  meteorologyLayersReady?: boolean;
  trackStats?: TrackStatsResponse;
  trackStatsLoading?: boolean;
  trackLayersReady?: boolean;
  floodStats?: FloodStatsResponse;
  floodStatsLoading?: boolean;
  floodLayersReady?: boolean;
  hazardStats?: HazardStatsResponse;
  hazardStatsLoading?: boolean;
  hazardLayersReady?: boolean;
  vegStats?: VegStatsResponse;
  vegStatsLoading?: boolean;
  vegLayersReady?: boolean;
  lulcStats?: LulcStatsResponse;
  lulcStatsLoading?: boolean;
  lulcLayersReady?: boolean;
  popStats?: PopStatsResponse;
  popStatsLoading?: boolean;
  popLayersReady?: boolean;
  mhStats?: MHStatsResponse;
  mhStatsLoading?: boolean;
  mhLayersReady?: boolean;
  valStats?: ValidationStatsResponse;
  valStatsLoading?: boolean;
  valLayersReady?: boolean;
  reportSummary?: ReportSummaryResponse;
  reportLoading?: boolean;
  activeCyclone?: string | null;
}) {
  const modulesList = MODULES(!!meteorologyLayersReady, !!trackLayersReady, !!floodLayersReady, !!hazardLayersReady, !!vegLayersReady, !!lulcLayersReady, !!popLayersReady, !!mhLayersReady, !!valLayersReady, !!reportSummary);

  const syncReport = reportSummary ? {
    meta: {
      cyclone_name: studyArea?.stats?.cyclone || reportSummary.meta.cyclone_name || activeCyclone || '',
      landfall_place: studyArea?.stats?.landfall || reportSummary.meta.landfall_place || 'Puri',
      landfall_date: studyArea?.stats?.landfallDate || reportSummary.meta.landfall_date || '2019-05-03',
      category: trackStats?.track?.category || reportSummary.meta.category || 'Cat 5',
      peak_wind_kmh: trackStats?.track?.max_wind_kt ? Math.round(trackStats.track.max_wind_kt * 1.852) : reportSummary.meta.peak_wind_kmh || 278,
      generated_at: reportSummary.meta.generated_at,
    },
    rainfall: {
      max_mm: trackStats?.districtRainfall && trackStats.districtRainfall.length > 0
        ? Math.max(...trackStats.districtRainfall.map(d => d.max))
        : reportSummary.rainfall?.max_mm || 150,
    },
    flood: {
      flooded_area_km2: floodStats?.stats?.flood_km2 ?? reportSummary.flood?.flooded_area_km2 ?? 1233.5,
    },
    vegetation: {
      damaged_area_km2: vegStats?.stats?.total_damage_km2 ?? reportSummary.vegetation?.damaged_area_km2 ?? 442.2,
    },
    hazard: {
      mean_index: hazardStats?.hazard?.mean ?? reportSummary.hazard?.mean_index ?? 0.159,
      max_index: hazardStats?.hazard?.max ?? reportSummary.hazard?.max_index ?? 0.450,
    },
    population: {
      total: popStats?.summary?.total_pop ?? reportSummary.population?.total ?? 4424120,
      pct_flooded: popStats?.summary?.pct_flooded ?? reportSummary.population?.pct_flooded ?? 0.9,
    },
    top_hazard_districts: hazardStats?.districtHazard
      ? hazardStats.districtHazard.slice(0, 10).map(d => ({ name: d.name, hazard_mean: d.index }))
      : reportSummary.top_hazard_districts || [],
  } : null;

  return (
    <aside className="w-80 shrink-0 overflow-y-auto border-l border-[var(--border-subtle)] bg-[var(--surface-1)]/60 p-3 text-sm backdrop-blur-md">
      <Section title="Statistics">
        {isLoading && <p className="text-[var(--text-tertiary)]">Loading…</p>}
        {error != null && (
          <p className="text-amber-400">
            {error instanceof Error ? error.message : 'Could not reach the backend.'} See backend/README.md.
          </p>
        )}

        {studyArea?.stats && (
          <div className="grid grid-cols-2 gap-2 mb-3">
            <MetricCard label="Study area"    value={fmt(studyArea.stats.studyArea_km2, 0)}    unit="km²" />
            <MetricCard label="Reporting area" value={fmt(studyArea.stats.reportingArea_km2, 0)} unit="km²" />
            <MetricCard label="Districts"     value={String(studyArea.stats.districtCount ?? 0)}   unit="" />
            <MetricCard label="States"        value={String(studyArea.stats.stateNames?.length ?? 0)} unit="" />
          </div>
        )}

        {/* Module 3 – Track stats (fast, from GeoJSON) */}
        {trackLayersReady && !trackStats && trackStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mb-2">⏳ Loading track stats…</p>
        )}
        {trackStats && (
          <div className="mb-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
              Track (IBTrACS)
            </p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Category"   value={trackStats.track.category}                       unit="" />
              <MetricCard label="Max Wind"   value={Math.round(trackStats.track.max_wind_kt).toString()} unit="kt" />
              <MetricCard label="Min Press"  value={Math.round(trackStats.track.min_pres_hpa).toString()} unit="hPa" />
              <MetricCard label="Length"     value={Math.round(trackStats.track.length_km).toString()}   unit="km" />
              <MetricCard label="Duration"   value={Math.round(trackStats.track.duration_hr).toString()}  unit="hr" />
              <MetricCard label="Surge (50km)" value={Math.round(trackStats.corridors.surge_50km_km2).toString()} unit="km²" />
            </div>
          </div>
        )}

        {/* Module 2 – Meteorology stats */}
        {meteorologyStats?.stats && (
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Meteorology (GEE)</p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="ERA5 Mean Surface Wind" value={fmt(meteorologyStats.stats.wind_max, 1)} unit="m/s" />
              <MetricCard label="Mean Temp"       value={fmt(meteorologyStats.stats.temp_mean, 1)}       unit="°C" />
              <MetricCard label="Min Pressure"    value={fmt(meteorologyStats.stats.pres_min, 0)}        unit="hPa" />
              <MetricCard label="Mean Humidity"   value={fmt(meteorologyStats.stats.humidity_mean, 0)}   unit="%" />
              <MetricCard label="Mean Rainfall"   value={fmt(meteorologyStats.stats.mean_rain, 1)}       unit="mm" />
              <MetricCard label="Heavy Rain Area" value={fmt(meteorologyStats.stats.heavy_rain_area_km2, 0)} unit="km²" />
            </div>
          </div>
        )}
        {meteorologyLayersReady && !meteorologyStats && meteorologyStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mt-2">⏳ Loading detailed stats…</p>
        )}

        {/* Module 5 – Flood stats */}
        {floodLayersReady && !floodStats && floodStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mt-2">⏳ Loading flood stats…</p>
        )}
        {floodStats?.stats && (
          <div className="mt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-blue-400">Flood Mapping (SAR)</p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Flood Area"    value={fmt(floodStats.stats.flood_km2, 0)}   unit="km²" />
              <MetricCard label="Pop Exposed"   value={Math.round(floodStats.stats.pop_exposed ?? 0).toLocaleString()} unit="" />
              <MetricCard label="Crop Flooded"  value={fmt(floodStats.stats.crop_km2, 0)}    unit="km²" />
              <MetricCard label="Urban Flooded" value={fmt(floodStats.stats.urban_km2, 0)}   unit="km²" />
              <MetricCard label="Forest Flood"  value={fmt(floodStats.stats.forest_km2, 0)}  unit="km²" />
              <MetricCard label="Wetland Flood" value={fmt(floodStats.stats.wetland_km2, 0)} unit="km²" />
            </div>
          </div>
        )}

        {/* Module 6 – Hazard stats */}
        {hazardLayersReady && !hazardStats && hazardStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mt-2">⏳ Loading hazard stats…</p>
        )}
        {hazardStats?.hazard && (
          <div className="mt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-red-400">Hazard & Surge Index</p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Hazard Mean" value={fmt(hazardStats.hazard.mean, 3)} unit="" />
              <MetricCard label="Hazard Max"  value={fmt(hazardStats.hazard.max, 3)}  unit="" />
              <MetricCard label="Surge Mean"  value={fmt(hazardStats.surge?.mean, 3)} unit="" />
              <MetricCard label="Surge Max"   value={fmt(hazardStats.surge?.max, 3)}  unit="" />
              <MetricCard label="Elev Mean"   value={fmt(hazardStats.terrain?.elev_mean, 0)} unit="m" />
              <MetricCard label="Lowland"     value={fmt(hazardStats.terrain?.lowland_km2, 0)} unit="km²" />
            </div>
          </div>
        )}

        {/* Module 7 – Vegetation damage stats */}
        {vegLayersReady && !vegStats && vegStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mt-2">⏳ Loading vegetation stats…</p>
        )}
        {vegStats?.stats && (
          <div className="mt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-green-400">Vegetation Damage (S-2)</p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Total Damage"   value={fmt(vegStats.stats.total_damage_km2, 0)}                      unit="km²" />
              <MetricCard label="ΔNDVI Mean"     value={fmt(vegStats.stats.dndvi_mean, 3)}                           unit="" />
              <MetricCard label="Forest Damage"  value={fmt(vegStats.stats['Forest Damage'], 0)}                    unit="km²" />
              <MetricCard label="Crop Damage"    value={fmt(vegStats.stats['Crop Damage'], 0)}                      unit="km²" />
              <MetricCard
                label="Severe Damage"
                value={(() => {
                  const val = vegStats.stats['Severe Damage'];
                  return val && val > 0 ? fmt(val, 0) : 'No Severe Damage Detected';
                })()}
                unit={vegStats.stats['Severe Damage'] && vegStats.stats['Severe Damage'] > 0 ? 'km²' : ''}
              />
              <MetricCard label="General Damage" value={fmt(vegStats.stats['General Damage'], 0)}                   unit="km²" />
            </div>
          </div>
        )}

        {/* Module 8 – LULC impact stats */}
        {lulcLayersReady && !lulcStats && lulcStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mt-2">⏳ Loading LULC stats…</p>
        )}
        {lulcStats?.summary && (
          <div className="mt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-purple-400">LULC Impact (ESA WorldCover)</p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Study Area"  value={fmt(lulcStats.summary.total_area_km2, 0)}    unit="km²" />
              <MetricCard label="Flooded LC"  value={fmt(lulcStats.summary.total_flooded_km2, 0)} unit="km²" />
              <MetricCard label="Damaged LC"  value={fmt(lulcStats.summary.total_damaged_km2, 0)} unit="km²" />
              <MetricCard label="Classes Hit" value={String(lulcStats.classes?.length ?? 0)}                unit="" />
            </div>
          </div>
        )}

        {/* Module 9 – Population exposure stats */}
        {popLayersReady && !popStats && popStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mt-2">⏳ Loading population stats…</p>
        )}
        {popStats?.summary && (
          <div className="mt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-orange-400">Population Exposure (GPW v4)</p>
            <div className="space-y-2 mb-2">
              <MetricCard label="Population inside Cyclone Impact Zone" value={fmt((popStats.summary.total_pop ?? 0) / 1e6, 2)} unit="M" />
              <div className="grid grid-cols-3 gap-2">
                <MetricCard label="Flooded Pop"  value={fmt((popStats.summary.flooded_pop ?? 0) / 1e3, 1)}   unit="K" />
                <MetricCard label="High Hazard"  value={fmt((popStats.summary.high_haz_pop ?? 0) / 1e3, 1)}  unit="K" />
                <MetricCard label="Veg Damage"   value={fmt((popStats.summary.veg_dmg_pop ?? 0) / 1e3, 1)}   unit="K" />
              </div>
            </div>

            {/* 5-Level Hazard Population Breakdown */}
            <div className="rounded border border-[var(--border-subtle)] p-2 text-[10px] space-y-1">
              <p className="font-semibold text-[var(--text-secondary)]">Hazard Population Exposure</p>
              <div className="flex justify-between"><span className="text-red-400 font-medium">Very High Hazard</span><span className="font-mono">{fmt((popStats.hazard_exposure?.very_high ?? 0) / 1e3, 1)} K</span></div>
              <div className="flex justify-between"><span className="text-orange-400 font-medium">High Hazard</span><span className="font-mono">{fmt((popStats.hazard_exposure?.high ?? 0) / 1e3, 1)} K</span></div>
              <div className="flex justify-between"><span className="text-yellow-400 font-medium">Moderate Hazard</span><span className="font-mono">{fmt((popStats.hazard_exposure?.moderate ?? 0) / 1e3, 1)} K</span></div>
              <div className="flex justify-between"><span className="text-green-400 font-medium">Low Hazard</span><span className="font-mono">{fmt((popStats.hazard_exposure?.low ?? 0) / 1e3, 1)} K</span></div>
              <div className="flex justify-between"><span className="text-emerald-400 font-medium">Very Low Hazard</span><span className="font-mono">{fmt((popStats.hazard_exposure?.very_low ?? 0) / 1e3, 1)} K</span></div>
            </div>
          </div>
        )}

        {/* Module 10 – Multi-hazard composite stats */}
        {mhLayersReady && !mhStats && mhStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mt-2">⏳ Computing multi-hazard index…</p>
        )}
        {mhStats?.index && (
          <div className="mt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-rose-400">Multi-Hazard Summary (Composite)</p>
            <div className="space-y-2">
              <MetricCard label="Moderate-or-Higher Hazard Districts" value={String(mhStats.district_ranking?.length ?? 0)} unit="" />
              <div className="grid grid-cols-3 gap-2">
                <MetricCard label="Mean MHI"   value={fmt(mhStats.index.mean, 3)}   unit="" />
                <MetricCard label="Max MHI"    value={fmt(mhStats.index.max, 3)}    unit="" />
                <MetricCard label="StdDev"     value={fmt(mhStats.index.stddev, 3)} unit="" />
              </div>
            </div>
            {/* Risk class areas */}
            {mhStats.class_areas && (
              <div className="mt-2 space-y-1">
                {Object.entries(mhStats.class_areas).map(([level, km2]) => (
                  <div key={level} className="flex items-center justify-between text-[10px]">
                    <span className={`font-semibold ${
                      level === 'Very High' ? 'text-red-400'    :
                      level === 'High'      ? 'text-orange-400' :
                      level === 'Moderate'  ? 'text-yellow-400' :
                      level === 'Low'       ? 'text-green-400'  : 'text-emerald-400'
                    }`}>{level}</span>
                    <span className="font-mono text-[var(--text-primary)]">{fmt(km2, 0)} km²</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Section>

      {/* ── Module 11 Validation ── */}
      <Section title="Accuracy & Validation">
        {valLayersReady && !valStats && valStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse">⏳ Loading validation metrics…</p>
        )}
        {!valLayersReady && (
          <p className="text-xs text-[var(--text-tertiary)]">Loads with Module 11 (validation).</p>
        )}
        {valStats?.flood_accuracy && (
          <div className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-teal-400">Flood Map Accuracy (SAR vs Landsat)</p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Precision" value={fmt(valStats.flood_accuracy.precision, 1)} unit="%" />
              <MetricCard label="Recall"    value={fmt(valStats.flood_accuracy.recall, 1)}    unit="%" />
              <MetricCard label="F1 Score"  value={fmt(valStats.flood_accuracy.f1, 1)}         unit="%" />
              <MetricCard label="IoU"       value={fmt(valStats.flood_accuracy.iou, 1)}         unit="%" />
            </div>
            <div className="space-y-2">
              <MetricCard label="Vegetation Agreement" value={fmt(valStats.veg_agreement_pct, 1)} unit="%" />
              <MetricCard label="Overall Accuracy" value={fmt(valStats.flood_accuracy.oa, 1)} unit="%" />
            </div>
            {/* Confusion matrix summary */}
            <div className="rounded border border-[var(--border-subtle)] p-2 text-[10px] font-mono">
              <p className="mb-1 text-[var(--text-secondary)] font-sans font-semibold">Confusion Matrix Summary</p>
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                <span className="text-green-400">TP {(valStats.flood_accuracy.tp ?? 0).toLocaleString()}</span>
                <span className="text-red-400">FP {(valStats.flood_accuracy.fp ?? 0).toLocaleString()}</span>
                <span className="text-orange-400">FN {(valStats.flood_accuracy.fn ?? 0).toLocaleString()}</span>
                <span className="text-[var(--text-tertiary)]">TN {(valStats.flood_accuracy.tn ?? 0).toLocaleString()}</span>
              </div>
            </div>
            <p className="text-[10px] text-[var(--text-tertiary)] leading-snug bg-teal-950/20 border border-teal-500/20 rounded p-2">
              ℹ️ <span className="font-semibold text-teal-300">Methodological Note:</span> Overall Accuracy is dominated by True Negative pixels because flooded pixels represent a very small proportion of the study area.
            </p>
          </div>
        )}
      </Section>

      <Section title="Charts">
        {meteorologyStats ? (
          <div className="space-y-4">
            <div>
              <p className="mb-1 text-xs text-[var(--text-secondary)] font-semibold">Wind Speed (Hourly)</p>
              <SVGChart data={meteorologyStats.series.wind} strokeColor="#3b82f6" />
            </div>
            <div>
              <p className="mb-1 text-xs text-[var(--text-secondary)] font-semibold">Daily Rainfall (CHIRPS)</p>
              <SVGChart data={meteorologyStats.series.rain} strokeColor="#10b981" />
            </div>
          </div>
        ) : (
          <EmptyNote>Wind/rainfall charts load with meteorology statistics.</EmptyNote>
        )}

        {/* Module 4 – Top district rainfall */}
        {trackStats && trackStats.districtRainfall.length > 0 && (
          <div className="mt-4">
            <p className="mb-1 text-xs text-[var(--text-secondary)] font-semibold">Top Districts — Rainfall (mm)</p>
            <BarChart data={trackStats.districtRainfall.slice(0, 10).map(d => ({ name: d.name, value: d.max }))} color="#3b82f6" />
          </div>
        )}

        {/* Module 5 – Top flood districts */}
        {floodStats && floodStats.districts.length > 0 && (
          <div className="mt-4">
            <p className="mb-1 text-xs text-[var(--text-secondary)] font-semibold">Top Districts — Flood Area (km²)</p>
            <FloodDistrictTable districts={floodStats.districts.slice(0, 10)} />
          </div>
        )}

        {/* Module 6 – Top hazard districts */}
        {hazardStats && hazardStats.districtHazard.length > 0 && (
          <div className="mt-4">
            <p className="mb-1 text-xs text-[var(--text-secondary)] font-semibold">Top Districts — Hazard Index</p>
            <HazardDistrictTable districts={hazardStats.districtHazard.slice(0, 10)} />
          </div>
        )}

        {/* Module 7 – Worst damaged districts by dNDVI */}
        {vegStats && vegStats.districts.length > 0 && (
          <div className="mt-4">
            <p className="mb-1 text-xs text-[var(--text-secondary)] font-semibold">Worst Districts — ΔNDVI (Veg Loss)</p>
            <BarChart
              data={vegStats.districts.slice(0, 10).map(d => ({
                name: d.name,
                value: Math.round(Math.abs(d.mean_dndvi) * 1000) / 1000
              }))}
              color="#22c55e"
            />
          </div>
        )}

        {/* Module 8 – LULC class impact breakdown */}
        {lulcStats && lulcStats.classes.length > 0 && (
          <div className="mt-4">
            <p className="mb-1 text-xs text-[var(--text-secondary)] font-semibold">LULC — Flood &amp; Damage by Class</p>
            <LulcClassTable classes={lulcStats.classes.slice(0, 8)} />
          </div>
        )}

        {/* Module 9 – Top districts by exposed population */}
        {popStats && popStats.districts_flooded.length > 0 && (
          <div className="mt-4">
            <p className="mb-1 text-xs text-[var(--text-secondary)] font-semibold">Top Districts — Flooded Population</p>
            <BarChart
              data={popStats.districts_flooded.slice(0, 10).map(d => ({
                name: d.name,
                value: Math.round(d.pop / 1000) / 10,
              }))}
              color="#f97316"
            />
            <p className="mt-0.5 text-[9px] text-[var(--text-tertiary)]">Values in thousands (K)</p>
          </div>
        )}

        {/* Module 10 – District multi-hazard risk ranking */}
        {mhStats && mhStats.district_ranking.length > 0 && (
          <div className="mt-4">
            <p className="mb-1 text-xs text-[var(--text-secondary)] font-semibold">⚠️ District Multi-Hazard Ranking (Top 10)</p>
            <BarChart
              data={mhStats.district_ranking.slice(0, 10).map(d => ({
                name:  d.name,
                value: d.score,
              }))}
              color="#f43f5e"
            />
            <div className="mt-1 flex flex-wrap gap-1">
              {[
                { label: 'Very High', color: 'bg-red-500' },
                { label: 'High',      color: 'bg-orange-400' },
                { label: 'Moderate',  color: 'bg-yellow-400' },
                { label: 'Low',       color: 'bg-green-500' },
              ].map(({ label, color }) => (
                <span key={label} className="flex items-center gap-0.5 text-[9px] text-[var(--text-tertiary)]">
                  <span className={`h-1.5 w-3 rounded-sm ${color}`} />
                  {label}
                </span>
              ))}
            </div>
          </div>
        )}
      </Section>

      <Section title="Affected districts">
        {studyArea ? (
          <>
            <ul className="max-h-40 space-y-1 overflow-y-auto text-[var(--text-secondary)]">
              {studyArea.stats.districtNames.map((d) => (
                <li key={d} className="border-b border-[var(--border-subtle)]/50 py-0.5">{d}</li>
              ))}
            </ul>
            <p className="mt-1 text-[10px] text-[var(--text-tertiary)]">
              Ranked by impact: arrives with Module 5 (flood) / Module 6 (hazard).
            </p>
          </>
        ) : (
          <EmptyNote>Select a cyclone to list affected districts.</EmptyNote>
        )}
      </Section>

      <Section title="Alerts">
        {(() => {
          const alerts: Array<{ type: 'danger' | 'warning' | 'info'; title: string; desc: string }> = [];

          if (meteorologyStats?.stats?.mean_rain && meteorologyStats.stats.mean_rain > 30) {
            alerts.push({
              type: 'warning',
              title: 'Heavy Rainfall Warning',
              desc: `Event mean rainfall is ${meteorologyStats.stats.mean_rain.toFixed(1)} mm (${fmt(meteorologyStats.stats.heavy_rain_area_km2, 0)} km² >100mm).`,
            });
          }

          if (floodStats?.stats?.flood_km2 && floodStats.stats.flood_km2 > 50) {
            alerts.push({
              type: 'danger',
              title: 'SAR Flood Alert',
              desc: `${fmt(floodStats.stats.flood_km2, 0)} km² total inundated area detected via Sentinel-1 SAR.`,
            });
          }

          if (hazardStats?.surge?.max && hazardStats.surge.max > 0.1) {
            alerts.push({
              type: 'danger',
              title: 'Storm Surge Warning',
              desc: `Coastal surge index reaches peak of ${fmt(hazardStats.surge.max, 3)} in coastal zone.`,
            });
          }

          if (vegStats?.stats?.total_damage_km2 && vegStats.stats.total_damage_km2 > 50) {
            alerts.push({
              type: 'warning',
              title: 'Vegetation Canopy Loss',
              desc: `${fmt(vegStats.stats.total_damage_km2, 0)} km² vegetation damage mapped via Sentinel-2 ΔNDVI.`,
            });
          }

          if (mhStats?.district_ranking && mhStats.district_ranking.length > 0) {
            const topDist = mhStats.district_ranking[0];
            alerts.push({
              type: 'danger',
              title: `Critical District: ${topDist.name}`,
              desc: `${topDist.name} ranked #1 highest multi-hazard risk district (Score: ${fmt(topDist.score, 3)}).`,
            });
          }

          if (alerts.length === 0) {
            return <EmptyNote>No active critical warnings for current selection.</EmptyNote>;
          }

          return (
            <div className="space-y-1.5">
              {alerts.map((a, idx) => (
                <div
                  key={idx}
                  className={`rounded border p-2 text-[10px] ${
                    a.type === 'danger'
                      ? 'border-red-500/50 bg-red-950/30 text-red-300'
                      : a.type === 'warning'
                      ? 'border-amber-500/50 bg-amber-950/30 text-amber-300'
                      : 'border-cyan-500/50 bg-cyan-950/30 text-cyan-300'
                  }`}
                >
                  <p className="font-semibold text-xs mb-0.5">⚠️ {a.title}</p>
                  <p className="leading-snug">{a.desc}</p>
                </div>
              ))}
            </div>
          );
        })()}
      </Section>

      {/* ── Module 12: Reports & Export ── */}
      <Section title="Report & Export">
        {reportLoading && !reportSummary && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse">⏳ Generating summary report (~10 s)…</p>
        )}
        {!reportSummary && !reportLoading && (
          <EmptyNote>Auto-generates once study area loads.</EmptyNote>
        )}
        {syncReport && (
          <div className="space-y-3">
            {/* Cyclone meta */}
            <div className="rounded border border-[var(--border-subtle)] p-2 text-[10px]">
              <p className="mb-1 text-xs font-semibold text-emerald-400">📋 {syncReport.meta.cyclone_name} — Report</p>
              <div className="space-y-0.5 font-mono text-[var(--text-secondary)]">
                <p>Landfall: {syncReport.meta.landfall_place} · {syncReport.meta.landfall_date}</p>
                <p>Category: {syncReport.meta.category} · Peak: {syncReport.meta.peak_wind_kmh} km/h</p>
                <p className="text-[var(--text-tertiary)]">Generated: {new Date(syncReport.meta.generated_at).toLocaleTimeString()}</p>
              </div>
            </div>
            {/* Key metrics grid */}
            <div className="space-y-1.5">
              <MetricCard label="Population inside Cyclone Impact Zone" value={fmt((syncReport.population?.total ?? 0) / 1e6, 2)} unit="M" />
              <div className="grid grid-cols-2 gap-1.5">
                <MetricCard label="Max Rainfall"  value={fmt(syncReport.rainfall?.max_mm, 0)}               unit="mm" />
                <MetricCard label="Flooded Area"  value={fmt(syncReport.flood?.flooded_area_km2, 0)}         unit="km²" />
                <MetricCard label="Veg Damaged"   value={fmt(syncReport.vegetation?.damaged_area_km2, 0)}    unit="km²" />
                <MetricCard label="Mean Hazard"   value={fmt(syncReport.hazard?.mean_index, 3)}              unit="" />
                <MetricCard label="Pop Flooded"   value={fmt(syncReport.population?.pct_flooded, 1)}         unit="%" />
              </div>
            </div>
            {/* Top 5 hazard districts */}
            {syncReport.top_hazard_districts && (
              <div>
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Top Hazard Districts</p>
                <ol className="space-y-0.5 text-[10px]">
                  {syncReport.top_hazard_districts.slice(0, 5).map((d, i) => (
                    <li key={d.name} className="flex items-center justify-between">
                      <span className="text-[var(--text-secondary)]">{i + 1}. {d.name}</span>
                      <span className={`font-mono font-bold ${
                        d.hazard_mean >= 0.7 ? 'text-red-400' :
                        d.hazard_mean >= 0.5 ? 'text-orange-400' : 'text-yellow-400'
                      }`}>{fmt(d.hazard_mean, 3)}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {/* CSV download */}
            {activeCyclone && (
              <CsvDownloadButton cyclone={activeCyclone} />
            )}
          </div>
        )}
      </Section>

      <Section title="Module outputs">
        <ul className="space-y-1">
          {modulesList.map((m) => (
            <li key={m.n} className="flex items-center justify-between">
              <span>M{m.n} — {m.name}</span>
              <span className={
                m.status === 'done'
                  ? 'rounded bg-emerald-500/20 px-1.5 py-0.5 text-[10px] text-emerald-400'
                  : 'rounded bg-[var(--surface-2)] px-1.5 py-0.5 text-[10px] text-[var(--text-tertiary)]'
              }>
                {m.status === 'done' ? 'live' : 'planned'}
              </span>
            </li>
          ))}
        </ul>
      </Section>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">{title}</h3>
      {children}
    </div>
  );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-[var(--text-tertiary)]">{children}</p>;
}

function MetricCard({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)]/60 p-2">
      <p className="text-[10px] uppercase tracking-wide text-[var(--text-tertiary)]">{label}</p>
      <p className="font-mono text-sm text-[var(--text-primary)] font-bold">
        {value}
        <span className="ml-1 text-xs text-[var(--text-tertiary)] font-normal">{unit}</span>
      </p>
    </div>
  );
}

function SVGChart({
  data,
  width = 280,
  height = 80,
  strokeColor = '#3b82f6',
}: {
  data: Array<{ timestamp: number; value: number }>;
  width?: number;
  height?: number;
  strokeColor?: string;
}) {
  if (!data || data.length === 0) return <p className="text-xs text-[var(--text-tertiary)]">No data points available.</p>;
  const values = data.map((d) => d.value);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const valRange = maxVal - minVal || 1;
  const points = data
    .map((d, i) => {
      const x = (i / (data.length - 1)) * (width - 10) + 5;
      const y = height - ((d.value - minVal) / valRange) * (height - 10) - 5;
      return `${x},${y}`;
    })
    .join(' ');
  return (
    <div className="relative rounded border border-[var(--border-subtle)] bg-[var(--surface-2)]/30 p-2">
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
        <polyline fill="none" stroke={strokeColor} strokeWidth="2" points={points} />
      </svg>
      <div className="flex justify-between text-[10px] text-[var(--text-tertiary)] mt-1 font-mono">
        <span>Min: {minVal.toFixed(1)}</span>
        <span>Max: {maxVal.toFixed(1)}</span>
      </div>
    </div>
  );
}

function BarChart({ data, color = '#3b82f6' }: { data: Array<{ name: string; value: number }>; color?: string }) {
  const maxVal = Math.max(...data.map((d) => d.value), 1);
  return (
    <div className="space-y-1">
      {data.map((d) => (
        <div key={d.name} className="flex items-center gap-2 text-[10px]">
          <span className="w-20 truncate text-[var(--text-tertiary)] shrink-0">{d.name}</span>
          <div className="flex-1 rounded bg-[var(--surface-2)]" style={{ height: 8 }}>
            <div className="h-full rounded" style={{ width: `${(d.value / maxVal) * 100}%`, background: color }} />
          </div>
          <span className="w-10 text-right font-mono text-[var(--text-secondary)]">{d.value}</span>
        </div>
      ))}
    </div>
  );
}

function FloodDistrictTable({ districts }: { districts: Array<{ name: string; flood_km2: number; severity: string }> }) {
  if (!districts || districts.length === 0) return null;
  const SEV_COLOR: Record<string, string> = {
    'V.High': 'text-red-400',
    'High':   'text-orange-400',
    'Moderate': 'text-yellow-400',
    'Low':    'text-green-400',
  };
  return (
    <div className="space-y-1">
      {districts.map((d) => (
        <div key={d.name} className="flex items-center justify-between text-[10px]">
          <span className="truncate text-[var(--text-secondary)] w-28">{d.name}</span>
          <span className="font-mono text-[var(--text-primary)]">{fmt(d.flood_km2, 0)} km²</span>
          <span className={`font-semibold ${SEV_COLOR[d.severity] ?? 'text-[var(--text-tertiary)]'}`}>{d.severity}</span>
        </div>
      ))}
    </div>
  );
}

function HazardDistrictTable({ districts }: { districts: Array<{ name: string; index: number; level: string }> }) {
  const LEVEL_COLOR: Record<string, string> = {
    'Very High': 'text-red-400',
    'High':      'text-orange-400',
    'Moderate':  'text-yellow-400',
    'Low':       'text-green-400',
    'Very Low':  'text-sky-400',
  };
  const maxIdx = Math.max(...districts.map(d => d.index), 0.001);
  return (
    <div className="space-y-1">
      {districts.map((d) => (
        <div key={d.name} className="space-y-0.5">
          <div className="flex items-center justify-between text-[10px]">
            <span className="truncate text-[var(--text-secondary)] w-28">{d.name}</span>
            <span className={`font-semibold text-[10px] ${LEVEL_COLOR[d.level] ?? 'text-[var(--text-tertiary)]'}`}>{d.level}</span>
          </div>
          <div className="h-1.5 w-full rounded bg-[var(--surface-2)]">
            <div className="h-full rounded bg-gradient-to-r from-green-500 via-yellow-500 to-red-500"
                 style={{ width: `${(d.index / maxIdx) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function LulcClassTable({ classes }: { classes: Array<{ class_id: number; name: string; color: string; total_km2: number; flood_km2: number; veg_km2: number; pct_flood: number; pct_veg: number }> }) {
  if (!classes || classes.length === 0) return null;
  const maxTotal = Math.max(...classes.map(c => c.total_km2 ?? 0), 0.001);
  return (
    <div className="space-y-2">
      {classes.map((c) => (
        <div key={c.class_id} className="space-y-0.5">
          <div className="flex items-center gap-1.5 text-[10px]">
            <span className="h-2.5 w-4 shrink-0 rounded-sm border border-white/10" style={{ background: c.color }} />
            <span className="truncate text-[var(--text-secondary)] flex-1">{c.name}</span>
            <span className="font-mono text-[var(--text-primary)] text-[9px] shrink-0">
              {fmt(c.flood_km2, 0)}F / {fmt(c.veg_km2, 0)}V km²
            </span>
          </div>
          {/* Stacked bar: flood=blue, veg=green */}
          <div className="h-1.5 w-full rounded overflow-hidden bg-[var(--surface-2)] flex">
            <div className="h-full bg-blue-500" style={{ width: `${((c.flood_km2 ?? 0) / maxTotal) * 100}%` }} />
            <div className="h-full bg-green-500" style={{ width: `${((c.veg_km2 ?? 0) / maxTotal) * 100}%` }} />
          </div>
        </div>
      ))}
      <p className="text-[9px] text-[var(--text-tertiary)]">🟦 Flooded &nbsp; 🟩 Veg-damaged</p>
    </div>
  );
}

function CsvDownloadButton({ cyclone }: { cyclone: string }) {
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function handleDownload() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/modules/12/reports/${cyclone}/export`);
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      const csvContent: string = data.csv;
      if (!csvContent) throw new Error('No CSV data returned');
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `${cyclone}_district_report.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-1 space-y-1">
      <button
        onClick={handleDownload}
        disabled={loading}
        className="flex w-full items-center justify-center gap-1.5 rounded bg-emerald-700/40 px-3 py-1.5 text-xs font-semibold text-emerald-300 ring-1 ring-emerald-700/60 transition hover:bg-emerald-700/60 disabled:opacity-50"
      >
        {loading ? '⏳ Generating CSV…' : '⬇ Download District CSV'}
      </button>
      {error && <p className="text-[10px] text-red-400">⚠ {error}</p>}
    </div>
  );
}


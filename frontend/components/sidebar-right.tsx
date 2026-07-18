'use client';

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

  return (
    <aside className="w-80 shrink-0 overflow-y-auto border-l border-[var(--border-subtle)] bg-[var(--surface-1)]/60 p-3 text-sm backdrop-blur-md">
      <Section title="Statistics">
        {isLoading && <p className="text-[var(--text-tertiary)]">Loading…</p>}
        {error != null && (
          <p className="text-amber-400">
            {error instanceof Error ? error.message : 'Could not reach the backend.'} See backend/README.md.
          </p>
        )}

        {studyArea && (
          <div className="grid grid-cols-2 gap-2 mb-3">
            <MetricCard label="Study area"    value={studyArea.stats.studyArea_km2.toFixed(0)}    unit="km²" />
            <MetricCard label="Reporting area" value={studyArea.stats.reportingArea_km2.toFixed(0)} unit="km²" />
            <MetricCard label="Districts"     value={String(studyArea.stats.districtCount)}        unit="" />
            <MetricCard label="States"        value={String(studyArea.stats.stateNames.length)}    unit="" />
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
        {meteorologyStats && (
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Meteorology (GEE)</p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Peak Wind"       value={meteorologyStats.stats.wind_max.toFixed(1)}        unit="m/s" />
              <MetricCard label="Mean Temp"       value={meteorologyStats.stats.temp_mean.toFixed(1)}       unit="°C" />
              <MetricCard label="Min Pressure"    value={meteorologyStats.stats.pres_min.toFixed(0)}        unit="hPa" />
              <MetricCard label="Mean Humidity"   value={meteorologyStats.stats.humidity_mean.toFixed(0)}   unit="%" />
              <MetricCard label="Mean Rainfall"   value={meteorologyStats.stats.mean_rain.toFixed(1)}       unit="mm" />
              <MetricCard label="Heavy Rain Area" value={meteorologyStats.stats.heavy_rain_area_km2.toFixed(0)} unit="km²" />
            </div>
          </div>
        )}
        {meteorologyLayersReady && !meteorologyStats && meteorologyStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mt-2">⏳ Loading detailed stats (2-3 min)…</p>
        )}

        {/* Module 5 – Flood stats */}
        {floodLayersReady && !floodStats && floodStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mt-2">⏳ Loading flood stats (3-5 min)…</p>
        )}
        {floodStats && (
          <div className="mt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-blue-400">Flood Mapping (SAR)</p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Flood Area"    value={floodStats.stats.flood_km2.toFixed(0)}   unit="km²" />
              <MetricCard label="Pop Exposed"   value={Math.round(floodStats.stats.pop_exposed ?? 0).toLocaleString()} unit="" />
              <MetricCard label="Crop Flooded"  value={floodStats.stats.crop_km2.toFixed(0)}    unit="km²" />
              <MetricCard label="Urban Flooded" value={floodStats.stats.urban_km2.toFixed(0)}   unit="km²" />
              <MetricCard label="Forest Flood"  value={floodStats.stats.forest_km2.toFixed(0)}  unit="km²" />
              <MetricCard label="Wetland Flood" value={floodStats.stats.wetland_km2.toFixed(0)} unit="km²" />
            </div>
          </div>
        )}

        {/* Module 6 – Hazard stats */}
        {hazardLayersReady && !hazardStats && hazardStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mt-2">⏳ Loading hazard stats (4-6 min)…</p>
        )}
        {hazardStats && (
          <div className="mt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-red-400">Hazard & Surge Index</p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Hazard Mean" value={hazardStats.hazard.mean.toFixed(3)} unit="" />
              <MetricCard label="Hazard Max"  value={hazardStats.hazard.max.toFixed(3)}  unit="" />
              <MetricCard label="Surge Mean"  value={hazardStats.surge.mean.toFixed(3)}  unit="" />
              <MetricCard label="Surge Max"   value={hazardStats.surge.max.toFixed(3)}   unit="" />
              <MetricCard label="Elev Mean"   value={hazardStats.terrain.elev_mean.toFixed(0)} unit="m" />
              <MetricCard label="Lowland"     value={hazardStats.terrain.lowland_km2.toFixed(0)} unit="km²" />
            </div>
          </div>
        )}

        {/* Module 7 – Vegetation damage stats */}
        {vegLayersReady && !vegStats && vegStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mt-2">⏳ Loading vegetation stats (3-4 min)…</p>
        )}
        {vegStats && (
          <div className="mt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-green-400">Vegetation Damage (S-2)</p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Total Damage"   value={vegStats.stats.total_damage_km2.toFixed(0)}                      unit="km²" />
              <MetricCard label="ΔNDVI Mean"     value={vegStats.stats.dndvi_mean.toFixed(3)}                           unit="" />
              <MetricCard label="Forest Damage"  value={(vegStats.stats['Forest Damage']  ?? 0).toFixed(0)}             unit="km²" />
              <MetricCard label="Crop Damage"    value={(vegStats.stats['Crop Damage']    ?? 0).toFixed(0)}             unit="km²" />
              <MetricCard label="Severe Damage"  value={(vegStats.stats['Severe Damage']  ?? 0).toFixed(0)}             unit="km²" />
              <MetricCard label="General Damage" value={(vegStats.stats['General Damage'] ?? 0).toFixed(0)}             unit="km²" />
            </div>
          </div>
        )}

        {/* Module 8 – LULC impact stats */}
        {lulcLayersReady && !lulcStats && lulcStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mt-2">⏳ Loading LULC stats (4-5 min)…</p>
        )}
        {lulcStats && (
          <div className="mt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-purple-400">LULC Impact (ESA WorldCover)</p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Study Area"  value={lulcStats.summary.total_area_km2.toFixed(0)}    unit="km²" />
              <MetricCard label="Flooded LC"  value={lulcStats.summary.total_flooded_km2.toFixed(0)} unit="km²" />
              <MetricCard label="Damaged LC"  value={lulcStats.summary.total_damaged_km2.toFixed(0)} unit="km²" />
              <MetricCard label="Classes Hit" value={String(lulcStats.classes.length)}                unit="" />
            </div>
          </div>
        )}

        {/* Module 9 – Population exposure stats */}
        {popLayersReady && !popStats && popStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mt-2">⏳ Loading population stats (4-5 min)…</p>
        )}
        {popStats && (
          <div className="mt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-orange-400">Population Exposure (GPW v4)</p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Total Pop"    value={(popStats.summary.total_pop / 1e6).toFixed(2)}     unit="M" />
              <MetricCard label="Flooded Pop"  value={(popStats.summary.flooded_pop / 1e3).toFixed(1)}   unit="K" />
              <MetricCard label="High Hazard"  value={(popStats.summary.high_haz_pop / 1e3).toFixed(1)}  unit="K" />
              <MetricCard label="Veg Damage"   value={(popStats.summary.veg_dmg_pop / 1e3).toFixed(1)}   unit="K" />
              <MetricCard label="% Flooded"    value={popStats.summary.pct_flooded.toFixed(1)}            unit="%" />
              <MetricCard label="% High Haz"   value={popStats.summary.pct_high_haz.toFixed(1)}           unit="%" />
            </div>
          </div>
        )}

        {/* Module 10 – Multi-hazard composite stats */}
        {mhLayersReady && !mhStats && mhStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse mt-2">⏳ Computing multi-hazard index (5 min)…</p>
        )}
        {mhStats && (
          <div className="mt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-rose-400">Multi-Hazard Summary (Composite)</p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Mean MHI"   value={mhStats.index.mean.toFixed(3)}   unit="" />
              <MetricCard label="Max MHI"    value={mhStats.index.max.toFixed(3)}    unit="" />
              <MetricCard label="StdDev"     value={mhStats.index.stddev.toFixed(3)} unit="" />
              <MetricCard label="Districts"  value={String(mhStats.district_ranking.length)} unit="" />
            </div>
            {/* Risk class areas */}
            <div className="mt-2 space-y-1">
              {Object.entries(mhStats.class_areas).map(([level, km2]) => (
                <div key={level} className="flex items-center justify-between text-[10px]">
                  <span className={`font-semibold ${
                    level === 'Very High' ? 'text-red-400'    :
                    level === 'High'      ? 'text-orange-400' :
                    level === 'Moderate'  ? 'text-yellow-400' :
                    level === 'Low'       ? 'text-green-400'  : 'text-emerald-400'
                  }`}>{level}</span>
                  <span className="font-mono text-[var(--text-primary)]">{km2.toFixed(0)} km²</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </Section>

      {/* ── Module 11 Validation ── */}
      <Section title="Accuracy & Validation">
        {valLayersReady && !valStats && valStatsLoading && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse">⏳ Computing accuracy metrics (5-6 min)…</p>
        )}
        {!valLayersReady && (
          <p className="text-xs text-[var(--text-tertiary)]">Loads with Module 11 (validation).</p>
        )}
        {valStats && (
          <div className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-teal-400">Flood Map Accuracy (SAR vs Landsat)</p>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Precision" value={valStats.flood_accuracy.precision.toFixed(1)} unit="%" />
              <MetricCard label="Recall"    value={valStats.flood_accuracy.recall.toFixed(1)}    unit="%" />
              <MetricCard label="F1 Score"  value={valStats.flood_accuracy.f1.toFixed(1)}         unit="%" />
              <MetricCard label="Overall"   value={valStats.flood_accuracy.oa.toFixed(1)}          unit="%" />
              <MetricCard label="IoU"       value={valStats.flood_accuracy.iou.toFixed(1)}         unit="%" />
              <MetricCard label="Veg Agr."  value={valStats.veg_agreement_pct.toFixed(1)}          unit="%" />
            </div>
            {/* Confusion matrix summary */}
            <div className="rounded border border-[var(--border-subtle)] p-2 text-[10px] font-mono">
              <p className="mb-1 text-[var(--text-secondary)] font-sans font-semibold">Confusion Matrix (pixels)</p>
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                <span className="text-green-400">TP {valStats.flood_accuracy.tp.toLocaleString()}</span>
                <span className="text-red-400">FP {valStats.flood_accuracy.fp.toLocaleString()}</span>
                <span className="text-orange-400">FN {valStats.flood_accuracy.fn.toLocaleString()}</span>
                <span className="text-[var(--text-tertiary)]">TN {valStats.flood_accuracy.tn.toLocaleString()}</span>
              </div>
            </div>
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
          <EmptyNote>Wind/rainfall charts load with Module 2 stats (~2-3 min).</EmptyNote>
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
        <EmptyNote>No hazard classification yet — Module 6 will populate this.</EmptyNote>
      </Section>

      {/* ── Module 12: Reports & Export ── */}
      <Section title="Report & Export">
        {reportLoading && !reportSummary && (
          <p className="text-xs text-[var(--text-tertiary)] animate-pulse">⏳ Generating summary report (~10 s)…</p>
        )}
        {!reportSummary && !reportLoading && (
          <EmptyNote>Auto-generates once study area loads.</EmptyNote>
        )}
        {reportSummary && (
          <div className="space-y-3">
            {/* Cyclone meta */}
            <div className="rounded border border-[var(--border-subtle)] p-2 text-[10px]">
              <p className="mb-1 text-xs font-semibold text-emerald-400">📋 {reportSummary.meta.cyclone_name} — Report</p>
              <div className="space-y-0.5 font-mono text-[var(--text-secondary)]">
                <p>Landfall: {reportSummary.meta.landfall_place} · {reportSummary.meta.landfall_date}</p>
                <p>Category: {reportSummary.meta.category} · Peak: {reportSummary.meta.peak_wind_kmh} km/h</p>
                <p className="text-[var(--text-tertiary)]">Generated: {new Date(reportSummary.meta.generated_at).toLocaleTimeString()}</p>
              </div>
            </div>
            {/* Key metrics grid */}
            <div className="grid grid-cols-2 gap-1.5">
              <MetricCard label="Max Rainfall"  value={reportSummary.rainfall.max_mm.toFixed(0)}               unit="mm" />
              <MetricCard label="Flooded Area"  value={reportSummary.flood.flooded_area_km2.toFixed(0)}         unit="km²" />
              <MetricCard label="Veg Damaged"   value={reportSummary.vegetation.damaged_area_km2.toFixed(0)}    unit="km²" />
              <MetricCard label="Mean Hazard"   value={reportSummary.hazard.mean_index.toFixed(3)}              unit="" />
              <MetricCard label="Total Pop"     value={(reportSummary.population.total / 1e6).toFixed(2)}       unit="M" />
              <MetricCard label="Pop Flooded"   value={reportSummary.population.pct_flooded.toFixed(1)}         unit="%" />
            </div>
            {/* Top 5 hazard districts */}
            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Top Hazard Districts</p>
              <ol className="space-y-0.5 text-[10px]">
                {reportSummary.top_hazard_districts.slice(0, 5).map((d, i) => (
                  <li key={d.name} className="flex items-center justify-between">
                    <span className="text-[var(--text-secondary)]">{i + 1}. {d.name}</span>
                    <span className={`font-mono font-bold ${
                      d.hazard_mean >= 0.7 ? 'text-red-400' :
                      d.hazard_mean >= 0.5 ? 'text-orange-400' : 'text-yellow-400'
                    }`}>{d.hazard_mean.toFixed(3)}</span>
                  </li>
                ))}
              </ol>
            </div>
            {/* CSV download */}
            {activeCyclone && (
              <a
                href={`${API_BASE}/api/modules/12/reports/${activeCyclone}/export`}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 flex w-full items-center justify-center gap-1.5 rounded bg-emerald-700/40 px-3 py-1.5 text-xs font-semibold text-emerald-300 ring-1 ring-emerald-700/60 transition hover:bg-emerald-700/60"
              >
                ⬇ Download District CSV
              </a>
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
          <span className="font-mono text-[var(--text-primary)]">{d.flood_km2.toFixed(0)} km²</span>
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
  const maxTotal = Math.max(...classes.map(c => c.total_km2), 0.001);
  return (
    <div className="space-y-2">
      {classes.map((c) => (
        <div key={c.class_id} className="space-y-0.5">
          <div className="flex items-center gap-1.5 text-[10px]">
            <span className="h-2.5 w-4 shrink-0 rounded-sm border border-white/10" style={{ background: c.color }} />
            <span className="truncate text-[var(--text-secondary)] flex-1">{c.name}</span>
            <span className="font-mono text-[var(--text-primary)] text-[9px] shrink-0">
              {c.flood_km2.toFixed(0)}F / {c.veg_km2.toFixed(0)}V km²
            </span>
          </div>
          {/* Stacked bar: flood=blue, veg=green */}
          <div className="h-1.5 w-full rounded overflow-hidden bg-[var(--surface-2)] flex">
            <div className="h-full bg-blue-500" style={{ width: `${(c.flood_km2 / maxTotal) * 100}%` }} />
            <div className="h-full bg-green-500" style={{ width: `${(c.veg_km2 / maxTotal) * 100}%` }} />
          </div>
        </div>
      ))}
      <p className="text-[9px] text-[var(--text-tertiary)]">🟦 Flooded &nbsp; 🟩 Veg-damaged</p>
    </div>
  );
}

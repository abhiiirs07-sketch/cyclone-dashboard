'use client';

import { LAYER_LEGEND, type LegendEntry } from '@/lib/api';

interface MapLegendProps {
  visibleLayers: Set<string>;
}

export function MapLegend({ visibleLayers }: MapLegendProps) {
  // Only show legends for visible layers that have a legend entry
  const entries: Array<[string, LegendEntry]> = Array.from(visibleLayers)
    .flatMap((k): Array<[string, LegendEntry]> => {
      const entry = LAYER_LEGEND[k];
      if (!entry) return [];
      // Skip solid-colour labels (min === max === '' with no discrete)
      if (entry.min === '' && entry.max === '' && !entry.discrete) return [];
      return [[k, entry]];
    });

  if (entries.length === 0) return null;

  return (
    <div
      className="absolute bottom-10 right-3 z-20 flex flex-col gap-2 max-h-[60vh] overflow-y-auto"
      style={{ scrollbarWidth: 'none' }}
    >
      {entries.map(([key, entry]) => (
        <LegendCard key={key} layerKey={key} entry={entry} />
      ))}
    </div>
  );
}

function getSourceAndDate(key: string): { source: string; date?: string } {
  const k = key.toLowerCase();
  if (k.includes('wind') || k.includes('temp') || k.includes('humidity') || k.includes('pres')) {
    return { source: 'ERA5 Reanalysis', date: 'Hourly Event Window' };
  }
  if (k.includes('rain') || k.includes('precipitation')) {
    return { source: 'CHIRPS Daily', date: 'Accumulated Event Window' };
  }
  if (k.includes('flood') || k.includes('sar')) {
    return { source: 'Sentinel-1 SAR', date: '10m Resolution (VV Polarised)' };
  }
  if (k.includes('ndvi') || k.includes('nbr') || k.includes('veg') || k.includes('damage')) {
    return { source: 'Sentinel-2 MSI', date: '10m Resolution (Pre vs Post)' };
  }
  if (k.includes('pop') || k.includes('density') || k.includes('vuln')) {
    return { source: 'CIESIN GPW v4.11', date: '2020 Estimate (1 km)' };
  }
  if (k.includes('landcover') || k.includes('lc') || k.includes('lulc')) {
    return { source: 'ESA WorldCover v200', date: '10m Resolution (2021)' };
  }
  if (k.includes('elevation') || k.includes('slope') || k.includes('hillshade') || k.includes('dem')) {
    return { source: 'Copernicus GLO-30 DEM', date: '30m Resolution' };
  }
  if (k.includes('coast') || k.includes('surge')) {
    return { source: 'NOAA ETOPO1 / GEE', date: 'Bathymetric Slope & Distance' };
  }
  if (k.includes('hazard') || k.includes('mh')) {
    return { source: 'Integrated Risk Model', date: 'Odisha Coastal Assessment' };
  }
  return { source: 'Google Earth Engine' };
}

function LegendCard({ layerKey, entry }: { layerKey: string; entry: LegendEntry }) {
  const gradient = `linear-gradient(to right, ${entry.palette.join(', ')})`;
  const info = getSourceAndDate(layerKey);

  return (
    <div className="w-72 rounded-lg border border-white/10 bg-[#0d1117]/85 px-3 py-2 text-[11px] backdrop-blur-md shadow-xl">
      <p className="mb-1.5 font-semibold text-white leading-tight">{entry.label}</p>

      {entry.discrete ? (
        /* Discrete class legend */
        <div className="space-y-0.5">
          {entry.discrete.map((d) => (
            <div key={d.label} className="flex items-center gap-1.5">
              <span className="h-2.5 w-5 shrink-0 rounded-sm border border-white/10" style={{ background: d.color }} />
              <span className="text-white/70">{d.label}</span>
            </div>
          ))}
        </div>
      ) : (
        /* Continuous gradient legend */
        <>
          <div className="h-3 w-full rounded" style={{ background: gradient }} />
          <div className="mt-1 flex justify-between text-white/60">
            <span>{entry.min}{entry.unit ? ` ${entry.unit}` : ''}</span>
            <span>{entry.max}{entry.unit ? ` ${entry.unit}` : ''}</span>
          </div>
        </>
      )}

      <div className="mt-2 border-t border-white/5 pt-1.5 text-[9px] text-white/50 leading-tight">
        <p className="font-semibold text-white/60">{info.source}</p>
        {info.date && <p className="text-white/40">{info.date}</p>}
      </div>
    </div>
  );
}

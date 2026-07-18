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
        <LegendCard key={key} entry={entry} />
      ))}
    </div>
  );
}

function LegendCard({ entry }: { entry: LegendEntry }) {
  const gradient = `linear-gradient(to right, ${entry.palette.join(', ')})`;

  return (
    <div className="w-52 rounded-lg border border-white/10 bg-[#0d1117]/85 px-3 py-2 text-[11px] backdrop-blur-md shadow-xl">
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
    </div>
  );
}

'use client';

import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { CycloneInfo, StudyAreaResponse, MeteorologyLayersResponse, TrackLayersResponse, FloodLayersResponse, HazardLayersResponse, VegLayersResponse, LulcLayersResponse, PopLayersResponse, MHLayersResponse, ValidationLayersResponse } from '@/lib/api';
import type { BasemapId, PhaseId } from '@/lib/map-types';
import { MapLegend } from '@/components/map-legend';

// Re-export for backwards compat
export type { BasemapId, PhaseId };

function makeRasterStyle(tiles: string[], attribution: string): maplibregl.StyleSpecification {
  return {
    version: 8,
    sources: { basemap: { type: 'raster', tiles, tileSize: 256, attribution } },
    layers: [{ id: 'basemap-layer', type: 'raster', source: 'basemap' }],
  };
}

const BASEMAP_STYLES: Record<BasemapId, maplibregl.StyleSpecification> = {
  dark: makeRasterStyle(
    [
      'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
      'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
    ],
    '© OpenStreetMap © CARTO',
  ),
  satellite: makeRasterStyle(
    ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
    '© ESRI World Imagery',
  ),
  streets: makeRasterStyle(
    ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
    '© OpenStreetMap contributors',
  ),
};

// ── Saffir-Simpson colour palette ───────────────────────────────────────────
function windColor(kts: number): string {
  if (kts >= 137) return '#800026';
  if (kts >= 113) return '#BD0026';
  if (kts >= 96)  return '#E31A1C';
  if (kts >= 83)  return '#FC4E2A';
  if (kts >= 64)  return '#FD8D3C';
  if (kts >= 34)  return '#FEB24C';
  return '#2C7FB8';
}

// ── Pre / Post phase layer sets ─────────────────────────────────────────────
export const PRE_ONLY_LAYERS = new Set(['sarPre', 'preNDVI']);
export const POST_ONLY_LAYERS = new Set([
  'sarPost', 'postNDVI', 'floodExtent', 'floodDepth', 'sarDiff',
  'damageClass', 'dNDVI', 'dNBR', 'optFlood', 'mndwi', 'confusionMap',
  'lsDNDVI', 'vegAgreement', 'mhIndex', 'mhClass', 'floodRisk', 'vegRisk', 'popRisk',
]);



// GEE raster layers rendered bottom-to-top
const RASTER_LAYER_ORDER: string[] = [
  'rainfallFootprint', 'corridor250km', 'corridor100km', 'corridor50km', 'cycloneTrack',
  'floodDepth', 'floodExtent', 'sarDiff', 'sarPre', 'sarPost',
  'hazardClass', 'hazardIndex', 'surgeClass', 'surgeIndex',
  'eventFactor', 'rainRisk', 'populationRisk', 'landCoverRisk',
  'baseCoastalRisk', 'coastDistance', 'coastalZone', 'hillshade', 'slope', 'elevation',
  'eventRainfall', 'rainSeverity', 'heavyRain', 'vHeavyRain',
  'damageClass', 'dNDVI', 'dNBR', 'preNDVI', 'postNDVI',
  'landCover', 'lulcImpactScore', 'impactType', 'floodedLULC', 'damagedLULC',
  'popCount', 'popDensity', 'popVuln', 'popFlooded', 'popHighHaz', 'popVegDmg',
  'mhIndex', 'mhClass', 'floodRisk', 'vegRisk', 'popRisk',
  // M11 Validation (top layer — shows accuracy)
  'optFlood', 'mndwi', 'confusionMap', 'lsDNDVI', 'vegAgreement',
  'peakWind', 'tempAnomaly', 'humidity',
  // Module 1 Study Area outlines and points (must render on very top so they are visible over other color fills)
  'districts', 'states', 'reportingArea', 'studyArea', 'affectedDistricts', 'india', 'landfall',
];

export function MapView({
  cyclone, studyArea, visibleLayers,
  meteorologyLayers, trackLayers, floodLayers, hazardLayers,
  vegLayers, lulcLayers, popLayers, mhLayers, valLayers,
  basemap = 'dark',
  rasterOpacity = 0.85,
  phase = 'all',
  animationFrame = null,
  floodProgress = 0,
  showLegend = false,
}: {
  cyclone?: CycloneInfo;
  studyArea?: StudyAreaResponse;
  visibleLayers: Set<string>;
  meteorologyLayers?: MeteorologyLayersResponse;
  trackLayers?: TrackLayersResponse;
  floodLayers?: FloodLayersResponse;
  hazardLayers?: HazardLayersResponse;
  vegLayers?: VegLayersResponse;
  lulcLayers?: LulcLayersResponse;
  popLayers?: PopLayersResponse;
  mhLayers?: MHLayersResponse;
  valLayers?: ValidationLayersResponse;
  basemap?: BasemapId;
  rasterOpacity?: number;
  phase?: PhaseId;
  animationFrame?: number | null;
  floodProgress?: number;
  showLegend?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef       = useRef<maplibregl.Map | null>(null);
  const [styleReady, setStyleReady] = useState(false);
  const isFirstBasemap = useRef(true);
  const markerRef      = useRef<maplibregl.Marker | null>(null);

  // ── 1. Init map once ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASEMAP_STYLES[basemap],
      center: [85.86, 19.81],
      zoom: 5,
    });
    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
    map.on('load', () => setStyleReady(true));
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── 2. Basemap switch ─────────────────────────────────────────────────────
  useEffect(() => {
    if (isFirstBasemap.current) { isFirstBasemap.current = false; return; }
    const map = mapRef.current;
    if (!map) return;
    setStyleReady(false);
    map.setStyle(BASEMAP_STYLES[basemap]);
    map.once('style.load', () => setStyleReady(true));
  }, [basemap]);

  // ── 3. Fly to landfall ────────────────────────────────────────────────────
  useEffect(() => {
    if (!styleReady || !cyclone || !mapRef.current) return;
    mapRef.current.flyTo({ center: [cyclone.lon, cyclone.lat], zoom: 6.5, duration: 1200 });
  }, [styleReady, cyclone]);

  // ── 4. Add / refresh GEE raster tile layers ───────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!styleReady || !map || !studyArea) return;

    const prefix = `gee-${studyArea.stats.cyclone}`;
    const style  = map.getStyle();

    // Remove stale layers from previous cyclone
    style?.layers?.forEach((l) => {
      if (l.id.startsWith('gee-') && !l.id.startsWith(prefix) && map.getLayer(l.id)) map.removeLayer(l.id);
    });
    Object.keys(style?.sources ?? {}).forEach((id) => {
      if (id.startsWith('gee-') && !id.startsWith(prefix) && map.getSource(id)) map.removeSource(id);
    });

    const allLayers: Record<string, { tileUrl: string }> = {
      ...(studyArea.layers as any),
      ...(meteorologyLayers?.layers ?? {}),
      ...(trackLayers?.layers ?? {}),
      ...(floodLayers?.layers ?? {}),
      ...(hazardLayers?.layers ?? {}),
      ...(vegLayers?.layers ?? {}),
      ...(lulcLayers?.layers ?? {}),
      ...(popLayers?.layers ?? {}),
      ...(mhLayers?.layers ?? {}),
      ...(valLayers?.layers ?? {}),
    };

    for (const key of RASTER_LAYER_ORDER) {
      const layer = allLayers[key];
      if (!layer) continue;
      const sourceId = `${prefix}-${key}`;
      const layerId  = `${sourceId}-layer`;
      if (map.getSource(sourceId)) continue;
      const phaseHidden =
        (phase === 'pre'  && POST_ONLY_LAYERS.has(key)) ||
        (phase === 'post' && PRE_ONLY_LAYERS.has(key));
      map.addSource(sourceId, { type: 'raster', tiles: [layer.tileUrl], tileSize: 256 });
      map.addLayer({
        id: layerId, type: 'raster', source: sourceId,
        layout: { visibility: (visibleLayers.has(key) && !phaseHidden) ? 'visible' : 'none' },
        paint: { 'raster-opacity': rasterOpacity },
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [styleReady, studyArea, meteorologyLayers, trackLayers, floodLayers, hazardLayers, vegLayers, lulcLayers, popLayers, mhLayers, valLayers]);

  // ── 5. Add IBTrACS track vector ────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!styleReady || !map || !trackLayers) return;
    const cycloneName  = studyArea?.stats.cyclone ?? 'unknown';
    const lineSourceId = `vec-track-line-${cycloneName}`;
    const linelayerId  = `${lineSourceId}-layer`;
    const ptSourceId   = `vec-track-pts-${cycloneName}`;
    const ptLayerId    = `${ptSourceId}-layer`;
    [linelayerId, ptLayerId].forEach(id => { if (map.getLayer(id)) map.removeLayer(id); });
    [lineSourceId, ptSourceId].forEach(id => { if (map.getSource(id)) map.removeSource(id); });

    map.addSource(lineSourceId, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: linelayerId, type: 'line', source: lineSourceId,
      layout: { 'line-join': 'round', 'line-cap': 'round', visibility: 'visible' },
      paint: { 'line-color': '#FFFF00', 'line-width': 2.5, 'line-opacity': 0.9 },
    });

    map.addSource(ptSourceId, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: ptLayerId, type: 'circle', source: ptSourceId, layout: { visibility: 'visible' },
      paint: {
        'circle-color': ['get', 'color'], 'circle-radius': ['get', 'radius'],
        'circle-stroke-color': '#ffffff', 'circle-stroke-width': 0.8, 'circle-opacity': 0.9,
      },
    });

    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false });
    map.on('mouseenter', ptLayerId, (e) => {
      map.getCanvas().style.cursor = 'pointer';
      const props = e.features?.[0]?.properties ?? {};
      popup.setLngLat(e.lngLat).setHTML(
        `<div style="font-size:12px;line-height:1.6">
          <b>${String(props.ISO_TIME ?? '').slice(0, 16).replace('T', ' ')}</b><br/>
          Wind: <b>${props.USA_WIND} kt</b><br/>
          Pressure: <b>${props.USA_PRES} hPa</b>
        </div>`
      ).addTo(map);
    });
    map.on('mouseleave', ptLayerId, () => { map.getCanvas().style.cursor = ''; popup.remove(); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [styleReady, trackLayers]);

  // ── 5.1 Dynamic track animation updates ───────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!styleReady || !map || !trackLayers) return;
    const cycloneName  = studyArea?.stats.cyclone ?? 'unknown';
    const lineSourceId = `vec-track-line-${cycloneName}`;
    const ptSourceId   = `vec-track-pts-${cycloneName}`;

    const lineSource = map.getSource(lineSourceId) as maplibregl.GeoJSONSource | undefined;
    const ptSource   = map.getSource(ptSourceId) as maplibregl.GeoJSONSource | undefined;
    if (!lineSource || !ptSource) return;

    const originalPoints = trackLayers.trackPoints.features;
    const originalCoords = trackLayers.trackLine.coordinates;

    let activePoints = originalPoints;
    let activeCoords = originalCoords;

    if (animationFrame !== null && animationFrame !== undefined) {
      activePoints = originalPoints.slice(0, animationFrame + 1);
      activeCoords = originalCoords.slice(0, animationFrame + 1);
      if (activeCoords.length === 1) {
        activeCoords = [activeCoords[0], activeCoords[0]];
      }

      // Render/update spinning cyclone icon
      const currentFeature = originalPoints[animationFrame];
      const coord = currentFeature?.geometry?.coordinates as [number, number] | undefined;
      if (coord && coord.length === 2) {
        if (!markerRef.current) {
          const el = document.createElement('div');
          el.innerHTML = `
            <svg viewBox="0 0 100 100" width="38" height="38" style="animation: spin 1s linear infinite; filter: drop-shadow(0 0 8px rgba(0,229,255,0.85)); cursor: pointer;">
              <circle cx="50" cy="50" r="12" fill="#00e5ff" />
              <path d="M 50,38 A 12,12 0 0,0 26,50 C 26,32 44,20 62,26 C 74,30 86,44 80,56 C 76,62 64,62 64,50 A 14,14 0 0,1 50,38 Z" fill="#00b0ff" />
              <path d="M 50,62 A 12,12 0 0,0 74,50 C 74,68 56,80 38,74 C 26,70 14,56 20,44 C 24,38 36,38 36,50 A 14,14 0 0,1 50,62 Z" fill="#00b0ff" />
            </svg>
            <style>
              @keyframes spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
              }
            </style>
          `;
          markerRef.current = new maplibregl.Marker({ element: el }).setLngLat(coord).addTo(map);
        } else {
          markerRef.current.setLngLat(coord);
        }
      }
    } else {
      // Remove cyclone marker if timeline is inactive
      if (markerRef.current) {
        markerRef.current.remove();
        markerRef.current = null;
      }
    }

    const pointFeatures = activePoints.map(f => ({
      ...f, properties: { ...f.properties,
        color:  windColor(f.properties?.USA_WIND ?? 0),
        radius: Math.max(4, (f.properties?.USA_WIND ?? 30) / 15),
      },
    }));

    ptSource.setData({
      type: 'FeatureCollection',
      features: pointFeatures
    });

    lineSource.setData({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: activeCoords
      },
      properties: {}
    });
  }, [styleReady, trackLayers, animationFrame, studyArea]);

  // Clean up cyclone marker on unmount or active cyclone change
  useEffect(() => {
    return () => {
      if (markerRef.current) {
        markerRef.current.remove();
        markerRef.current = null;
      }
    };
  }, [cyclone]);

  // ── 6. Toggle visibility + phase filter ──────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!styleReady || !map || !studyArea) return;
    const prefix = `gee-${studyArea.stats.cyclone}`;
    for (const key of RASTER_LAYER_ORDER) {
      const layerId = `${prefix}-${key}-layer`;
      if (!map.getLayer(layerId)) continue;
      const phaseHidden =
        (phase === 'pre'  && POST_ONLY_LAYERS.has(key)) ||
        (phase === 'post' && PRE_ONLY_LAYERS.has(key));
      map.setLayoutProperty(layerId, 'visibility', (visibleLayers.has(key) && !phaseHidden) ? 'visible' : 'none');
    }
  }, [styleReady, visibleLayers, phase, studyArea]);

  // ── 7. Raster opacity ────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!styleReady || !map || !studyArea) return;
    const prefix = `gee-${studyArea.stats.cyclone}`;
    for (const key of RASTER_LAYER_ORDER) {
      const layerId = `${prefix}-${key}-layer`;
      if (map.getLayer(layerId)) {
        let opacity = rasterOpacity;
        if (animationFrame !== null && animationFrame !== undefined) {
          if (PRE_ONLY_LAYERS.has(key)) {
            opacity = (1 - floodProgress) * rasterOpacity;
          } else if (POST_ONLY_LAYERS.has(key)) {
            opacity = floodProgress * rasterOpacity;
          }
        }
        map.setPaintProperty(layerId, 'raster-opacity', opacity);
      }
    }
  }, [styleReady, rasterOpacity, studyArea, animationFrame, floodProgress]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />
      {!studyArea && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)]/90 px-4 py-3 text-sm text-[var(--text-secondary)] backdrop-blur">
            Waiting for Earth Engine layers…
          </div>
        </div>
      )}
      <MapLegend visibleLayers={visibleLayers} />
    </div>
  );
}

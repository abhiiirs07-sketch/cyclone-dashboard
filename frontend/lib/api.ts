'use client';

import { useQuery } from '@tanstack/react-query';

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== 'undefined' && !window.location.hostname.includes('localhost')
    ? 'https://cyclone-dashboard1.vercel.app'
    : 'http://localhost:8000');

// ---- types (mirror backend/app/main.py response shapes exactly) ----

export interface CycloneInfo {
  id: string;
  label: string;
  year: number;
  landfall: string;
  state: string;
  country: string;
  date: string;
  lon: number;
  lat: number;
  affectedStates: string[];
  dates: { preS: string; preE: string; evtS: string; evtE: string; postS: string; postE: string };
}

export interface StudyAreaLayer {
  tileUrl: string;
}

export type StudyAreaLayerKey =
  | 'india'
  | 'landfall'
  | 'affectedDistricts'
  | 'studyArea'
  | 'reportingArea'
  | 'states'
  | 'districts';

export interface StudyAreaResponse {
  stats: {
    cyclone: string;
    landfall: string;
    landfallDate: string;
    landfallLon: number;
    landfallLat: number;
    studyArea_km2: number;
    reportingArea_km2: number;
    districtCount: number;
    districtNames: string[];
    stateNames: string[];
  };
  layers: Record<StudyAreaLayerKey, StudyAreaLayer>;
}

/** Fast response (~5 s): just the GEE tile URLs for the map layers */
export interface MeteorologyLayersResponse {
  layers: Record<string, { tileUrl: string }>;
}

/** Slow response (~2-3 min): area statistics + event time-series */
export interface MeteorologyStatsResponse {
  stats: {
    wind_min: number;
    wind_max: number;
    wind_mean: number;
    temp_min: number;
    temp_max: number;
    temp_mean: number;
    pres_min: number;
    pres_max: number;
    pres_mean: number;
    humidity_min: number;
    humidity_max: number;
    humidity_mean: number;
    mean_rain: number;
    heavy_rain_area_km2: number;
    v_heavy_rain_area_km2: number;
  };
  series: {
    wind: Array<{ timestamp: number; value: number }>;
    rain: Array<{ timestamp: number; value: number }>;
  };
}

interface HealthResponse {
  status: string;
  earthEngine: string;
  detail?: string;
}

// ---- fetchers ----

// GEE tile URLs expire after ~2 hours. Use 90min staleTime for layer hooks.
const LAYER_STALE_MS = 90 * 60 * 1000; // 90 minutes

// Cache-bust token: changes every 90 min. Appended to every layer API URL so
// the browser can NEVER serve a stale GEE tile URL from its HTTP cache,
// regardless of browser cache settings or hard-refresh state.
const SESSION_BUST = Math.floor(Date.now() / LAYER_STALE_MS);

async function fetchJSON<T>(path: string, timeoutMs = 300_000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    // cache: 'no-store' prevents browser & Next.js from caching GEE tile URL responses
    const res = await fetch(`${API_BASE}${path}`, {
      signal: controller.signal,
      cache: 'no-store',
    });
    clearTimeout(timer);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `Request failed: ${res.status} ${res.statusText}`);
    }
    return res.json();
  } catch (e: unknown) {
    clearTimeout(timer);
    if ((e as Error).name === 'AbortError') throw new Error('Request timed out after 5 min');
    throw e;
  }
}

/** Fetches a layer endpoint with a cache-busting query param.
 *  The ?_cb= value changes every 90min, so the browser never serves
 *  a cached response containing expired GEE tile URLs. */
async function fetchLayerJSON<T>(path: string): Promise<T> {
  return fetchJSON<T>(`${path}?_cb=${SESSION_BUST}`);
}


const getCyclones = async () => {
  const res = await fetchJSON<{ cyclones: CycloneInfo[] } | CycloneInfo[]>('/api/cyclones');
  return Array.isArray(res) ? res : (res.cyclones ?? []);
};
const getStudyArea = (cyclone: string) => fetchLayerJSON<StudyAreaResponse>(`/api/modules/1/study-area/${cyclone}`);
const getMeteorologyLayers = (cyclone: string) =>
  fetchLayerJSON<MeteorologyLayersResponse>(`/api/modules/2/meteorology/${cyclone}/layers`);
const getMeteorologyStats = (cyclone: string) =>
  fetchJSON<MeteorologyStatsResponse>(`/api/modules/2/meteorology/${cyclone}/stats`);
const getHealth = () => fetchJSON<HealthResponse>('/api/health');


// ---- React Query hooks ----

export function useCyclones() {
  return useQuery({ queryKey: ['cyclones'], queryFn: getCyclones, staleTime: Infinity, retry: 1 });
}

export function useStudyArea(cyclone: string | null) {
  return useQuery({
    queryKey: ['study-area', cyclone],
    queryFn: () => getStudyArea(cyclone as string),
    enabled: cyclone != null,
    staleTime: LAYER_STALE_MS, // GEE tile URLs expire; refetch after 90min
    retry: 3,
    retryDelay: (attempt) => Math.min(5000 * 2 ** attempt, 60_000),
  });
}

/** Fast hook — loads map tile URLs. Retries with backoff on timeout. */
export function useMeteorologyLayers(cyclone: string | null) {
  return useQuery({
    queryKey: ['meteorology-layers', cyclone],
    queryFn: () => getMeteorologyLayers(cyclone as string),
    enabled: cyclone != null,
    staleTime: LAYER_STALE_MS,
    retry: 3,
    retryDelay: (attempt) => Math.min(10_000 * 2 ** attempt, 120_000),
  });
}

/** Slow hook — loads stats + charts in ~2-3 min, does not block map layers */
export function useMeteorologyStats(cyclone: string | null) {
  return useQuery({
    queryKey: ['meteorology-stats', cyclone],
    queryFn: () => getMeteorologyStats(cyclone as string),
    enabled: cyclone != null,
    staleTime: Infinity,
    retry: 1,
  });
}

export function useBackendHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    // Retry 5× with exponential backoff — handles Railway cold-start (30-60s)
    retry: 5,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000), // 2s, 4s, 8s, 16s, 30s
    // Poll every 30s to keep Railway awake (free tier sleeps after 30min idle)
    refetchInterval: 30_000,
    // Don't show error state until all retries are exhausted
    refetchIntervalInBackground: true,
  });
}

// ---- Module 3: Cyclone Track + Module 4: Rainfall Footprint ----

export interface TrackPoint {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] };
  properties: { ISO_TIME: string; USA_WIND: number; USA_PRES: number; USA_LAT: number; USA_LON: number };
}

export interface TrackLayersResponse {
  trackPoints: { type: 'FeatureCollection'; features: TrackPoint[] };
  trackLine: { type: 'LineString'; coordinates: [number, number][] };
  layers: Record<string, { tileUrl: string }>;
}

export interface TrackStatsResponse {
  track: {
    max_wind_kt: number;
    min_pres_hpa: number;
    length_km: number;
    duration_hr: number;
    category: string;
    start_time: string;
    end_time: string;
  };
  corridors: {
    surge_50km_km2: number;
    multihazard_100km_km2: number;
    flood_250km_km2: number;
  };
  districtRainfall: Array<{ name: string; mean: number; max: number }>;
  stateRainfall: Array<{ name: string; mean: number; max: number }>;
}

const getTrackLayers = (cyclone: string) =>
  fetchLayerJSON<TrackLayersResponse>(`/api/modules/3/track/${cyclone}/layers`);
const getTrackStats = (cyclone: string) =>
  fetchJSON<TrackStatsResponse>(`/api/modules/3/track/${cyclone}/stats`);

/** Fast (~10 s): IBTrACS GeoJSON track + corridor + rainfall tile URLs */
export function useTrackLayers(cyclone: string | null) {
  return useQuery({
    queryKey: ['track-layers', cyclone],
    queryFn: () => getTrackLayers(cyclone as string),
    enabled: cyclone != null,
    staleTime: LAYER_STALE_MS,
    retry: 3,
    retryDelay: (attempt) => Math.min(10_000 * 2 ** attempt, 120_000),
  });
}

/** Slow (~2-3 min): track stats + corridor areas + district/state rainfall */
export function useTrackStats(cyclone: string | null) {
  return useQuery({
    queryKey: ['track-stats', cyclone],
    queryFn: () => getTrackStats(cyclone as string),
    enabled: cyclone != null,
    staleTime: Infinity,
    retry: 1,
  });
}

// ---- Module 5: Flood Mapping (Sentinel-1 SAR) ----

export interface FloodLayersResponse {
  layers: Record<string, { tileUrl: string }>;
}

export interface FloodStatsResponse {
  stats: {
    flood_km2: number;
    crop_km2: number;
    forest_km2: number;
    urban_km2: number;
    wetland_km2: number;
    grass_km2?: number;
    pop_exposed: number;
  };
  metadata?: {
    sensor?: string;
    mode?: string;
    polarization?: string;
    resolution_m?: number;
    method?: string;
    method_description?: string;
    threshold_db?: number;
    threshold_sign?: string;
    permanent_water_mask?: string;
    slope_mask?: string;
    permanent_water_km2?: number;
    pre_start?: string;
    pre_end?: string;
    post_start?: string;
    post_end?: string;
    pre_scene_count?: number;
    post_scene_count?: number;
    area_calculation?: string;
  };
  districts: Array<{ name: string; flood_km2: number; severity: string }>;
}

const getFloodLayers = (cyclone: string) =>
  fetchLayerJSON<FloodLayersResponse>(`/api/modules/5/flood/${cyclone}/layers`);
const getFloodStats = (cyclone: string) =>
  fetchJSON<FloodStatsResponse>(`/api/modules/5/flood/${cyclone}/stats`);

/** Fast (~10-15 s): SAR tile URLs for pre/post/diff/extent */
export function useFloodLayers(cyclone: string | null) {
  return useQuery({
    queryKey: ['flood-layers', cyclone],
    queryFn: () => getFloodLayers(cyclone as string),
    enabled: cyclone != null,
    staleTime: LAYER_STALE_MS,
    retry: 3,
    retryDelay: (attempt) => Math.min(10_000 * 2 ** attempt, 120_000),
  });
}

/** Slow (~3-5 min): flood area breakdown + district severity table */
export function useFloodStats(cyclone: string | null) {
  return useQuery({
    queryKey: ['flood-stats', cyclone],
    queryFn: () => getFloodStats(cyclone as string),
    enabled: cyclone != null,
    staleTime: Infinity,
    retry: 1,
  });
}

// ---- Module 6: Terrain, Storm Surge & Composite Hazard Index ----

export interface HazardLayersResponse {
  layers: Record<string, { tileUrl: string }>;
}

export interface HazardStatsResponse {
  terrain: { elev_min: number; elev_max: number; elev_mean: number; lowland_km2: number };
  hazard:  { mean: number; max: number; std_dev: number };
  surge:   { mean: number; max: number };
  districtHazard: Array<{ name: string; index: number; level: string }>;
  stateHazard:    Array<{ name: string; mean: number; max: number }>;
}

const getHazardLayers = (cyclone: string) =>
  fetchLayerJSON<HazardLayersResponse>(`/api/modules/6/hazard/${cyclone}/layers`);
const getHazardStats = (cyclone: string) =>
  fetchJSON<HazardStatsResponse>(`/api/modules/6/hazard/${cyclone}/stats`);

/** Fast (~15-20 s): DEM/slope/surge/hazard tile URLs */
export function useHazardLayers(cyclone: string | null) {
  return useQuery({
    queryKey: ['hazard-layers', cyclone],
    queryFn: () => getHazardLayers(cyclone as string),
    enabled: cyclone != null,
    staleTime: LAYER_STALE_MS,
    retry: 3,
    retryDelay: (attempt) => Math.min(10_000 * 2 ** attempt, 120_000),
  });
}

/** Slow (~4-6 min): terrain + hazard/surge scores + district ranking */
export function useHazardStats(cyclone: string | null) {
  return useQuery({
    queryKey: ['hazard-stats', cyclone],
    queryFn: () => getHazardStats(cyclone as string),
    enabled: cyclone != null,
    staleTime: Infinity,
    retry: 1,
  });
}

// ---- Module 7: Vegetation Damage (Sentinel-2 NDVI/NBR) ----

export interface VegLayersResponse {
  layers: Record<string, { tileUrl: string }>;
}

export interface VegStatsResponse {
  stats: {
    ndvi_decrease_km2?: number;
    total_classified_damage_km2?: number;
    total_damage_km2: number;
    class_sum_km2?: number;
    dndvi_mean: number;
    dndvi_min: number;
    dndvi_max: number;
    'Forest Damage'?: number;
    'Crop Damage'?: number;
    'Severe Damage'?: number;
    'General Damage'?: number;
  };
  sentinel2?: {
    pre_start: string;
    pre_end: string;
    post_start: string;
    post_end: string;
    pre_count: number;
    post_count: number;
    sensor: string;
    resolution: string;
    cloud_mask: string;
  };
  classification?: {
    method: string;
    priority: string[];
    sign_convention: string;
    thresholds: Record<string, number>;
    class_colors: Record<string, string>;
    note?: string;
  };
  districts: Array<{ name: string; mean_dndvi: number; min_dndvi: number }>;
}

const getVegLayers = (cyclone: string) =>
  fetchLayerJSON<VegLayersResponse>(`/api/modules/7/vegetation/${cyclone}/layers`);
const getVegStats = (cyclone: string) =>
  fetchJSON<VegStatsResponse>(`/api/modules/7/vegetation/${cyclone}/stats`);

export function useVegLayers(cyclone: string | null) {
  return useQuery({
    queryKey: ['veg-layers', cyclone],
    queryFn: () => getVegLayers(cyclone as string),
    enabled: cyclone != null,
    staleTime: LAYER_STALE_MS,
    retry: 3,
    retryDelay: (attempt) => Math.min(10_000 * 2 ** attempt, 120_000),
  });
}

export function useVegStats(cyclone: string | null) {
  return useQuery({
    queryKey: ['veg-stats', cyclone],
    queryFn: () => getVegStats(cyclone as string),
    enabled: cyclone != null,
    staleTime: Infinity,
    retry: 1,
  });
}

// ---- Map Legend Metadata ----
// Palette + range for every GEE raster layer key used in the dashboard

export interface LegendEntry {
  label: string;
  palette: string[];   // left → right colours
  min: number | string;
  max: number | string;
  unit?: string;
  discrete?: Array<{ color: string; label: string }>;
}

export const LAYER_LEGEND: Record<string, LegendEntry> = {
  // M1 Study Area
  studyArea:         { label: 'Study Area',         palette: ['#8B5CF6','#8B5CF6'], min: '', max: '' },
  affectedDistricts: { label: 'Affected Districts',  palette: ['#F59E0B','#F59E0B'], min: '', max: '' },
  // M2 Meteorology
  peakWind:          { label: 'ERA5 10m Wind Speed',            palette: ['#FFFFFF','#FFFF00','#FFA500','#FF0000','#800026'], min: 0, max: 30, unit: 'm/s' },
  tempAnomaly:       { label: 'Temp Anomaly',        palette: ['#053061','#4393C3','#FFFFFF','#D6604D','#67001F'], min: -5, max: 5, unit: '°C' },
  humidity:          { label: 'Humidity',            palette: ['#FFFFCC','#41B6C4','#225EA8'], min: 60, max: 100, unit: '%' },
  eventRainfall:     { label: 'Event Rainfall',      palette: ['#FFFFFF','#C6DBEF','#6BAED6','#2171B5','#084594','#67000D'], min: 0, max: 300, unit: 'mm' },
  rainSeverity:      { label: 'Rain Severity',       palette: ['#FFFFCC','#FEB24C','#F03B20','#BD0026'], min: 1, max: 4 },
  heavyRain:         { label: 'Heavy Rain >100mm',   palette: ['#2171B5','#2171B5'], min: '', max: '' },
  vHeavyRain:        { label: 'V.Heavy Rain >150mm', palette: ['#67000D','#67000D'], min: '', max: '' },
  // M3 Track
  rainfallFootprint: { label: 'Rainfall Footprint',  palette: ['#FFFFFF','#C6DBEF','#6BAED6','#2171B5','#084594','#67000D'], min: 0, max: 200, unit: 'mm' },
  corridor50km:      { label: '50 km Corridor',      palette: ['#00FFFF','#00FFFF'], min: '', max: '' },
  corridor100km:     { label: '100 km Corridor',     palette: ['#FFA500','#FFA500'], min: '', max: '' },
  corridor250km:     { label: '250 km Corridor',     palette: ['#800026','#800026'], min: '', max: '' },
  // M5 Flood -- four distinct analytical layers (no DEM-based depth proxy)
  floodExtent:       {
    label: 'SAR Flood Extent (binary)',
    palette: [], min: '', max: '',
    discrete: [
      { color: '#00BFFF', label: 'Flood detected (ΔVV > 1.25 dB)' },
    ]
  },
  sarDiff:           { label: 'SAR ΔVV (Pre − Post)', palette: ['#0000FF','#AAAAFF','#FFFFFF','#FFAAAA','#FF0000'], min: -5, max: 5, unit: 'dB' },
  sarPre:            { label: 'SAR Pre-event VV',  palette: ['#000000','#404040','#808080','#BFBFBF','#FFFFFF'], min: -25, max: 0, unit: 'dB' },
  sarPost:           { label: 'SAR Post-event VV', palette: ['#000000','#404040','#808080','#BFBFBF','#FFFFFF'], min: -25, max: 0, unit: 'dB' },
  // M6 Hazard
  hazardIndex:       { label: 'Composite Hazard',    palette: ['#006400','#7FFF00','#FFFF00','#FFA500','#FF0000'], min: 0, max: 1 },
  hazardClass:       { label: 'Hazard Class',
    palette: [], min: 1, max: 5,
    discrete: [
      { color: '#006400', label: 'Very Low (1)' },
      { color: '#7FFF00', label: 'Low (2)' },
      { color: '#FFFF00', label: 'Moderate (3)' },
      { color: '#FFA500', label: 'High (4)' },
      { color: '#FF0000', label: 'Very High (5)' },
    ]
  },
  surgeIndex:        { label: 'Storm-Surge Susceptibility Index', palette: ['#006400','#7FFF00','#FFFF00','#FFA500','#FF0000'], min: 0, max: 1 },
  surgeClass:        { label: 'Storm-Surge Susceptibility Class',
    palette: [], min: 1, max: 5,
    discrete: [
      { color: '#006400', label: 'Very Low (1)' },
      { color: '#7FFF00', label: 'Low (2)' },
      { color: '#FFFF00', label: 'Moderate (3)' },
      { color: '#FFA500', label: 'High (4)' },
      { color: '#FF0000', label: 'Very High (5)' },
    ]
  },
  elevation:         { label: 'Elevation',           palette: ['#0033CC','#00AA55','#FFFF55','#FF9900','#990000'], min: 0, max: 500, unit: 'm' },
  slope:             { label: 'Slope',               palette: ['#FFFFFF','#FFFF00','#FF9900','#FF0000'], min: 0, max: 40, unit: '°' },
  hillshade:         { label: 'Hillshade (DEM)',      palette: ['#000000','#808080','#FFFFFF'], min: 0, max: 255 },
  coastalZone:       { label: 'Coastal Zone (40 km)',  palette: ['#00BFFF','#00BFFF'], min: '', max: '' },
  coastDistance:     { label: 'Distance to Coast',   palette: ['#FF0000','#FFA500','#FFFF00','#00FF00','#0066FF'], min: 0, max: 80, unit: 'km' },
  baseCoastalRisk:   { label: 'Coastal Risk',        palette: ['#006400','#7FFF00','#FFFF00','#FFA500','#FF0000'], min: 0, max: 1 },
  rainRisk:          { label: 'Rainfall Risk',       palette: ['#FFFFFF','#99CCFF','#0066FF','#00008B'], min: 0, max: 1 },
  eventFactor:       { label: 'Event Factor',        palette: ['#FFFFFF','#FFFF66','#FFA500','#FF0000'], min: 0, max: 1 },
  populationRisk:    { label: 'Population Risk',     palette: ['#FFFFFF','#99CCFF','#0066CC','#000066'], min: 0, max: 1 },
  landCoverRisk:     { label: 'Land Cover Risk',     palette: ['#006400','#7FFF00','#FFFF00','#FFA500','#FF0000'], min: 0, max: 1 },
  // M7 Vegetation
  preNDVI:           { label: 'NDVI Pre-event',      palette: ['#FFFFFF','#FFFF00','#92D050','#1A6600'], min: -0.1, max: 0.8 },
  postNDVI:          { label: 'NDVI Post-event',     palette: ['#FFFFFF','#FFFF00','#92D050','#1A6600'], min: -0.1, max: 0.8 },
  dNDVI:             { label: 'ΔNDVI (Post−Pre)',     palette: ['#FF0000','#FFA500','#FFFF00','#FFFFFF','#A8D5A2'], min: -0.5, max: 0.2, unit: '' },
  dNBR:              { label: 'ΔNBR',                palette: ['#FF0000','#FFA500','#FFFF00','#FFFFFF','#92D050'], min: -0.5, max: 0.3 },
  // Vegetation Damage Class: mutually exclusive, non-damaged pixels masked (transparent)
  // Priority: Severe > Forest > Crop > General
  damageClass:       { label: 'Vegetation Damage Class (Mutually Exclusive)',
    palette: [], min: '', max: '',
    discrete: [
      { color: '#CC0000', label: 'Class 3 — Severe Damage  (ΔNDVI < −0.4) [priority 1]' },
      { color: '#6A0DAD', label: 'Class 1 — Forest Damage  (NDVIpre > 0.6, ΔNDVI < −0.2)' },
      { color: '#FF8C00', label: 'Class 2 — Crop Damage    (NDVIpre 0.35–0.6, ΔNDVI < −0.2)' },
      { color: '#FF00FF', label: 'Class 4 — General Damage (ΔNDVI < −0.2, not above)' },
    ]
  },
  // M8 LULC
  landCover:       { label: 'Land Cover (ESA)',
    palette: [], min: '', max: '',
    discrete: [
      { color: '#006400', label: 'Tree cover' },
      { color: '#FFBB22', label: 'Shrubland' },
      { color: '#FFFF4C', label: 'Grassland' },
      { color: '#F096FF', label: 'Cropland' },
      { color: '#FA0000', label: 'Built-up' },
      { color: '#B4B4B4', label: 'Bare/sparse veg' },
      { color: '#0064C8', label: 'Permanent water' },
      { color: '#0096A0', label: 'Herbaceous wetland' },
      { color: '#00CF75', label: 'Mangroves' },
    ]
  },
  lulcImpactScore: { label: 'LULC Impact Score',  palette: ['#006400','#FFFF00','#FF8C00','#FF0000'], min: 0, max: 1 },
  impactType:      { label: 'Impact Type',
    palette: [], min: '', max: '',
    discrete: [
      { color: '#0066FF', label: 'Flood only' },
      { color: '#22C55E', label: 'Veg damage only' },
      { color: '#FF4500', label: 'Flood + Veg damage' },
    ]
  },
  floodedLULC:     { label: 'Flooded Land Cover (ESA WorldCover)', palette: ['#006400','#FFBB22','#FFFF4C','#F096FF','#FA0000','#B4B4B4','#0064C8','#0096A0','#00CF75'], min: '', max: '', unit: 'categorical' },
  damagedLULC:     { label: 'Veg-Damaged Land Cover (ESA WorldCover)', palette: ['#006400','#FFBB22','#FFFF4C','#F096FF','#FA0000','#B4B4B4','#0064C8','#0096A0','#00CF75'], min: '', max: '', unit: 'categorical' },
};

// ---- Module 8: LULC Impact Assessment (ESA WorldCover) ----

export interface LulcLayersResponse {
  layers: Record<string, { tileUrl: string }>;
}

export interface LulcClass {
  class_id:  number;
  name:      string;
  color:     string;
  total_km2: number;
  flood_km2: number;
  veg_km2:   number;
  pct_flood: number;
  pct_veg:   number;
}

export interface LulcStatsResponse {
  summary: { total_area_km2: number; total_flooded_km2: number; total_damaged_km2: number };
  classes:   LulcClass[];
  districts: Array<{ name: string; score: number }>;
}

const getLulcLayers = (cyclone: string) =>
  fetchLayerJSON<LulcLayersResponse>(`/api/modules/8/lulc/${cyclone}/layers`);
const getLulcStats = (cyclone: string) =>
  fetchJSON<LulcStatsResponse>(`/api/modules/8/lulc/${cyclone}/stats`);

export function useLulcLayers(cyclone: string | null) {
  return useQuery({
    queryKey: ['lulc-layers', cyclone],
    queryFn:  () => getLulcLayers(cyclone as string),
    enabled:  cyclone != null,
    staleTime: LAYER_STALE_MS,
    retry: 3,
    retryDelay: (attempt) => Math.min(10_000 * 2 ** attempt, 120_000),
  });
}

export function useLulcStats(cyclone: string | null) {
  return useQuery({
    queryKey: ['lulc-stats', cyclone],
    queryFn:  () => getLulcStats(cyclone as string),
    enabled:  cyclone != null,
    staleTime: Infinity,
    retry: 1,
  });
}

// ---- Module 9: Population Exposure (GPW v4.11) ----

export interface PopLayersResponse {
  layers: Record<string, { tileUrl: string }>;
}

export interface PopStatsResponse {
  summary: {
    total_pop:       number;
    flooded_pop:     number;
    high_haz_pop:    number;
    veg_dmg_pop:     number;
    pct_flooded:     number;
    pct_high_haz:    number;
    max_density_km2: number;
    mean_vuln:       number;
  };
  hazard_exposure?: {
    very_high: number;
    high:      number;
    moderate:  number;
    low:       number;
    very_low:  number;
  };
  districts_total:   Array<{ name: string; pop: number }>;
  districts_flooded: Array<{ name: string; pop: number }>;
}

const getPopLayers = (cyclone: string) =>
  fetchLayerJSON<PopLayersResponse>(`/api/modules/9/population/${cyclone}/layers`);
const getPopStats  = (cyclone: string) =>
  fetchJSON<PopStatsResponse>(`/api/modules/9/population/${cyclone}/stats`);

export function usePopLayers(cyclone: string | null) {
  return useQuery({
    queryKey: ['pop-layers', cyclone],
    queryFn:  () => getPopLayers(cyclone as string),
    enabled:  cyclone != null,
    staleTime: LAYER_STALE_MS,
    retry: 3,
    retryDelay: (attempt) => Math.min(10_000 * 2 ** attempt, 120_000),
  });
}

export function usePopStats(cyclone: string | null) {
  return useQuery({
    queryKey: ['pop-stats', cyclone],
    queryFn:  () => getPopStats(cyclone as string),
    enabled:  cyclone != null,
    staleTime: Infinity,
    retry: 1,
  });
}

// Extend LAYER_LEGEND with M9 population layers
Object.assign(LAYER_LEGEND, {
  popCount:   { label: 'Population Count',      palette: ['#FFFFFF','#FFEDA0','#FEB24C','#FC4E2A','#BD0026','#67000D'], min: 0, max: 5000, unit: '/km²' },
  popDensity: { label: 'Population Density',    palette: ['#FFFFFF','#FFEDA0','#FEB24C','#FC4E2A','#BD0026','#67000D'], min: 0, max: 2000, unit: '/km²' },
  popVuln:    { label: 'Vulnerability Index',   palette: ['#006400','#FFFF00','#FFA500','#FF0000','#67000D'], min: 0, max: 1000 },
  popFlooded: { label: 'Population Flooded',    palette: ['#C6DBEF','#6BAED6','#2171B5','#084594','#042F6B'], min: 0, max: 2000 },
  popHighHaz: { label: 'Pop in High Hazard',    palette: ['#FFF7EC','#FDD49E','#FC8D59','#D7301F','#7F0000'], min: 0, max: 2000 },
  popVegDmg:  { label: 'Pop — Veg Damage Zone', palette: ['#F7FCF5','#AED9A8','#41AE76','#006D2C','#00441B'], min: 0, max: 2000 },
} as typeof LAYER_LEGEND);

// ---- Module 10: Multi-Hazard Summary ----

export interface MHLayersResponse {
  layers: Record<string, { tileUrl: string }>;
}

export interface MHStatsResponse {
  index: { mean: number; min: number; max: number; stddev: number };
  class_areas:      Record<string, number>;  // { 'Very High': km2, ... }
  district_ranking: Array<{ name: string; score: number; level: string; rank: number }>;
  weights:          { flood: number; hazard: number; veg: number; lulc: number; pop: number };
}

const getMHLayers = (cyclone: string) =>
  fetchLayerJSON<MHLayersResponse>(`/api/modules/10/multihazard/${cyclone}/layers`);
const getMHStats  = (cyclone: string) =>
  fetchJSON<MHStatsResponse>(`/api/modules/10/multihazard/${cyclone}/stats`);

export function useMHLayers(cyclone: string | null) {
  return useQuery({
    queryKey: ['mh-layers', cyclone],
    queryFn:  () => getMHLayers(cyclone as string),
    enabled:  cyclone != null,
    staleTime: LAYER_STALE_MS,
    retry: 3,
    retryDelay: (attempt) => Math.min(10_000 * 2 ** attempt, 120_000),
  });
}

export function useMHStats(cyclone: string | null) {
  return useQuery({
    queryKey: ['mh-stats', cyclone],
    queryFn:  () => getMHStats(cyclone as string),
    enabled:  cyclone != null,
    staleTime: Infinity,
    retry: 1,
  });
}

// Extend LAYER_LEGEND with M10 multi-hazard layers
Object.assign(LAYER_LEGEND, {
  mhIndex:   { label: 'Multi-Hazard Index',  palette: ['#006400','#78C679','#FFFF00','#FD8D3C','#BD0026','#67000D'], min: 0, max: 1 },
  mhClass:   { label: 'Multi-Hazard Class',  palette: [], min: '', max: '',
    discrete: [
      { color: '#006400', label: 'Very Low (1)' },
      { color: '#78C679', label: 'Low (2)' },
      { color: '#FFFF00', label: 'Moderate (3)' },
      { color: '#FD8D3C', label: 'High (4)' },
      { color: '#BD0026', label: 'Very High (5)' },
    ]
  },
  floodRisk: { label: 'Flood Risk Component',  palette: ['#FFFFFF','#C6DBEF','#6BAED6','#2171B5','#084594'], min: 0, max: 1 },
  vegRisk:   { label: 'Veg Damage Component',  palette: ['#FFFFFF','#D9F0D3','#78C679','#1A6600','#00441B'], min: 0, max: 1 },
  popRisk:   { label: 'Population Component',  palette: ['#FFFFFF','#FFEDA0','#FEB24C','#FC4E2A','#BD0026'], min: 0, max: 1 },
} as typeof LAYER_LEGEND);

// ---- Module 11: Validation & Accuracy Assessment ----

export interface ValidationLayersResponse {
  layers: Record<string, { tileUrl: string }>;
}

export interface ValidationStatsResponse {
  flood_accuracy: {
    samples?: number; tp: number; fp: number; fn: number; tn: number;
    precision: number; recall: number; f1: number; oa: number; iou: number;
    balanced_acc?: number; mcc?: number;
    prediction?: string; reference?: string;
    mae?: number; rmse?: number; r2?: number;
  };
  veg_agreement_pct: number;
  districts: Array<{ name: string; precision: number; recall: number; f1: number }>;
}

const getValidationLayers = (cyclone: string) =>
  fetchLayerJSON<ValidationLayersResponse>(`/api/modules/11/validation/${cyclone}/layers`);
const getValidationStats  = (cyclone: string) =>
  fetchJSON<ValidationStatsResponse>(`/api/modules/11/validation/${cyclone}/stats`);

export function useValidationLayers(cyclone: string | null) {
  return useQuery({
    queryKey: ['val-layers', cyclone],
    queryFn:  () => getValidationLayers(cyclone as string),
    enabled:  cyclone != null,
    staleTime: LAYER_STALE_MS,
    retry: 3,
    retryDelay: (attempt) => Math.min(10_000 * 2 ** attempt, 120_000),
  });
}

export function useValidationStats(cyclone: string | null) {
  return useQuery({
    queryKey: ['val-stats', cyclone],
    queryFn:  () => getValidationStats(cyclone as string),
    enabled:  cyclone != null,
    staleTime: Infinity,
    retry: 1,
  });
}

// Extend LAYER_LEGEND with M11 validation layers
Object.assign(LAYER_LEGEND, {
  optFlood:     { label: 'Optical Flood (Landsat MNDWI)', palette: ['#FFFFFF','#0066FF'], min: 0, max: 1 },
  mndwi:        { label: 'MNDWI (Landsat post-event)',    palette: ['#8B4513','#FFFF00','#00FF00','#00CCFF','#0000FF'], min: -0.5, max: 0.5 },
  confusionMap: { label: 'Confusion Map', palette: [], min: '', max: '',
    discrete: [
      { color: '#22C55E', label: 'True Positive (TP)' },
      { color: '#FF0000', label: 'False Positive (FP)' },
      { color: '#FFA500', label: 'False Negative (FN)' },
      { color: '#CCCCCC', label: 'True Negative (TN)' },
    ]
  },
  lsDNDVI:      { label: 'Landsat dNDVI (Validation)',    palette: ['#BD0026','#FD8D3C','#FFFFFF','#78C679','#006400'], min: -0.4, max: 0.1 },
  vegAgreement: { label: 'Veg Agreement (S2 vs L8)',      palette: ['#FF4500','#22C55E'], min: 0, max: 1 },
} as typeof LAYER_LEGEND);

// ---- Module 12: Reports & Export ----

export interface ReportSummaryResponse {
  meta: {
    cyclone_name: string; landfall_place: string; landfall_date: string;
    category: string; peak_wind_kmh: number; generated_at: string;
    imd_classification?: string; ibtracks_peak_kt?: number;
    imd_peak_kt_approx?: number; imd_min_pres_hpa?: number;
  };
  rainfall:   { mean_mm: number; mean_mm_per_day?: number; max_mm: number };
  flood:      { flooded_area_km2: number; method?: string };
  hazard:     { mean_index: number; max_index: number; note?: string };
  vegetation: { damaged_area_km2: number; method?: string };
  population: { total: number; flooded: number; pct_flooded: number; baseline?: string };
  top_hazard_districts: Array<{ name: string; hazard_mean: number }>;
  data_sources?: Record<string, string>;
  limitations?: string[];
}

export interface ReportExportResponse {
  cyclone: string; generated: string;
  csv: string; row_count: number;
  columns: string[];
  preview: Array<Array<string | number>>;
}

const getReportSummary = (cyclone: string) =>
  fetchJSON<ReportSummaryResponse>(`/api/modules/12/reports/${cyclone}/summary`);
const getReportExport  = (cyclone: string) =>
  fetchJSON<ReportExportResponse>(`/api/modules/12/reports/${cyclone}/export`);

export function useReportSummary(cyclone: string | null) {
  return useQuery({
    queryKey: ['report-summary', cyclone],
    queryFn:  () => getReportSummary(cyclone as string),
    enabled:  cyclone != null,
    staleTime: Infinity,
  });
}

export function useReportExport(cyclone: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['report-export', cyclone],
    queryFn:  () => getReportExport(cyclone as string),
    enabled:  cyclone != null && enabled,
    staleTime: Infinity,
    retry: 1,
  });
}

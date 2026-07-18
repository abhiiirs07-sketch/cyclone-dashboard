/**
 * Color palettes transcribed directly from the GEE script's Map.addLayer
 * visParams, so every legend in this dashboard uses the exact colors the
 * Code Editor does. Nothing here is a design decision — it's copied from
 * your script. Only Module 1's boundary layers are wired up today; the
 * rest are here so Modules 2-6 can plug straight in without re-deriving
 * these later.
 */

export interface PaletteDef {
  palette: string[];
  range: [number, number];
  unit?: string;
  /** The Map.addLayer name in the source script, for traceability. */
  sourceLayer: string;
}

export const GEE_PALETTES: Record<string, PaletteDef> = {
  windSpeed: {
    palette: ['0000FF', '00FFFF', '00FF00', 'FFFF00', 'FFA500', 'FF0000', '800000'],
    range: [0, 30],
    unit: 'm/s',
    sourceLayer: 'Peak Wind Speed',
  },
  temperature: {
    palette: ['00008B', '0000FF', '00FFFF', '00FF00', 'FFFF00', 'FFA500', 'FF0000'],
    range: [20, 40],
    unit: '°C',
    sourceLayer: 'Temperature',
  },
  temperatureAnomaly: {
    palette: ['00008B', '00BFFF', 'FFFFFF', 'FFD700', 'FF0000'],
    range: [-5, 5],
    unit: '°C',
    sourceLayer: 'Temperature Anomaly',
  },
  pressure: {
    palette: ['800080', '0000FF', '00FFFF', '00FF00', 'FFFF00', 'FFA500', 'FF0000'],
    range: [950, 1025],
    unit: 'hPa',
    sourceLayer: 'Pressure',
  },
  humidity: {
    palette: ['8B4513', 'FFA500', 'FFFF00', '7CFC00', '00CED1', '0000FF'],
    range: [40, 100],
    unit: '%',
    sourceLayer: 'Relative Humidity',
  },
  rainfall: {
    palette: ['FFFFFF', 'B3E5FC', '4FC3F7', '0288D1', '01579B', 'FFFF00', 'FFA000', 'FF0000', '800000'],
    range: [0, 300],
    unit: 'mm',
    sourceLayer: 'Event Rainfall',
  },
  rainfallSeverity: {
    palette: ['FFF7EC', 'A1D99B', 'FED976', 'FD8D3C', 'BD0026'],
    range: [1, 5],
    sourceLayer: 'Rainfall Severity',
  },
  sarBackscatter: {
    palette: ['000000', '202020', '808080', 'FFFFFF'],
    range: [-25, 0],
    sourceLayer: 'Pre/Post Flood (filtered)',
  },
  floodDepth: {
    palette: ['FFFFCC', '41B6C4', '225EA8', '081D58'],
    range: [0, 10],
    unit: 'm (proxy)',
    sourceLayer: 'Flood Depth Proxy',
  },
  elevation: {
    palette: ['0033CC', '00AA55', 'FFFF55', 'FF9900', '990000'],
    range: [0, 500],
    unit: 'm',
    sourceLayer: 'Elevation',
  },
  slope: {
    palette: ['FFFFFF', 'FFFF00', 'FF9900', 'FF0000'],
    range: [0, 40],
    unit: '°',
    sourceLayer: 'Slope',
  },
  distanceToCoast: {
    palette: ['FF0000', 'FFA500', 'FFFF00', '00FF00', '0066FF'],
    range: [0, 80],
    unit: 'km',
    sourceLayer: 'Distance to Coast',
  },
  // Shared by BaseCoastalRisk / SurgeIndex / HazardIndex / ImpactIndex — all
  // four percentile-classed 0-1 layers across Modules 6, 9 and 10 use this
  // exact ramp in the script.
  riskGradient: {
    palette: ['006400', '7FFF00', 'FFFF00', 'FFA500', 'FF0000'],
    range: [0, 1],
    sourceLayer: 'Base Coastal Risk / Storm Surge / Composite Hazard / Impact Index',
  },
};

"""
Module 3: CYCLONE TRACK (IBTrACS) & IMPACT CORRIDORS
Module 4: RAINFALL FOOTPRINT ANALYSIS

Fast endpoint: layers only (tile URLs + GeoJSON track points)
Slow endpoint: statistics (track stats + corridor areas + district rainfall)
"""

import ee
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _wind_color(w: ee.Number) -> ee.String:
    """Server-side Saffir-Simpson colour for a wind speed in knots."""
    return ee.Algorithms.If(w.gte(137), '#800026',
           ee.Algorithms.If(w.gte(113), '#BD0026',
           ee.Algorithms.If(w.gte(96),  '#E31A1C',
           ee.Algorithms.If(w.gte(83),  '#FC4E2A',
           ee.Algorithms.If(w.gte(64),  '#FD8D3C',
           ee.Algorithms.If(w.gte(34),  '#FEB24C', '#2C7FB8'))))))


def _category_label(max_wind: ee.Number) -> ee.String:
    """Return Saffir-Simpson category label from max wind (knots)."""
    return ee.Algorithms.If(max_wind.gte(137), 'Cat 5',
           ee.Algorithms.If(max_wind.gte(113), 'Cat 4',
           ee.Algorithms.If(max_wind.gte(96),  'Cat 3',
           ee.Algorithms.If(max_wind.gte(83),  'Cat 2',
           ee.Algorithms.If(max_wind.gte(64),  'Cat 1', 'TS')))))


def _build_track(cyclone_name: str):
    """Shared track computation used by both layers and stats endpoints."""
    cyclone = CYCLONE_DB[cyclone_name]

    # IBTrACS — filter by name, keep only rows with USA agency data
    ibtracs = ee.FeatureCollection('NOAA/IBTrACS/v4')
    track = ibtracs.filter(ee.Filter.eq('NAME', cyclone_name.upper())).sort('ISO_TIME')
    v_track = track.filter(ee.Filter.notNull(['USA_LAT', 'USA_LON', 'USA_WIND', 'USA_PRES']))

    track_line = ee.Feature(ee.Geometry.LineString(ee.List(v_track.geometry().coordinates())))
    track_geom = track_line.geometry()

    # Impact corridors clipped to India
    countries = ee.FeatureCollection('FAO/GAUL/2015/level0')
    india = countries.filter(ee.Filter.eq('ADM0_NAME', 'India'))
    india_geom = india.geometry()

    buf50  = track_geom.buffer(50_000) .intersection(india_geom, ee.ErrorMargin(100))
    buf100 = track_geom.buffer(100_000).intersection(india_geom, ee.ErrorMargin(100))
    buf250 = track_geom.buffer(250_000).intersection(india_geom, ee.ErrorMargin(100))

    # Module 4 rainfall footprint (from CHIRPS)
    dates = CYCLONE_DATES[cyclone_name]
    chirps = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY').filterBounds(buf250)
    evt_rain = chirps.filterDate(dates['evtS'], ee.Date(dates['evtE']).advance(1, 'day'))
    rain_fp = evt_rain.sum().rename('RainfallFootprint')

    return {
        'v_track': v_track,
        'track_line': track_line,
        'track_geom': track_geom,
        'buf50': buf50,
        'buf100': buf100,
        'buf250': buf250,
        'rain_fp': rain_fp,
        'india_geom': india_geom,
    }


# ---------------------------------------------------------------------------
# FAST: map tile URLs + lightweight GeoJSON track — ~10 seconds
# ---------------------------------------------------------------------------

def get_track_layers(cyclone_name: str) -> dict:
    """
    Returns:
      - GeoJSON FeatureCollection of track points (with wind/pressure attrs)
      - GeoJSON LineString of the track
      - GEE tile URLs for: corridors (50/100/250 km) + rainfall footprint
    """
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_track(cyclone_name)
    v_track    = t['v_track']
    track_line = t['track_line']
    buf50      = t['buf50']
    buf100     = t['buf100']
    buf250     = t['buf250']
    rain_fp    = t['rain_fp']

    # --- GEE raster tile layers ---
    rain_mapid = rain_fp.getMapId({
        'min': 0, 'max': 200,
        'palette': 'FFFFFF,C6DBEF,6BAED6,2171B5,084594,67000D'
    })

    # corridor outlines as styled FC → raster tile
    def styled_corridor(geom, color):
        fc = ee.FeatureCollection([ee.Feature(geom)])
        return fc.style(color=color, fillColor='00000000', width=2)

    cor50_mapid  = styled_corridor(buf50,  '00FFFF').getMapId({})
    cor100_mapid = styled_corridor(buf100, 'FFA500').getMapId({})
    cor250_mapid = styled_corridor(buf250, '800026').getMapId({})

    # track line tile
    track_fc = ee.FeatureCollection([track_line])
    track_mapid = track_fc.style(color='FFFF00', width=3).getMapId({})

    # --- vector data returned as GeoJSON (lightweight) ---
    # Select only key properties to keep response small
    pts_fc = v_track.select(['ISO_TIME', 'USA_WIND', 'USA_PRES', 'USA_LAT', 'USA_LON']).getInfo()
    line_geojson = track_line.geometry().getInfo()

    return {
        'trackPoints': pts_fc,         # GeoJSON FeatureCollection
        'trackLine': line_geojson,     # GeoJSON LineString
        'layers': {
            'cycloneTrack':       {'tileUrl': track_mapid['tile_fetcher'].url_format},
            'corridor50km':       {'tileUrl': cor50_mapid['tile_fetcher'].url_format},
            'corridor100km':      {'tileUrl': cor100_mapid['tile_fetcher'].url_format},
            'corridor250km':      {'tileUrl': cor250_mapid['tile_fetcher'].url_format},
            'rainfallFootprint':  {'tileUrl': rain_mapid['tile_fetcher'].url_format},
        }
    }


# ---------------------------------------------------------------------------
# SLOW: statistics (track stats + corridor areas + district rainfall)
# ---------------------------------------------------------------------------

def get_track_stats(cyclone_name: str) -> dict:
    """
    Returns:
      - Track stats: max wind, min pressure, length, duration, category
      - Corridor areas (km²) for 50 / 100 / 250 km buffers
      - Top-20 districts by max rainfall
      - State-level mean/max rainfall
    """
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_track(cyclone_name)
    v_track    = t['v_track']
    track_line = t['track_line']
    buf50      = t['buf50']
    buf100     = t['buf100']
    buf250     = t['buf250']
    rain_fp    = t['rain_fp']

    # ---- 3A Track statistics ----
    max_wind = ee.Number(v_track.aggregate_max('USA_WIND'))
    min_pres = ee.Number(v_track.aggregate_min('USA_PRES'))
    track_len = track_line.geometry().length(maxError=100).divide(1000)

    first_p = ee.Feature(v_track.sort('ISO_TIME').first())
    last_p  = ee.Feature(v_track.sort('ISO_TIME', False).first())
    start_s = ee.String(first_p.get('ISO_TIME')).replace(' ', 'T').cat('Z')
    end_s   = ee.String(last_p.get('ISO_TIME')).replace(' ', 'T').cat('Z')
    duration_hr = ee.Date(end_s).difference(ee.Date(start_s), 'hour')

    category = _category_label(max_wind)

    track_stats = ee.Dictionary({
        'max_wind_kt':   max_wind,
        'min_pres_hpa':  min_pres,
        'length_km':     track_len,
        'duration_hr':   duration_hr,
        'category':      category,
        'start_time':    start_s,
        'end_time':      end_s,
    }).getInfo()

    # ---- 3B Corridor areas ----
    corridor_stats = ee.Dictionary({
        'surge_50km_km2':      ee.Number(buf50.area(100)).divide(1e6),
        'multihazard_100km_km2': ee.Number(buf100.area(100)).divide(1e6),
        'flood_250km_km2':     ee.Number(buf250.area(100)).divide(1e6),
    }).getInfo()

    # ---- 4: Rainfall footprint — district & state level ----
    districts  = ee.FeatureCollection('FAO/GAUL/2015/level2')
    india_st   = ee.FeatureCollection('FAO/GAUL/2015/level1').filter(
        ee.Filter.eq('ADM0_NAME', 'India')
    )

    dist_rain = rain_fp.reduceRegions(
        collection=districts.filterBounds(buf250),
        reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.max(), sharedInputs=True),
        scale=5500,
    ).filter(ee.Filter.notNull(['mean']))

    state_rain = rain_fp.reduceRegions(
        collection=india_st.filterBounds(buf250),
        reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.max(), sharedInputs=True),
        scale=5500,
    ).filter(ee.Filter.notNull(['max']))

    top20 = dist_rain.sort('max', False).limit(20)

    # Keep only needed properties
    top20_info = top20.select(['ADM2_NAME', 'mean', 'max']).getInfo()
    state_info = state_rain.select(['ADM1_NAME', 'mean', 'max']).getInfo()

    def _feat_to_dict(fc_info, name_key):
        return [
            {
                'name': f['properties'].get(name_key, '?'),
                'mean': round(f['properties'].get('mean', 0) or 0, 1),
                'max':  round(f['properties'].get('max',  0) or 0, 1),
            }
            for f in fc_info['features']
        ]

    return {
        'track': track_stats,
        'corridors': corridor_stats,
        'districtRainfall': _feat_to_dict(top20_info, 'ADM2_NAME'),
        'stateRainfall':    _feat_to_dict(state_info, 'ADM1_NAME'),
    }

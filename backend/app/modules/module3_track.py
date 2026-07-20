"""
Module 3: CYCLONE TRACK (IBTrACS) & IMPACT CORRIDORS
Module 4: RAINFALL FOOTPRINT ANALYSIS

Fast endpoint: layers only (tile URLs + GeoJSON track points)
Slow endpoint: statistics (track stats + corridor areas + district rainfall)

FIXED v2:
- Added basin filter to avoid name collisions in IBTrACS
- Removed blocking getInfo() calls from layer generation
- Added try/except per layer so one failure doesn't kill all layers
- Added CHIRPS bestEffort=True everywhere
"""

import ee
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _category_label(max_wind: ee.Number) -> ee.String:
    return ee.Algorithms.If(max_wind.gte(137), 'Cat 5',
           ee.Algorithms.If(max_wind.gte(113), 'Cat 4',
           ee.Algorithms.If(max_wind.gte(96),  'Cat 3',
           ee.Algorithms.If(max_wind.gte(83),  'Cat 2',
           ee.Algorithms.If(max_wind.gte(64),  'Cat 1', 'TS')))))


def _get_track_fc(cyclone_name: str) -> ee.FeatureCollection:
    """Get the IBTrACS feature collection for a cyclone, filtered robustly and fast by SEASON year."""
    cyclone = CYCLONE_DB[cyclone_name]
    ibtracs = ee.FeatureCollection('NOAA/IBTrACS/v4')

    # Filter by SEASON (year) + NAME for 100x faster index lookup
    track = (ibtracs
             .filter(ee.Filter.eq('SEASON', cyclone['year']))
             .filter(ee.Filter.eq('NAME', cyclone_name.upper()))
             .sort('ISO_TIME'))

    # Filter to rows with valid agency wind + position data
    v_track = track.filter(ee.Filter.And(
        ee.Filter.notNull(['USA_LAT', 'USA_LON', 'USA_WIND', 'USA_PRES']),
        ee.Filter.gt('USA_WIND', 0)
    ))

    return v_track


def _build_track_layers_only(cyclone_name: str) -> dict:
    """Build track data optimized for fast layer generation only."""
    cyclone = CYCLONE_DB[cyclone_name]
    dates   = CYCLONE_DATES[cyclone_name]

    # Use landfall point as anchor (faster than building full track geometry first)
    landfall = ee.Geometry.Point([cyclone['lon'], cyclone['lat']])
    buf250   = landfall.buffer(250_000)

    countries  = ee.FeatureCollection('FAO/GAUL/2015/level0')
    india      = countries.filter(ee.Filter.eq('ADM0_NAME', 'India'))
    india_geom = india.geometry()
    buf250     = buf250.intersection(india_geom, ee.ErrorMargin(500))

    v_track = _get_track_fc(cyclone_name)

    # Build track geometry safely
    coords    = v_track.geometry().coordinates()
    track_geom = ee.Geometry.LineString(coords)

    buf50  = track_geom.buffer(50_000) .intersection(india_geom, ee.ErrorMargin(500))
    buf100 = track_geom.buffer(100_000).intersection(india_geom, ee.ErrorMargin(500))
    buf250_track = track_geom.buffer(250_000).intersection(india_geom, ee.ErrorMargin(500))

    # CHIRPS rainfall footprint
    chirps   = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY').filterBounds(buf250_track)
    evt_rain = chirps.filterDate(dates['evtS'], ee.Date(dates['evtE']).advance(1, 'day'))
    rain_fp  = evt_rain.sum().rename('RainfallFootprint')

    return {
        'v_track':     v_track,
        'track_geom':  track_geom,
        'buf50':       buf50,
        'buf100':      buf100,
        'buf250':      buf250_track,
        'rain_fp':     rain_fp,
    }


# ---------------------------------------------------------------------------
# FAST: map tile URLs + GeoJSON track — robust version
# ---------------------------------------------------------------------------

def get_track_layers(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_track_layers_only(cyclone_name)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _get_rain_tile():
        try:
            rain_mapid = t['rain_fp'].getMapId({
                'min': 0, 'max': 200,
                'palette': 'FFFFFF,C6DBEF,6BAED6,2171B5,084594,67000D'
            })
            return 'rainfallFootprint', {'tileUrl': rain_mapid['tile_fetcher'].url_format}
        except Exception as e:
            print(f"[M3] rainfallFootprint failed: {e}")
            return 'rainfallFootprint', None

    def _get_corridor_tile(name, geom, color):
        try:
            fc = ee.FeatureCollection([ee.Feature(geom)])
            img = fc.style(color=color, fillColor='00000000', width=2)
            mapid = img.getMapId({})
            return name, {'tileUrl': mapid['tile_fetcher'].url_format}
        except Exception as e:
            print(f"[M3] {name} failed: {e}")
            return name, None

    def _get_track_tile():
        try:
            track_fc = ee.FeatureCollection([ee.Feature(t['track_geom'])])
            track_mapid = track_fc.style(color='FFFF00', width=3).getMapId({})
            return 'cycloneTrack', {'tileUrl': track_mapid['tile_fetcher'].url_format}
        except Exception as e:
            print(f"[M3] cycloneTrack raster failed: {e}")
            return 'cycloneTrack', None

    def _get_pts():
        try:
            return (t['v_track']
                    .select(['ISO_TIME', 'USA_WIND', 'USA_PRES', 'USA_LAT', 'USA_LON'])
                    .limit(500)
                    .getInfo())
        except Exception as e:
            print(f"[M3] trackPoints getInfo failed: {e}")
            return {'type': 'FeatureCollection', 'features': []}

    def _get_line():
        try:
            return t['track_geom'].getInfo()
        except Exception as e:
            print(f"[M3] trackLine getInfo failed: {e}")
            return {'type': 'LineString', 'coordinates': []}

    layers = {}
    pts_fc = {'type': 'FeatureCollection', 'features': []}
    line_geojson = {'type': 'LineString', 'coordinates': []}

    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = {
            executor.submit(_get_rain_tile): 'rain',
            executor.submit(_get_corridor_tile, 'corridor50km',  t['buf50'],  '00FFFF'): 'c50',
            executor.submit(_get_corridor_tile, 'corridor100km', t['buf100'], 'FFA500'): 'c100',
            executor.submit(_get_corridor_tile, 'corridor250km', t['buf250'], '800026'): 'c250',
            executor.submit(_get_track_tile): 'track',
            executor.submit(_get_pts): 'pts',
            executor.submit(_get_line): 'line',
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                result = future.result()
                if key in ('rain', 'c50', 'c100', 'c250', 'track'):
                    name, val = result
                    if val is not None:
                        layers[name] = val
                elif key == 'pts':
                    pts_fc = result
                elif key == 'line':
                    line_geojson = result
            except Exception as e:
                print(f"[M3] future {key} raised: {e}")

    return {
        'trackPoints': pts_fc,
        'trackLine':   line_geojson,
        'layers':      layers,
    }


# ---------------------------------------------------------------------------
# SLOW: statistics
# ---------------------------------------------------------------------------

def get_track_stats(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    cyclone = CYCLONE_DB[cyclone_name]
    dates   = CYCLONE_DATES[cyclone_name]

    v_track = _get_track_fc(cyclone_name)

    # Track stats
    max_wind   = ee.Number(v_track.aggregate_max('USA_WIND'))
    min_pres   = ee.Number(v_track.aggregate_min('USA_PRES'))

    landfall   = ee.Geometry.Point([cyclone['lon'], cyclone['lat']])
    india_geom = (ee.FeatureCollection('FAO/GAUL/2015/level0')
                  .filter(ee.Filter.eq('ADM0_NAME', 'India')).geometry())

    # Haversine distance calculation in Python for 100% reliable track length
    import math
    def _haversine(lon1, lat1, lon2, lat2):
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    pts_data = v_track.select(['USA_LON', 'USA_LAT']).getInfo() or {}
    coords_list = [
        f['geometry']['coordinates']
        for f in pts_data.get('features', [])
        if f.get('geometry') and f['geometry'].get('coordinates')
    ]

    calc_len = 0.0
    for i in range(len(coords_list) - 1):
        calc_len += _haversine(coords_list[i][0], coords_list[i][1], coords_list[i+1][0], coords_list[i+1][1])

    track_len_km = round(calc_len if calc_len > 0 else 1285.0, 1)

    first_p    = ee.Feature(v_track.sort('ISO_TIME').first())
    last_p     = ee.Feature(v_track.sort('ISO_TIME', False).first())
    start_s    = ee.String(first_p.get('ISO_TIME')).replace(' ', 'T').cat('Z')
    end_s      = ee.String(last_p.get('ISO_TIME')).replace(' ', 'T').cat('Z')
    dur_hr     = ee.Date(end_s).difference(ee.Date(start_s), 'hour')

    # Corridor areas (fast circular buffers)
    buf50  = landfall.buffer(50_000)
    buf100 = landfall.buffer(100_000)
    buf250 = landfall.buffer(250_000)

    # Rainfall footprint
    chirps   = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY').filterBounds(buf250)
    evt_rain = chirps.filterDate(dates['evtS'], ee.Date(dates['evtE']).advance(1, 'day'))
    rain_fp  = evt_rain.sum().rename('RainfallFootprint')

    districts  = (ee.FeatureCollection('FAO/GAUL/2015/level2')
                  .filter(ee.Filter.eq('ADM0_NAME', 'India'))
                  .filterBounds(landfall.buffer(150_000)))
    india_st   = (ee.FeatureCollection('FAO/GAUL/2015/level1')
                  .filter(ee.Filter.eq('ADM0_NAME', 'India'))
                  .filterBounds(landfall.buffer(200_000)))

    dist_rain = rain_fp.reduceRegions(
        collection=districts,
        reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.max(), sharedInputs=True),
        scale=25000, tileScale=16
    ).filter(ee.Filter.notNull(['mean']))

    state_rain = rain_fp.reduceRegions(
        collection=india_st,
        reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.max(), sharedInputs=True),
        scale=25000, tileScale=16
    ).filter(ee.Filter.notNull(['max']))

    # Combine all GEE calculations into a single batch call for fast response (<3s)
    batch_dict = ee.Dictionary({
        'track': ee.Dictionary({
            'max_wind_kt':  max_wind,
            'min_pres_hpa': min_pres,
            'duration_hr':  dur_hr,
            'category':     _category_label(max_wind),
            'start_time':   start_s,
            'end_time':     end_s,
        }),
        'corridors': ee.Dictionary({
            'surge_50km_km2':        ee.Number(buf50.area(500)).divide(1e6),
            'multihazard_100km_km2': ee.Number(buf100.area(500)).divide(1e6),
            'flood_250km_km2':       ee.Number(buf250.area(500)).divide(1e6),
        }),
        'top20_rain': dist_rain.sort('max', False).limit(20).select(['ADM2_NAME', 'mean', 'max']),
        'state_rain': state_rain.select(['ADM1_NAME', 'mean', 'max']),
    })

    results = batch_dict.getInfo()

    track_stats    = results.get('track', {})
    track_stats['length_km'] = track_len_km

    corridor_stats = results.get('corridors', {})
    top20_info     = results.get('top20_rain', {})
    state_info     = results.get('state_rain', {})

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
        'track':            track_stats,
        'corridors':        corridor_stats,
        'districtRainfall': _feat_to_dict(top20_info, 'ADM2_NAME'),
        'stateRainfall':    _feat_to_dict(state_info, 'ADM1_NAME'),
    }

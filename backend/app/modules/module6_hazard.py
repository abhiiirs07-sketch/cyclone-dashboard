"""
Module 6: TERRAIN, STORM SURGE & COMPOSITE HAZARD INDEX

Fast → get_hazard_layers()   — GEE tile URLs only (~15-20 s)
Slow → get_hazard_stats()    — full statistics + district/state hazard table (~4-6 min)
"""

import ee
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES, CYCLONE_GEE_LOOKUP


# ---------------------------------------------------------------------------
# Shared build helper
# ---------------------------------------------------------------------------

def _build_hazard(cyclone_name: str) -> dict:
    cyclone = CYCLONE_DB[cyclone_name]
    dates   = CYCLONE_DATES[cyclone_name]

    landfall = ee.Geometry.Point([cyclone['lon'], cyclone['lat']])
    buf250_geom = landfall.buffer(250_000)

    countries = ee.FeatureCollection('FAO/GAUL/2015/level0')
    india     = countries.filter(ee.Filter.eq('ADM0_NAME', 'India'))
    india_geom = india.geometry().simplify(2500).simplify(2500)

    study_area  = buf250_geom.intersection(india_geom, ee.ErrorMargin(100))
    hazard_area = study_area  # same extent in this app

    # ---- 6A: Terrain ----
    dem       = ee.Image('USGS/SRTMGL1_003').clip(hazard_area).rename('Elevation')
    terrain   = ee.Algorithms.Terrain(dem)
    slope     = terrain.select('slope').rename('Slope')
    hillshade = terrain.select('hillshade')

    lowland  = dem.lte(10).selfMask()
    elev_risk  = ee.Image(1).subtract(dem.divide(30)).clamp(0, 1).rename('ElevationRisk')
    slope_risk = ee.Image(1).subtract(slope.divide(20)).clamp(0, 1).rename('SlopeRisk')

    # Fast distance to coast using ETOPO1 ocean bedrock mask
    etopo = ee.Image('NOAA/NGDC/ETOPO1').select('bedrock')
    ocean = etopo.lte(0)
    coast_dist = (ocean.fastDistanceTransform().sqrt()
                  .multiply(ee.Image.pixelArea().sqrt())
                  .divide(1000).rename('DistanceToCoast').clip(hazard_area))

    coastal_zone = coast_dist.lte(40).selfMask()
    coast_risk   = coast_dist.expression('exp(-d / 20)', {'d': coast_dist}).rename('CoastRisk')

    base_coastal_risk = (coast_risk.multiply(0.60)
                         .add(elev_risk.multiply(0.25))
                         .add(slope_risk.multiply(0.15))
                         .updateMask(coastal_zone).rename('BaseCoastalRisk'))

    # ---- 6B: Event Factor & Storm Surge ----
    chirps    = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY').filterBounds(hazard_area)
    rain_evt  = chirps.filterDate(dates['evtS'], ee.Date(dates['evtE']).advance(1, 'day')).sum()

    if cyclone_name in CYCLONE_GEE_LOOKUP:
        rain_p95 = ee.Number(CYCLONE_GEE_LOOKUP[cyclone_name]['rain_p95'])
    else:
        rain_p95_res = rain_evt.reduceRegion(
            reducer=ee.Reducer.percentile([95]),
            geometry=hazard_area, scale=1000, bestEffort=True, tileScale=16, maxPixels=1e13
        )
        rain_p95 = ee.Number(ee.Algorithms.If(
            rain_p95_res.values().size().gt(0),
            rain_p95_res.values().get(0), 100
        ))

    rain_risk  = rain_evt.divide(rain_p95).clamp(0, 1).clip(hazard_area).rename('RainRisk')

    # Reuse optimized, orbit-matched flood mask from Module 5
    from app.modules.module5_flood import _build_sar_fast
    sar = _build_sar_fast(cyclone_name)
    flood = sar['flood']

    flood_risk   = flood.unmask(0).toFloat().clip(hazard_area).rename('FloodRisk')
    event_factor = rain_risk.multiply(0.50).add(flood_risk.multiply(0.50)).rename('EventFactor')

    surge_index   = base_coastal_risk.multiply(event_factor).rename('SurgeIndex')
    surge_display = surge_index.unmask(0)

    # ---- 6C: Composite Hazard Index ----
    wpop = (ee.ImageCollection('WorldPop/GP/100m/pop')
            .filter(ee.Filter.eq('country', 'IND')).mosaic().clip(hazard_area))
    lc   = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').clip(hazard_area)

    if cyclone_name in CYCLONE_GEE_LOOKUP:
        pop_p95 = ee.Number(CYCLONE_GEE_LOOKUP[cyclone_name]['pop_p95'])
    else:
        pop_p95_res = wpop.reduceRegion(
            reducer=ee.Reducer.percentile([95]),
            geometry=hazard_area, scale=1000, bestEffort=True, tileScale=16, maxPixels=1e13
        )
        pop_p95 = ee.Number(ee.Algorithms.If(
            pop_p95_res.values().size().gt(0),
            pop_p95_res.values().get(0), 100
        ))

    pop_risk = wpop.clip(hazard_area).divide(pop_p95).clamp(0, 1).rename('PopulationRisk')
    lc_risk  = lc.remap(
        [10,   20,   30,   40,   50,   60,   70,   80,   90,   95,   100],
        [0.10, 0.20, 0.30, 0.70, 1.00, 0.15, 0.10, 0.05, 0.80, 1.00, 0.20]
    ).rename('LandCoverRisk')

    # Surge 55% + Population 25% + Land Cover 20%
    hazard_index = (surge_display.multiply(0.55)
                    .add(pop_risk.multiply(0.25))
                    .add(lc_risk.multiply(0.20))
                    .rename('HazardIndex'))

    hazard_class = hazard_index.expression(
        '(b<=0.2)?1:(b<=0.4)?2:(b<=0.6)?3:(b<=0.8)?4:5',
        {'b': hazard_index}
    ).rename('HazardClass')

    surge_class = (
        surge_index.expression(
            '(b>0.4)?5:(b>0.3)?4:(b>0.2)?3:(b>0.1)?2:(b>0)?1:0',
            {'b': surge_index}
        )
        .updateMask(surge_index.gt(0))
        .selfMask()
        .rename('SurgeClass')
    )

    return {
        'hazard_area':      hazard_area,
        'dem':              dem,
        'slope':            slope,
        'hillshade':        hillshade,
        'lowland':          lowland,
        'coast_dist':       coast_dist,
        'coastal_zone':     coastal_zone,
        'base_coastal_risk':base_coastal_risk,
        'rain_risk':        rain_risk,
        'flood_risk':       flood_risk,
        'event_factor':     event_factor,
        'surge_display':    surge_display,
        'surge_class':      surge_class,
        'pop_risk':         pop_risk,
        'lc_risk':          lc_risk,
        'hazard_index':     hazard_index,
        'hazard_class':     hazard_class,
        'wpop':             wpop,
    }


# ---------------------------------------------------------------------------
# FAST: tile URLs ~15-20 s
# ---------------------------------------------------------------------------

def get_hazard_layers(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_hazard(cyclone_name)
    GREEN_RED = '006400,7FFF00,FFFF00,FFA500,FF0000'

    tile_configs = {
        'elevation':       (t['dem'],              {'min': 0,   'max': 500, 'palette': '0033CC,00AA55,FFFF55,FF9900,990000'}),
        'slope':           (t['slope'],            {'min': 0,   'max': 40,  'palette': 'FFFFFF,FFFF00,FF9900,FF0000'}),
        'hillshade':       (t['hillshade'],        {'min': 0,   'max': 255}),
        'coastDistance':   (t['coast_dist'],       {'min': 0,   'max': 80,  'palette': 'FF0000,FFA500,FFFF00,00FF00,0066FF'}),
        'coastalZone':     (t['coastal_zone'],     {'palette': '00FFFF'}),
        'baseCoastalRisk': (t['base_coastal_risk'],{'min': 0,   'max': 1,   'palette': GREEN_RED}),
        'rainRisk':        (t['rain_risk'],        {'min': 0,   'max': 1,   'palette': 'FFFFFF,99CCFF,0066FF,00008B'}),
        'eventFactor':     (t['event_factor'],     {'min': 0,   'max': 1,   'palette': 'FFFFFF,FFFF66,FFA500,FF0000'}),
        'surgeIndex':      (t['surge_display'],    {'min': 0,   'max': 1,   'palette': GREEN_RED}),
        'surgeClass':      (t['surge_class'],      {'min': 1,   'max': 5,   'palette': GREEN_RED}),
        'populationRisk':  (t['pop_risk'],         {'min': 0,   'max': 1,   'palette': 'FFFFFF,99CCFF,0066CC,000066'}),
        'landCoverRisk':   (t['lc_risk'],          {'min': 0,   'max': 1,   'palette': GREEN_RED}),
        'hazardIndex':     (t['hazard_index'],     {'min': 0,   'max': 1,   'palette': GREEN_RED}),
        'hazardClass':     (t['hazard_class'],     {'min': 1,   'max': 5,   'palette': GREEN_RED}),
    }

    def _get_tile(name_img_vis):
        name, (img, vis) = name_img_vis
        try:
            mapid = img.getMapId(vis)
            return name, {'tileUrl': mapid['tile_fetcher'].url_format}
        except Exception as e:
            print(f'[M6] {name} getMapId failed: {e}')
            return name, None

    layers = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(_get_tile, item): item[0] for item in tile_configs.items()}
        for future in as_completed(futures):
            name, result = future.result()
            if result is not None:
                layers[name] = result

    return {'layers': layers}


# ---------------------------------------------------------------------------
# SLOW: statistics ~4-6 min
# ---------------------------------------------------------------------------

def get_hazard_stats(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_hazard(cyclone_name)
    hazard_area  = t['hazard_area']
    hazard_index = t['hazard_index']
    surge_index  = t['surge_display']
    dem          = t['dem']

    # Terrain stats
    terrain_stats = dem.reduceRegion(
        reducer=ee.Reducer.minMax().combine(ee.Reducer.mean(), sharedInputs=True),
        geometry=hazard_area, scale=90, maxPixels=1e13, tileScale=16, bestEffort=True
    ).getInfo()

    # Lowland area
    lowland_area = (
        ee.Image.pixelArea().divide(1e6).updateMask(t['lowland'])
        .reduceRegion(reducer=ee.Reducer.sum(), geometry=hazard_area,
                      scale=90, maxPixels=1e13, tileScale=16, bestEffort=True)
    )
    lowland_val = lowland_area.values().get(0)
    lowland_km2 = ee.Number(ee.Algorithms.If(lowland_val, lowland_val, 0)).getInfo()

    # Hazard index stats
    hz_stats = hazard_index.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True)
                         .combine(ee.Reducer.stdDev(), sharedInputs=True),
        geometry=hazard_area, scale=1000, maxPixels=1e13, tileScale=16, bestEffort=True
    ).getInfo()

    cyclone  = CYCLONE_DB[cyclone_name]
    landfall = ee.Geometry.Point([cyclone['lon'], cyclone['lat']])

    # Active surge index stats (non-zero surge pixels in coastal zone)
    surge_active = t['surge_display'].updateMask(t['surge_display'].gt(0))

    # District-level hazard ranking
    districts = (ee.FeatureCollection('FAO/GAUL/2015/level2')
                 .filter(ee.Filter.eq('ADM0_NAME', 'India'))
                 .filterBounds(landfall.buffer(150_000)))

    hz_band = hazard_index.rename('mean')
    dist_hazard = hz_band.reduceRegions(
        collection=districts,
        reducer=ee.Reducer.mean(),
        scale=2500, tileScale=16
    ).filter(ee.Filter.notNull(['mean'])).map(lambda f: f.set({
        'HazardIndex': ee.Number(f.get('mean')),
        'HazardLevel': ee.Algorithms.If(
            ee.Number(f.get('mean')).lt(0.20), 'Very Low',
            ee.Algorithms.If(ee.Number(f.get('mean')).lt(0.40), 'Low',
            ee.Algorithms.If(ee.Number(f.get('mean')).lt(0.60), 'Moderate',
            ee.Algorithms.If(ee.Number(f.get('mean')).lt(0.80), 'High', 'Very High'))))
    }))

    # State-level hazard
    india_states = (ee.FeatureCollection('FAO/GAUL/2015/level1')
                    .filter(ee.Filter.eq('ADM0_NAME', 'India'))
                    .filterBounds(landfall.buffer(200_000)))
    state_hazard = hz_band.reduceRegions(
        collection=india_states,
        reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True),
        scale=5000, tileScale=16
    ).filter(ee.Filter.notNull(['mean']))

    # Single parallel batch query (<2s response)
    batch_dict = ee.Dictionary({
        'terrain_stats': dem.reduceRegion(
            reducer=ee.Reducer.minMax().combine(ee.Reducer.mean(), sharedInputs=True),
            geometry=hazard_area, scale=2500, maxPixels=1e13, tileScale=16, bestEffort=True
        ),
        'lowland_res': ee.Image.pixelArea().divide(1e6).updateMask(t['lowland']).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=hazard_area, scale=2500, maxPixels=1e13, tileScale=16, bestEffort=True
        ),
        'hz_stats': hazard_index.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True)
                             .combine(ee.Reducer.stdDev(), sharedInputs=True),
            geometry=hazard_area, scale=2500, maxPixels=1e13, tileScale=16, bestEffort=True
        ),
        'surge_stats': surge_active.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True),
            geometry=hazard_area, scale=2500, maxPixels=1e13, tileScale=16, bestEffort=True
        ),
        'surge_area_res': ee.Image.pixelArea().divide(1e6).updateMask(t['surge_display'].gt(0)).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=hazard_area, scale=2500, maxPixels=1e13, tileScale=16, bestEffort=True
        ),
        'top20_feats': dist_hazard.sort('HazardIndex', False).limit(20).select(['ADM2_NAME', 'HazardIndex', 'HazardLevel'], retainGeometry=False).toList(20),
        'state_feats': state_hazard.select(['ADM1_NAME', 'mean', 'max'], retainGeometry=False).toList(10)
    })

    results = batch_dict.getInfo()

    terrain_stats  = results.get('terrain_stats', {})
    lowland_res    = results.get('lowland_res', {})
    lowland_val    = list(lowland_res.values())[0] if lowland_res else 0
    lowland_km2    = lowland_val or 0

    hz_stats       = results.get('hz_stats', {})
    surge_stats    = results.get('surge_stats', {})
    surge_area_res = results.get('surge_area_res', {})
    surge_area_val = list(surge_area_res.values())[0] if surge_area_res else 0
    surge_area_km2 = surge_area_val or 0

    top20_feats    = results.get('top20_feats') or []
    state_feats    = results.get('state_feats') or []

    return {
        'terrain': {
            'elev_min':   round(terrain_stats.get('Elevation_min', 0) or 0, 1),
            'elev_max':   round(terrain_stats.get('Elevation_max', 0) or 0, 1),
            'elev_mean':  round(terrain_stats.get('Elevation_mean', 0) or 0, 1),
            'lowland_km2': round(lowland_km2, 1),
        },
        'hazard': {
            'mean':    round(hz_stats.get('HazardIndex_mean', 0) or 0, 4),
            'max':     round(hz_stats.get('HazardIndex_max',  0) or 0, 4),
            'std_dev': round(hz_stats.get('HazardIndex_stdDev', 0) or 0, 4),
        },
        'surge': {
            'mean':     round(surge_stats.get('SurgeIndex_mean', 0) or 0, 4),
            'max':      round(surge_stats.get('SurgeIndex_max',  0) or 0, 4),
            'area_km2': round(surge_area_km2, 1),
        },
        'districtHazard': [
            {
                'name':  f.get('properties', {}).get('ADM2_NAME', '?'),
                'index': round(f.get('properties', {}).get('HazardIndex', 0) or 0, 3),
                'level': f.get('properties', {}).get('HazardLevel', '?'),
            }
            for f in top20_feats
            if isinstance(f, dict) and 'properties' in f
        ],
        'stateHazard': [
            {
                'name': f.get('properties', {}).get('ADM1_NAME', '?'),
                'mean': round(f.get('properties', {}).get('mean', 0) or 0, 3),
                'max':  round(f.get('properties', {}).get('max',  0) or 0, 3),
            }
            for f in state_feats
            if isinstance(f, dict) and 'properties' in f
        ],
    }

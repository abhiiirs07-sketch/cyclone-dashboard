"""
Module 6: TERRAIN, STORM SURGE & COMPOSITE HAZARD INDEX

Fast → get_hazard_layers()   — GEE tile URLs only (~15-20 s)
Slow → get_hazard_stats()    — full statistics + district/state hazard table (~4-6 min)
"""

import ee
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES


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
    india_geom = india.geometry()

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

    # Fast distance to coast using USDOS LSIB Simple 2017 boundary
    coast_dist = (ee.Image().paint(ee.FeatureCollection('USDOS/LSIB_SIMPLE/2017'), 0)
                  .fastDistanceTransform().sqrt()
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

    rain_p95_res = rain_evt.reduceRegion(
        reducer=ee.Reducer.percentile([95]),
        geometry=hazard_area, scale=1000, bestEffort=True, tileScale=16, maxPixels=1e13
    )
    rain_p95 = ee.Number(ee.Algorithms.If(
        rain_p95_res.values().size().gt(0),
        rain_p95_res.values().get(0), 100
    ))

    rain_risk  = rain_evt.divide(rain_p95).clamp(0, 1).clip(hazard_area).rename('RainRisk')

    # Re-derive flood from SAR for the event factor (simple 1.25 dB threshold)
    s1_base = (ee.ImageCollection('COPERNICUS/S1_GRD')
               .filterBounds(hazard_area)
               .filter(ee.Filter.eq('instrumentMode', 'IW'))
               .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')))

    def _lee(img, size=5):
        b  = img.bandNames().get(0)
        mean = img.focal_mean(size, 'square', 'pixels')
        var_ = img.subtract(mean).pow(2).focal_mean(size, 'square', 'pixels')
        noise_var = mean.pow(2).multiply(0.25)
        w = var_.subtract(noise_var).max(0).divide(var_.max(1e-9))
        return mean.add(w.multiply(img.subtract(mean))).rename([b])

    s1_pre  = s1_base.filterDate(dates['preS'],  dates['preE']).sort('system:time_start')
    s1_post = s1_base.filterDate(dates['postS'], dates['postE']).sort('system:time_start')
    pre_f   = _lee(s1_pre.mosaic().select('VV').clip(hazard_area))
    post_f  = _lee(s1_post.mosaic().select('VV').clip(hazard_area))
    sar_diff = pre_f.subtract(post_f).rename('SARdiff')

    perm_water = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').gt(90)
    slope_mask = ee.Terrain.slope(ee.Image('USGS/SRTMGL1_003')).lt(8)
    flood = (sar_diff.gt(1.25)
             .updateMask(perm_water.Not())
             .updateMask(slope_mask)
             .selfMask())

    flood_risk   = flood.unmask(0).toFloat().clip(hazard_area).rename('FloodRisk')
    event_factor = rain_risk.multiply(0.50).add(flood_risk.multiply(0.50)).rename('EventFactor')

    surge_index   = base_coastal_risk.multiply(event_factor).rename('SurgeIndex')
    surge_display = surge_index.unmask(0)

    # ---- 6C: Composite Hazard Index ----
    wpop = (ee.ImageCollection('WorldPop/GP/100m/pop')
            .filter(ee.Filter.eq('country', 'IND')).mosaic().clip(hazard_area))
    lc   = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').clip(hazard_area)

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

    surge_class = surge_index.expression(
        '(b<=0.2)?1:(b<=0.4)?2:(b<=0.6)?3:(b<=0.8)?4:5',
        {'b': surge_index}
    ).rename('SurgeClass')

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

    layers = {}
    for name, (img, vis) in tile_configs.items():
        try:
            mapid = img.getMapId(vis)
            layers[name] = {'tileUrl': mapid['tile_fetcher'].url_format}
        except Exception:
            pass  # skip layers that fail (e.g. no coastal pixels)

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

    # Surge index stats
    surge_stats = surge_index.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True),
        geometry=hazard_area, scale=1000, maxPixels=1e13, tileScale=16, bestEffort=True
    ).getInfo()

    # District-level hazard ranking
    districts = ee.FeatureCollection('FAO/GAUL/2015/level2')
    dist_hazard = hazard_index.reduceRegions(
        collection=districts.filterBounds(hazard_area),
        reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True),
        scale=1000, tileScale=16
    ).filter(ee.Filter.notNull(['mean'])).map(lambda f: f.set({
        'HazardIndex': ee.Number(f.get('mean')),
        'HazardLevel': ee.Algorithms.If(
            ee.Number(f.get('mean')).lt(0.20), 'Very Low',
            ee.Algorithms.If(ee.Number(f.get('mean')).lt(0.40), 'Low',
            ee.Algorithms.If(ee.Number(f.get('mean')).lt(0.60), 'Moderate',
            ee.Algorithms.If(ee.Number(f.get('mean')).lt(0.80), 'High', 'Very High'))))
    }))

    top20 = dist_hazard.sort('HazardIndex', False).limit(20)
    top20_info = top20.select(['ADM2_NAME', 'HazardIndex', 'HazardLevel']).getInfo()

    # State-level hazard
    india_states = ee.FeatureCollection('FAO/GAUL/2015/level1').filter(
        ee.Filter.eq('ADM0_NAME', 'India')
    )
    state_hazard = hazard_index.reduceRegions(
        collection=india_states.filterBounds(hazard_area),
        reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True),
        scale=2000, tileScale=16
    ).filter(ee.Filter.notNull(['mean']))
    state_info = state_hazard.select(['ADM1_NAME', 'mean', 'max']).getInfo()

    def _feat_list(fc_info, name_key, fields):
        return [
            {k: f['properties'].get(k) for k in [name_key] + fields}
            for f in fc_info['features']
        ]

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
            'mean': round(surge_stats.get('SurgeIndex_mean', 0) or 0, 4),
            'max':  round(surge_stats.get('SurgeIndex_max',  0) or 0, 4),
        },
        'districtHazard': [
            {
                'name':  f['properties'].get('ADM2_NAME', '?'),
                'index': round(f['properties'].get('HazardIndex', 0) or 0, 3),
                'level': f['properties'].get('HazardLevel', '?'),
            }
            for f in top20_info['features']
        ],
        'stateHazard': [
            {
                'name': f['properties'].get('ADM1_NAME', '?'),
                'mean': round(f['properties'].get('mean', 0) or 0, 3),
                'max':  round(f['properties'].get('max',  0) or 0, 3),
            }
            for f in state_info['features']
        ],
    }

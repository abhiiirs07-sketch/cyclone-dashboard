"""
Module 10: MULTI-HAZARD SUMMARY
Final composite risk index combining:
  - M5  SAR flood extent         (weight 0.30)
  - M6  Storm surge / hazard     (weight 0.25)
  - M7  Vegetation damage NDVI   (weight 0.15)
  - M8  LULC sensitivity         (weight 0.10)
  - M9  Population vulnerability (weight 0.20)

Fast → get_multihazard_layers()   ~15 s  (tile URLs)
Slow → get_multihazard_stats()    ~5 min (district risk table + overall summary)
"""

import ee
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES, CYCLONE_GEE_LOOKUP


# ── Weights for composite index ────────────────────────────────────────────
W_FLOOD  = 0.30
W_HAZARD = 0.25
W_VEG    = 0.15
W_LULC   = 0.10
W_POP    = 0.20

RISK_LEVELS = ['Very Low', 'Low', 'Moderate', 'High', 'Very High']


def _build_multihazard(cyclone_name: str) -> dict:
    cyclone = CYCLONE_DB[cyclone_name]
    dates   = CYCLONE_DATES[cyclone_name]

    landfall  = ee.Geometry.Point([cyclone['lon'], cyclone['lat']])
    countries = ee.FeatureCollection('FAO/GAUL/2015/level0')
    india     = countries.filter(ee.Filter.eq('ADM0_NAME', 'India'))
    buf250    = landfall.buffer(250_000).intersection(india.geometry().simplify(2500), ee.ErrorMargin(100))

    # Reuse optimized, orbit-matched flood mask from Module 5
    from app.modules.module5_flood import _build_sar_fast
    sar = _build_sar_fast(cyclone_name)
    flood_binary = sar['flood']
    # Smooth flood risk 0-1 using distance transform
    flood_risk = flood_binary.unmask(0).focal_mean(3, 'circle', 'pixels').rename('floodRisk')

    # ── Component 2: Hazard index (surge + pop + LC, from M6) ─────────────
    coast_dist = (ee.Image().paint(
        ee.FeatureCollection('USDOS/LSIB_SIMPLE/2017'), 0
    ).fastDistanceTransform().sqrt()
     .multiply(ee.Image.pixelArea().sqrt())
     .divide(1000).rename('coastDist').clip(buf250))

    base_coastal = coast_dist.subtract(5).divide(250).clamp(0, 1).multiply(-1).add(1)
    evt_rain     = (ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
                    .filterDate(dates['evtS'], dates['evtE'])
                    .filterBounds(buf250).sum().clip(buf250))
    if cyclone_name in CYCLONE_GEE_LOOKUP:
        rain_max = ee.Number(CYCLONE_GEE_LOOKUP[cyclone_name]['rain_max'])
    else:
        rain_max = ee.Number(evt_rain.reduceRegion(
            reducer=ee.Reducer.max(), geometry=buf250, scale=5000, maxPixels=1e9, bestEffort=True
        ).values().get(0))
    rain_risk    = evt_rain.divide(rain_max).rename('rainRisk')
    event_factor = rain_risk.multiply(0.6).add(base_coastal.multiply(0.4))
    surge_idx    = base_coastal.multiply(event_factor).pow(0.5)

    pop_density  = (ee.ImageCollection('CIESIN/GPWv411/GPW_Population_Density')
                    .filterDate('2020-01-01', '2020-12-31').first()
                    .select('population_density').clip(buf250))
    pop_norm     = pop_density.divide(5000).clamp(0, 1)

    lc           = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').clip(buf250)
    lc_risk      = lc.remap(
        [10,  20,  30,  40,  50,  60,  70,  80,  90,  95,  100],
        [85,  60,  55,  80,  95,  15,  5,   30,  70,  90,  10]
    ).divide(100).rename('lcRisk')

    hazard_idx = surge_idx.multiply(0.55).add(pop_norm.multiply(0.25)).add(lc_risk.multiply(0.20))

    # Reuse optimized vegetation damage mask and dNDVI from Module 7
    from app.modules.module7_vegetation import _build_veg
    veg = _build_veg(cyclone_name)
    d_ndvi = veg['d_ndvi']
    # Normalise: clamp -0.5 to 0, then flip so 0=no damage, 1=total loss
    veg_risk  = d_ndvi.clamp(-0.5, 0).multiply(-2).rename('vegRisk')

    # ── Component 4: LULC sensitivity (already 0-1) ────────────────────────
    lulc_risk = lc_risk.rename('lulcRisk')   # reuse from M6

    # ── Component 5: Population vulnerability (pop_norm already 0-1) ───────
    pop_risk = pop_norm.rename('popRisk')

    # ── Composite multi-hazard index ───────────────────────────────────────
    mh_index = (flood_risk.multiply(W_FLOOD)
                .add(hazard_idx.multiply(W_HAZARD))
                .add(veg_risk.multiply(W_VEG))
                .add(lulc_risk.multiply(W_LULC))
                .add(pop_risk.multiply(W_POP))
                .clamp(0, 1)
                .rename('MultiHazard'))

    # Classify into 5 levels using percentile breaks
    mh_class = (mh_index
                .where(mh_index.lte(0.20), 1)
                .where(mh_index.gt(0.20).And(mh_index.lte(0.40)), 2)
                .where(mh_index.gt(0.40).And(mh_index.lte(0.60)), 3)
                .where(mh_index.gt(0.60).And(mh_index.lte(0.80)), 4)
                .where(mh_index.gt(0.80), 5)
                .rename('MHClass'))

    return {
        'buf250':      buf250,
        'flood_risk':  flood_risk,
        'hazard_idx':  hazard_idx,
        'veg_risk':    veg_risk,
        'lulc_risk':   lulc_risk,
        'pop_risk':    pop_risk,
        'mh_index':    mh_index,
        'mh_class':    mh_class,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FAST: tile URLs ~15 s
# ─────────────────────────────────────────────────────────────────────────────

def get_multihazard_layers(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_multihazard(cyclone_name)

    tile_configs = {
        'mhIndex':    (t['mh_index'].updateMask(t['mh_index'].gt(0.05)),   {'min': 0, 'max': 1, 'palette': '006400,78C679,FFFF00,FD8D3C,BD0026,67000D'}),
        'mhClass':    (t['mh_class'].selfMask(), {'min': 1, 'max': 5, 'palette': '006400,78C679,FFFF00,FD8D3C,BD0026'}),
        'floodRisk':  (t['flood_risk'].updateMask(t['flood_risk'].gt(0.01)), {'min': 0, 'max': 1, 'palette': 'C6DBEF,6BAED6,2171B5,084594,042F6B'}),
        'vegRisk':    (t['veg_risk'].updateMask(t['veg_risk'].gt(0.01)),   {'min': 0, 'max': 1, 'palette': 'D9F0D3,78C679,1A6600,00441B,002200'}),
        'popRisk':    (t['pop_risk'].updateMask(t['pop_risk'].gt(0.01)),   {'min': 0, 'max': 1, 'palette': 'FFEDA0,FEB24C,FC4E2A,BD0026,67000D'}),
    }

    def _get_tile(name_img_vis):
        name, (img, vis) = name_img_vis
        try:
            mapid = img.getMapId(vis)
            return name, {'tileUrl': mapid['tile_fetcher'].url_format}
        except Exception as e:
            print(f'[M10] {name} getMapId failed: {e}')
            return name, None

    layers = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(_get_tile, item): item[0] for item in tile_configs.items()}
        for future in as_completed(futures):
            name, result = future.result()
            if result is not None:
                layers[name] = result

    return {'layers': layers}


# ─────────────────────────────────────────────────────────────────────────────
# SLOW: statistics ~5 min
# ─────────────────────────────────────────────────────────────────────────────

def get_multihazard_stats(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t      = _build_multihazard(cyclone_name)
    buf250 = t['buf250']

    cyclone   = CYCLONE_DB[cyclone_name]
    landfall  = ee.Geometry.Point([cyclone['lon'], cyclone['lat']])

    # District multi-hazard ranking
    districts = (ee.FeatureCollection('FAO/GAUL/2015/level2')
                 .filter(ee.Filter.eq('ADM0_NAME', 'India'))
                 .filterBounds(landfall.buffer(150_000)))
    mh_band   = t['mh_index'].rename('mean')
    dist_mh   = mh_band.reduceRegions(
        collection=districts,
        reducer=ee.Reducer.mean(),
        scale=5000, tileScale=16
    ).filter(ee.Filter.notNull(['mean']))

    top20_list = dist_mh.sort('mean', False).limit(20).select(['ADM2_NAME', 'mean'], retainGeometry=False).toList(20)

    # Group all calculations into a single dictionary
    stats_dict = ee.Dictionary({
        'idx_stats': t['mh_index'].reduceRegion(
            reducer=(ee.Reducer.mean()
                     .combine(ee.Reducer.min(), sharedInputs=True)
                     .combine(ee.Reducer.max(), sharedInputs=True)
                     .combine(ee.Reducer.stdDev(), sharedInputs=True)),
            geometry=buf250, scale=5000, maxPixels=1e13, tileScale=16, bestEffort=True
        ),
        'class_groups': ee.Image.pixelArea().addBands(t['mh_class']).reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName='class'),
            geometry=buf250, scale=5000, maxPixels=1e13, tileScale=16, bestEffort=True
        ).get('groups'),
        'top20': top20_list
    })

    results = stats_dict.getInfo()
    idx_stats = results.get('idx_stats', {})
    class_groups = results.get('class_groups') or []
    top20_feats = results.get('top20') or []

    class_areas = {}
    for g in (class_groups or []):
        cls = int(g.get('class', 0))
        if 1 <= cls <= 5:
            class_areas[RISK_LEVELS[cls - 1]] = round(g.get('sum', 0) / 1e6, 1)

    def _risk_level(score: float) -> str:
        if score >= 0.80: return 'Very High'
        if score >= 0.60: return 'High'
        if score >= 0.40: return 'Moderate'
        if score >= 0.20: return 'Low'
        return 'Very Low'

    district_ranking = [
        {
            'name':  f.get('properties', {}).get('ADM2_NAME', '?'),
            'score': round(f.get('properties', {}).get('mean', 0) or 0, 3),
            'level': _risk_level(f.get('properties', {}).get('mean', 0) or 0),
            'rank':  i + 1,
        }
        for i, f in enumerate(top20_feats)
        if isinstance(f, dict) and 'properties' in f
    ]

    return {
        'index': {
            'mean':   round(idx_stats.get('MultiHazard_mean',   0) or 0, 3),
            'min':    round(idx_stats.get('MultiHazard_min',    0) or 0, 3),
            'max':    round(idx_stats.get('MultiHazard_max',    0) or 0, 3),
            'stddev': round(idx_stats.get('MultiHazard_stdDev', 0) or 0, 3),
        },
        'class_areas':       class_areas,   # {level: km2}
        'district_ranking':  district_ranking,
        'weights': {
            'flood':   W_FLOOD,
            'hazard':  W_HAZARD,
            'veg':     W_VEG,
            'lulc':    W_LULC,
            'pop':     W_POP,
        },
    }

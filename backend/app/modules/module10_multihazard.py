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
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES


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
    buf250    = landfall.buffer(250_000).intersection(india.geometry(), ee.ErrorMargin(100))

    # ── Component 1: Flood risk (SAR-derived binary mask → 0/1) ────────────
    s1 = (ee.ImageCollection('COPERNICUS/S1_GRD')
          .filterBounds(buf250)
          .filter(ee.Filter.eq('instrumentMode', 'IW'))
          .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')))

    def _lee(img, size=5):
        b    = img.bandNames().get(0)
        m    = img.focal_mean(size, 'square', 'pixels')
        v    = img.subtract(m).pow(2).focal_mean(size, 'square', 'pixels')
        nv   = m.pow(2).multiply(0.25)
        w    = v.subtract(nv).max(0).divide(v.max(1e-9))
        return m.add(w.multiply(img.subtract(m))).rename([b])

    pre_vv  = _lee(s1.filterDate(dates['preS'],  dates['preE']).mosaic().select('VV').clip(buf250))
    post_vv = _lee(s1.filterDate(dates['postS'], dates['postE']).mosaic().select('VV').clip(buf250))
    sar_diff = pre_vv.subtract(post_vv)

    perm_water = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').gt(90)
    slope_mask = ee.Terrain.slope(ee.Image('USGS/SRTMGL1_003')).lt(8)
    flood_binary = (sar_diff.gt(1.25)
                    .updateMask(perm_water.Not())
                    .updateMask(slope_mask))
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
    rain_max     = ee.Number(evt_rain.reduceRegion(
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

    # ── Component 3: Vegetation damage (dNDVI normalised -0.5→0 = 0→1) ────
    evt_s = ee.Date(dates['evtS'])
    evt_e = ee.Date(dates['evtE'])
    # Fast cloud-masked Sentinel-2 using QA60 and low cloud cover threshold
    s2_col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
              .filterBounds(buf250)
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)))

    def _mask_s2(img):
        qa = img.select('QA60')
        cloud_bit_mask = 1 << 10
        cirrus_bit_mask = 1 << 11
        mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
        return img.updateMask(mask).divide(10000).copyProperties(img, ['system:time_start'])

    s2 = s2_col.map(_mask_s2)

    pre_ndvi  = s2.filterDate(evt_s.advance(-30,'day'), evt_s.advance(-1,'day')).median().clip(buf250).normalizedDifference(['B8','B4'])
    post_ndvi = s2.filterDate(evt_e.advance(1,'day'),  evt_e.advance(30,'day')).median().clip(buf250).normalizedDifference(['B8','B4'])
    d_ndvi    = post_ndvi.subtract(pre_ndvi)
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
        'mhIndex':    (t['mh_index'],   {'min': 0, 'max': 1, 'palette': '006400,78C679,FFFF00,FD8D3C,BD0026,67000D'}),
        'mhClass':    (t['mh_class'].selfMask(), {'min': 1, 'max': 5, 'palette': '006400,78C679,FFFF00,FD8D3C,BD0026'}),
        'floodRisk':  (t['flood_risk'], {'min': 0, 'max': 1, 'palette': 'FFFFFF,C6DBEF,6BAED6,2171B5,084594'}),
        'vegRisk':    (t['veg_risk'],   {'min': 0, 'max': 1, 'palette': 'FFFFFF,D9F0D3,78C679,1A6600,00441B'}),
        'popRisk':    (t['pop_risk'],   {'min': 0, 'max': 1, 'palette': 'FFFFFF,FFEDA0,FEB24C,FC4E2A,BD0026'}),
    }

    layers = {}
    for name, (img, vis) in tile_configs.items():
        try:
            mapid = img.getMapId(vis)
            layers[name] = {'tileUrl': mapid['tile_fetcher'].url_format}
        except Exception:
            pass

    return {'layers': layers}


# ─────────────────────────────────────────────────────────────────────────────
# SLOW: statistics ~5 min
# ─────────────────────────────────────────────────────────────────────────────

def get_multihazard_stats(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t      = _build_multihazard(cyclone_name)
    buf250 = t['buf250']

    # District multi-hazard ranking
    districts = ee.FeatureCollection('FAO/GAUL/2015/level2')
    dist_mh = t['mh_index'].reduceRegions(
        collection=districts.filterBounds(buf250),
        reducer=ee.Reducer.mean(),
        scale=1000, tileScale=16
    ).filter(ee.Filter.notNull(['mean']))

    top20 = dist_mh.sort('mean', False).limit(20).select(['ADM2_NAME', 'mean'])

    # Group all calculations into a single dictionary
    stats_dict = ee.Dictionary({
        'idx_stats': t['mh_index'].reduceRegion(
            reducer=(ee.Reducer.mean()
                     .combine(ee.Reducer.min(), sharedInputs=True)
                     .combine(ee.Reducer.max(), sharedInputs=True)
                     .combine(ee.Reducer.stdDev(), sharedInputs=True)),
            geometry=buf250, scale=1000, maxPixels=1e13, tileScale=16, bestEffort=True
        ),
        'class_groups': ee.Image.pixelArea().addBands(t['mh_class']).reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName='class'),
            geometry=buf250, scale=1000, maxPixels=1e13, tileScale=16, bestEffort=True
        ).get('groups'),
        'top20': top20
    })

    results = stats_dict.getInfo()
    idx_stats = results.get('idx_stats', {})
    class_groups = results.get('class_groups') or []
    top20_info = results.get('top20', {})

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
            'name':  f['properties'].get('ADM2_NAME', '?'),
            'score': round(f['properties'].get('mean', 0) or 0, 3),
            'level': _risk_level(f['properties'].get('mean', 0) or 0),
            'rank':  i + 1,
        }
        for i, f in enumerate(top20_info.get('features', []))
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

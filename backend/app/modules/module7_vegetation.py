"""
Module 7: VEGETATION DAMAGE ASSESSMENT (Sentinel-2 NDVI/NBR)

Fast → get_veg_layers()   — tile URLs only (~15 s)
Slow → get_veg_stats()    — damage class areas + district table (~3-4 min)
"""

import ee
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES


def _add_indices(img: ee.Image) -> ee.Image:
    return (img
            .addBands(img.normalizedDifference(['B8', 'B4']).rename('NDVI'))
            .addBands(img.normalizedDifference(['B3', 'B8']).rename('NDWI'))
            .addBands(img.normalizedDifference(['B8', 'B12']).rename('NBR')))


def _build_veg(cyclone_name: str) -> dict:
    cyclone = CYCLONE_DB[cyclone_name]
    dates   = CYCLONE_DATES[cyclone_name]

    landfall  = ee.Geometry.Point([cyclone['lon'], cyclone['lat']])
    countries = ee.FeatureCollection('FAO/GAUL/2015/level0')
    india     = countries.filter(ee.Filter.eq('ADM0_NAME', 'India'))
    buf250    = landfall.buffer(250_000).intersection(india.geometry(), ee.ErrorMargin(100))

    # 30-day pre/post windows around event
    evt_s = ee.Date(dates['evtS'])
    evt_e = ee.Date(dates['evtE'])
    pre_start  = evt_s.advance(-30, 'day')
    pre_end    = evt_s.advance(-1,  'day')
    post_start = evt_e.advance(1,   'day')
    post_end   = evt_e.advance(30,  'day')

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

    pre_s2  = _add_indices(s2.filterDate(pre_start,  pre_end).median().clip(buf250))
    post_s2 = _add_indices(s2.filterDate(post_start, post_end).median().clip(buf250))

    pre_ndvi  = pre_s2.select('NDVI')
    post_ndvi = post_s2.select('NDVI')
    pre_nbr   = pre_s2.select('NBR')
    post_nbr  = post_s2.select('NBR')

    d_ndvi = post_ndvi.subtract(pre_ndvi).rename('dNDVI')
    d_nbr  = post_nbr.subtract(pre_nbr).rename('dNBR')

    # Damage classification
    # 1=Forest damage, 2=Crop damage, 3=Severe, 4=General, 0=No damage
    damage_class = d_ndvi.expression(
        '(pre>0.6 && d<-0.2)?1:(pre>=0.35 && pre<=0.6 && d<-0.2)?2:(d<-0.4)?3:(d<-0.2)?4:0',
        {'pre': pre_ndvi, 'd': d_ndvi}
    ).rename('DamageClass')

    veg_damage = damage_class.gt(0).selfMask()

    return {
        'buf250':       buf250,
        'pre_ndvi':     pre_ndvi,
        'post_ndvi':    post_ndvi,
        'd_ndvi':       d_ndvi,
        'd_nbr':        d_nbr,
        'damage_class': damage_class,
        'veg_damage':   veg_damage,
    }


# ---------------------------------------------------------------------------
# FAST: tile URLs ~15 s
# ---------------------------------------------------------------------------

def get_veg_layers(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_veg(cyclone_name)

    tile_configs = {
        'preNDVI':      (t['pre_ndvi'],     {'min': -0.1, 'max': 0.8, 'palette': 'FFFFFF,FFFF00,92D050,1A6600'}),
        'postNDVI':     (t['post_ndvi'],    {'min': -0.1, 'max': 0.8, 'palette': 'FFFFFF,FFFF00,92D050,1A6600'}),
        'dNDVI':        (t['d_ndvi'],       {'min': -0.5, 'max': 0.2, 'palette': 'FF0000,FFA500,FFFF00,FFFFFF,A8D5A2'}),
        'dNBR':         (t['d_nbr'],        {'min': -0.5, 'max': 0.3, 'palette': 'FF0000,FFA500,FFFF00,FFFFFF,92D050'}),
        'damageClass':  (t['damage_class'].selfMask(), {'min': 1, 'max': 4, 'palette': '00441B,78C679,FD8D3C,BD0026'}),
    }

    layers = {}
    for name, (img, vis) in tile_configs.items():
        try:
            mapid = img.getMapId(vis)
            layers[name] = {'tileUrl': mapid['tile_fetcher'].url_format}
        except Exception:
            pass

    return {'layers': layers}


# ---------------------------------------------------------------------------
# SLOW: statistics ~3-4 min
# ---------------------------------------------------------------------------

def get_veg_stats(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_veg(cyclone_name)
    buf250       = t['buf250']
    damage_class = t['damage_class']
    d_ndvi       = t['d_ndvi']

    # Total damage area
    total_dm = (ee.Image.pixelArea().divide(1e6).updateMask(t['veg_damage'])
                .reduceRegion(reducer=ee.Reducer.sum(), geometry=buf250,
                              scale=100, maxPixels=1e13, tileScale=16, bestEffort=True))
    total_val = total_dm.values().get(0)
    total_km2 = ee.Number(ee.Algorithms.If(total_val, total_val, 0)).getInfo()

    # Per-class areas using grouped reducer
    groups_raw = (ee.Image.pixelArea().addBands(damage_class)
                  .reduceRegion(
                      reducer=ee.Reducer.sum().group(groupField=1, groupName='class'),
                      geometry=buf250, scale=2000, maxPixels=1e13, tileScale=16, bestEffort=True
                  ).get('groups').getInfo())

    class_labels = {1: 'Forest Damage', 2: 'Crop Damage', 3: 'Severe Damage', 4: 'General Damage'}
    class_areas = {}
    for g in (groups_raw or []):
        cls = int(g.get('class', 0))
        if cls in class_labels:
            class_areas[class_labels[cls]] = round(g.get('sum', 0) / 1e6, 1)

    # dNDVI stats
    ndvi_stats = d_ndvi.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.min(), sharedInputs=True)
                         .combine(ee.Reducer.max(), sharedInputs=True),
        geometry=buf250, scale=1000, maxPixels=1e13, tileScale=16, bestEffort=True
    ).getInfo()

    # District-level damage
    districts = ee.FeatureCollection('FAO/GAUL/2015/level2')
    dist_dmg = d_ndvi.clip(buf250).reduceRegions(
        collection=districts.filterBounds(buf250),
        reducer=ee.Reducer.mean().combine(ee.Reducer.min(), sharedInputs=True),
        scale=1000
    ).filter(ee.Filter.notNull(['mean']))

    top15 = dist_dmg.sort('mean').limit(15)   # lowest (most negative) dNDVI = worst damage
    top15_info = top15.select(['ADM2_NAME', 'mean', 'min']).getInfo()

    districts_list = [
        {
            'name':      f['properties'].get('ADM2_NAME', '?'),
            'mean_dndvi': round(f['properties'].get('mean', 0) or 0, 3),
            'min_dndvi':  round(f['properties'].get('min',  0) or 0, 3),
        }
        for f in top15_info['features']
    ]

    return {
        'stats': {
            'total_damage_km2': round(total_km2, 1),
            'dndvi_mean': round(ndvi_stats.get('dNDVI_mean', 0) or 0, 3),
            'dndvi_min':  round(ndvi_stats.get('dNDVI_min',  0) or 0, 3),
            'dndvi_max':  round(ndvi_stats.get('dNDVI_max',  0) or 0, 3),
            **class_areas,
        },
        'districts': districts_list,
    }

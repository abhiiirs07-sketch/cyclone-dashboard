"""
Module 8: LULC IMPACT ASSESSMENT (ESA WorldCover v2 + cross-module analysis)

Fast → get_lulc_layers()   — tile URLs only (~15 s)
Slow → get_lulc_stats()    — per-class impact areas + district composition (~4-5 min)
"""

import ee
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES


# ESA WorldCover v2 class definitions
LULC_CLASSES = {
    10:  ('Tree cover',         '#006400'),
    20:  ('Shrubland',          '#FFBB22'),
    30:  ('Grassland',          '#FFFF4C'),
    40:  ('Cropland',           '#F096FF'),
    50:  ('Built-up',           '#FA0000'),
    60:  ('Bare/sparse veg',    '#B4B4B4'),
    70:  ('Snow & ice',         '#F0F0F0'),
    80:  ('Permanent water',    '#0064C8'),
    90:  ('Herbaceous wetland', '#0096A0'),
    95:  ('Mangroves',          '#00CF75'),
    100: ('Moss & lichen',      '#FAE6A0'),
}


def _build_lulc(cyclone_name: str) -> dict:
    cyclone = CYCLONE_DB[cyclone_name]
    dates   = CYCLONE_DATES[cyclone_name]

    landfall  = ee.Geometry.Point([cyclone['lon'], cyclone['lat']])
    countries = ee.FeatureCollection('FAO/GAUL/2015/level0')
    india     = countries.filter(ee.Filter.eq('ADM0_NAME', 'India'))
    buf250    = landfall.buffer(250_000).intersection(india.geometry(), ee.ErrorMargin(100))

    # ESA WorldCover v2 land cover
    lc = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').clip(buf250)

    # Re-derive flood mask (SAR Sentinel-1)
    s1 = (ee.ImageCollection('COPERNICUS/S1_GRD')
          .filterBounds(buf250)
          .filter(ee.Filter.eq('instrumentMode', 'IW'))
          .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')))

    def _lee(img, size=5):
        b  = img.bandNames().get(0)
        mean = img.focal_mean(size, 'square', 'pixels')
        var_ = img.subtract(mean).pow(2).focal_mean(size, 'square', 'pixels')
        noise_var = mean.pow(2).multiply(0.25)
        w = var_.subtract(noise_var).max(0).divide(var_.max(1e-9))
        return mean.add(w.multiply(img.subtract(mean))).rename([b])

    s1_pre  = s1.filterDate(dates['preS'],  dates['preE']).sort('system:time_start')
    s1_post = s1.filterDate(dates['postS'], dates['postE']).sort('system:time_start')
    pre_f   = _lee(s1_pre.mosaic().select('VV').clip(buf250))
    post_f  = _lee(s1_post.mosaic().select('VV').clip(buf250))
    sar_diff = pre_f.subtract(post_f)

    perm_water  = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').gt(90)
    slope_mask  = ee.Terrain.slope(ee.Image('USGS/SRTMGL1_003')).lt(8)
    flood_mask  = (sar_diff.gt(1.25)
                   .updateMask(perm_water.Not())
                   .updateMask(slope_mask)
                   .selfMask())

    # Re-derive vegetation damage mask (dNDVI < -0.2)
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

    def _ndvi(img): return img.normalizedDifference(['B8', 'B4']).rename('NDVI')

    pre_ndvi  = _ndvi(s2.filterDate(evt_s.advance(-30,'day'), evt_s.advance(-1,'day')).median().clip(buf250))
    post_ndvi = _ndvi(s2.filterDate(evt_e.advance(1,'day'),  evt_e.advance(30,'day')).median().clip(buf250))
    d_ndvi    = post_ndvi.subtract(pre_ndvi).rename('dNDVI')
    veg_damage_mask = d_ndvi.lt(-0.2).selfMask()

    # Composite impact layer: 0=unaffected, 1=flood-only, 2=veg-damage-only, 3=both
    flood_bin  = flood_mask.unmask(0).multiply(1)
    veg_bin    = veg_damage_mask.unmask(0).multiply(2)
    impact_img = flood_bin.add(veg_bin).rename('ImpactType')

    # LULC change risk score per class (based on sensitivity to cyclone impacts)
    lulc_impact_score = lc.remap(
        [10,   20,   30,   40,   50,   60,   70,   80,   90,   95,   100],
        [0.85, 0.60, 0.55, 0.80, 0.95, 0.15, 0.05, 0.30, 0.70, 0.90, 0.10]
    ).rename('LULCImpactScore')

    return {
        'buf250':            buf250,
        'lc':                lc,
        'flood_mask':        flood_mask,
        'veg_damage_mask':   veg_damage_mask,
        'impact_img':        impact_img,
        'lulc_impact_score': lulc_impact_score,
        'd_ndvi':            d_ndvi,
    }


# ---------------------------------------------------------------------------
# FAST: tile URLs ~15 s
# ---------------------------------------------------------------------------

def get_lulc_layers(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_lulc(cyclone_name)

    # ESA WorldCover colour palette in class order (10,20,...,100)
    ESA_PALETTE = '006400,FFBB22,FFFF4C,F096FF,FA0000,B4B4B4,F0F0F0,0064C8,0096A0,00CF75,FAE6A0'

    tile_configs = {
        'landCover':       (t['lc'],                 {'min': 10, 'max': 100, 'palette': ESA_PALETTE}),
        'lulcImpactScore': (t['lulc_impact_score'],  {'min': 0,  'max': 1,   'palette': '006400,FFFF00,FF8C00,FF0000'}),
        'impactType':      (t['impact_img'].selfMask(),{'min': 1, 'max': 3,   'palette': '0066FF,22C55E,FF4500'}),
        'floodedLULC':     (t['lc'].updateMask(t['flood_mask']),
                            {'min': 10, 'max': 100, 'palette': ESA_PALETTE}),
        'damagedLULC':     (t['lc'].updateMask(t['veg_damage_mask']),
                            {'min': 10, 'max': 100, 'palette': ESA_PALETTE}),
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
# SLOW: statistics ~4-5 min
# ---------------------------------------------------------------------------

def get_lulc_stats(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t  = _build_lulc(cyclone_name)
    buf250 = t['buf250']
    lc     = t['lc']

    # Group computations into one dictionary to do a single round-trip
    stats_dict = ee.Dictionary({
        'total_area': ee.Image.pixelArea().divide(1e6).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=buf250, scale=1000, maxPixels=1e13, tileScale=16, bestEffort=True
        ).values().get(0),
        'lc_area_groups': ee.Image.pixelArea().addBands(lc).reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName='class'),
            geometry=buf250, scale=1000, maxPixels=1e13, tileScale=16, bestEffort=True
        ).get('groups'),
        'flood_area_groups': ee.Image.pixelArea().updateMask(t['flood_mask']).addBands(lc).reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName='class'),
            geometry=buf250, scale=1000, maxPixels=1e13, tileScale=16, bestEffort=True
        ).get('groups'),
        'veg_area_groups': ee.Image.pixelArea().updateMask(t['veg_damage_mask']).addBands(lc).reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName='class'),
            geometry=buf250, scale=1000, maxPixels=1e13, tileScale=16, bestEffort=True
        ).get('groups')
    })

    results = stats_dict.getInfo()
    total_area = results.get('total_area', 0) or 0
    lc_area_groups = results.get('lc_area_groups') or []
    flood_area_groups = results.get('flood_area_groups') or []
    veg_area_groups = results.get('veg_area_groups') or []

    def _groups_to_dict(groups):
        return {int(g['class']): round(g['sum'] / 1e6, 1) for g in (groups or [])}

    lc_areas    = _groups_to_dict(lc_area_groups)
    flood_areas = _groups_to_dict(flood_area_groups)
    veg_areas   = _groups_to_dict(veg_area_groups)

    # Build per-class table
    class_table = []
    for cls_id, (cls_name, cls_color) in LULC_CLASSES.items():
        total  = lc_areas.get(cls_id, 0)
        flooded = flood_areas.get(cls_id, 0)
        damaged = veg_areas.get(cls_id, 0)
        if total > 0:
            class_table.append({
                'class_id':   cls_id,
                'name':       cls_name,
                'color':      cls_color,
                'total_km2':  total,
                'flood_km2':  flooded,
                'veg_km2':    damaged,
                'pct_flood':  round(flooded / total * 100, 1) if total > 0 else 0,
                'pct_veg':    round(damaged / total * 100, 1) if total > 0 else 0,
            })

    # Sort by combined impact (flood + veg damage)
    class_table.sort(key=lambda x: x['flood_km2'] + x['veg_km2'], reverse=True)

    # District LULC impact summary
    districts = ee.FeatureCollection('FAO/GAUL/2015/level2')
    dist_score = t['lulc_impact_score'].reduceRegions(
        collection=districts.filterBounds(buf250),
        reducer=ee.Reducer.mean(),
        scale=500, tileScale=16
    ).filter(ee.Filter.notNull(['mean']))
    dist_info = dist_score.sort('mean', False).limit(15).select(['ADM2_NAME', 'mean']).getInfo()

    return {
        'summary': {
            'total_area_km2':     round(total_area, 0),
            'total_flooded_km2':  round(sum(flood_areas.values()), 1),
            'total_damaged_km2':  round(sum(veg_areas.values()), 1),
        },
        'classes':   class_table,
        'districts': [
            {
                'name':  f['properties'].get('ADM2_NAME', '?'),
                'score': round(f['properties'].get('mean', 0) or 0, 3),
            }
            for f in dist_info['features']
        ],
    }

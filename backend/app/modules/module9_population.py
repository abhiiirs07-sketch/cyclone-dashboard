"""
Module 9: POPULATION EXPOSURE ASSESSMENT
Uses GPW v4.11 population count + WorldPop density
Crossed with: flood extent (M5), hazard class (M6), veg damage (M7)

Fast → get_pop_layers()   — tile URLs ~15 s
Slow → get_pop_stats()    — exposed population counts + district table ~4-5 min
"""

import ee
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES


def _build_pop(cyclone_name: str) -> dict:
    cyclone = CYCLONE_DB[cyclone_name]
    dates   = CYCLONE_DATES[cyclone_name]

    landfall  = ee.Geometry.Point([cyclone['lon'], cyclone['lat']])
    countries = ee.FeatureCollection('FAO/GAUL/2015/level0')
    india     = countries.filter(ee.Filter.eq('ADM0_NAME', 'India'))
    buf250    = landfall.buffer(250_000).intersection(india.geometry(), ee.ErrorMargin(100))

    # -----------------------------------------------------------------
    # Population data (GPW v4.11 — ~1 km resolution)
    # -----------------------------------------------------------------
    gpw_year = 2020
    pop_count   = (ee.ImageCollection('CIESIN/GPWv411/GPW_Population_Count')
                   .filterDate(f'{gpw_year}-01-01', f'{gpw_year}-12-31')
                   .first()
                   .select('population_count')
                   .clip(buf250))

    pop_density = (ee.ImageCollection('CIESIN/GPWv411/GPW_Population_Density')
                   .filterDate(f'{gpw_year}-01-01', f'{gpw_year}-12-31')
                   .first()
                   .select('population_density')
                   .clip(buf250))

    # -----------------------------------------------------------------
    # Flood mask (re-derived from Sentinel-1 SAR, same as M5)
    # -----------------------------------------------------------------
    s1 = (ee.ImageCollection('COPERNICUS/S1_GRD')
          .filterBounds(buf250)
          .filter(ee.Filter.eq('instrumentMode', 'IW'))
          .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')))

    def _lee(img, size=5):
        b    = img.bandNames().get(0)
        mean = img.focal_mean(size, 'square', 'pixels')
        var_ = img.subtract(mean).pow(2).focal_mean(size, 'square', 'pixels')
        nvar = mean.pow(2).multiply(0.25)
        w    = var_.subtract(nvar).max(0).divide(var_.max(1e-9))
        return mean.add(w.multiply(img.subtract(mean))).rename([b])

    pre_vv  = _lee(s1.filterDate(dates['preS'],  dates['preE']).mosaic().select('VV').clip(buf250))
    post_vv = _lee(s1.filterDate(dates['postS'], dates['postE']).mosaic().select('VV').clip(buf250))
    sar_diff = pre_vv.subtract(post_vv)

    perm_water = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').gt(90)
    slope_mask = ee.Terrain.slope(ee.Image('USGS/SRTMGL1_003')).lt(8)
    flood_mask = (sar_diff.gt(1.25)
                  .updateMask(perm_water.Not())
                  .updateMask(slope_mask)
                  .selfMask())

    # -----------------------------------------------------------------
    # Hazard index (re-derived, composite from M6)
    # -----------------------------------------------------------------
    coast_dist  = (ee.Image().paint(
        ee.FeatureCollection('USDOS/LSIB_SIMPLE/2017'), 0
    ).fastDistanceTransform().sqrt()
     .multiply(ee.Image.pixelArea().sqrt())
     .divide(1000).rename('coastDist').clip(buf250))

    base_coastal = coast_dist.subtract(5).divide(250).clamp(0, 1).multiply(-1).add(1)
    evt_rain     = (ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
                    .filterDate(dates['evtS'], dates['evtE'])
                    .filterBounds(buf250)
                    .sum().clip(buf250))
    rain_max     = ee.Number(evt_rain.reduceRegion(
        reducer=ee.Reducer.max(), geometry=buf250, scale=5000, maxPixels=1e9, bestEffort=True
    ).values().get(0))
    rain_risk    = evt_rain.divide(rain_max).rename('rainRisk')
    event_factor = rain_risk.multiply(0.6).add(base_coastal.multiply(0.4))
    surge_index  = base_coastal.multiply(event_factor).pow(0.5)

    pop_norm     = pop_density.divide(5000).clamp(0, 1)
    hazard_index = surge_index.multiply(0.55).add(pop_norm.multiply(0.25)).add(rain_risk.multiply(0.20))

    # -----------------------------------------------------------------
    # Vegetation damage mask (dNDVI < -0.2, same as M7)
    # -----------------------------------------------------------------
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

    pre_ndvi  = s2.filterDate(evt_s.advance(-30,'day'), evt_s.advance(-1,'day')).median().clip(buf250).normalizedDifference(['B8','B4']).rename('NDVI')
    post_ndvi = s2.filterDate(evt_e.advance(1,'day'),  evt_e.advance(30,'day')).median().clip(buf250).normalizedDifference(['B8','B4']).rename('NDVI')
    d_ndvi    = post_ndvi.subtract(pre_ndvi).rename('dNDVI')
    veg_mask  = d_ndvi.lt(-0.2).selfMask()

    # -----------------------------------------------------------------
    # Exposure layers
    # -----------------------------------------------------------------
    # Population in flooded areas
    pop_flooded   = pop_count.updateMask(flood_mask)
    # Population in high-hazard zones (top 30% hazard)
    hazard_thresh = hazard_index.gt(0.6)
    pop_high_haz  = pop_count.updateMask(hazard_thresh)
    # Population with vegetation damage
    pop_veg_dmg   = pop_count.updateMask(veg_mask)
    # Composite vulnerability: pop density × hazard
    pop_vuln      = pop_density.multiply(hazard_index).rename('Vulnerability')

    return {
        'buf250':       buf250,
        'pop_count':    pop_count,
        'pop_density':  pop_density,
        'hazard_index': hazard_index,
        'flood_mask':   flood_mask,
        'veg_mask':     veg_mask,
        'pop_flooded':  pop_flooded,
        'pop_high_haz': pop_high_haz,
        'pop_veg_dmg':  pop_veg_dmg,
        'pop_vuln':     pop_vuln,
    }


# ---------------------------------------------------------------------------
# FAST: tile URLs ~15 s
# ---------------------------------------------------------------------------

def get_pop_layers(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_pop(cyclone_name)

    tile_configs = {
        'popCount':    (t['pop_count'],    {'min': 0, 'max': 5000,  'palette': 'FFFFFF,FFEDA0,FEB24C,FC4E2A,BD0026,67000D'}),
        'popDensity':  (t['pop_density'],  {'min': 0, 'max': 2000,  'palette': 'FFFFFF,FFEDA0,FEB24C,FC4E2A,BD0026,67000D'}),
        'popVuln':     (t['pop_vuln'],     {'min': 0, 'max': 1000,  'palette': '006400,FFFF00,FFA500,FF0000,67000D'}),
        'popFlooded':  (t['pop_flooded'],  {'min': 0, 'max': 2000,  'palette': 'C6DBEF,6BAED6,2171B5,084594,042F6B'}),
        'popHighHaz':  (t['pop_high_haz'],{'min': 0, 'max': 2000,  'palette': 'FFF7EC,FDD49E,FC8D59,D7301F,7F0000'}),
        'popVegDmg':   (t['pop_veg_dmg'], {'min': 0, 'max': 2000,  'palette': 'F7FCF5,AED9A8,41AE76,006D2C,00441B'}),
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

def get_pop_stats(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t      = _build_pop(cyclone_name)
    buf250 = t['buf250']

    def _sum_pop(img):
        res = img.reduceRegion(
            reducer=ee.Reducer.sum(), geometry=buf250,
            scale=1000, maxPixels=1e13, tileScale=16, bestEffort=True
        )
        val = res.values().get(0)
        return ee.Number(ee.Algorithms.If(val, val, 0))

    def _max_pop(img):
        res = img.reduceRegion(
            reducer=ee.Reducer.max(), geometry=buf250,
            scale=1000, maxPixels=1e13, tileScale=16, bestEffort=True
        )
        val = res.values().get(0)
        return ee.Number(ee.Algorithms.If(val, val, 0))

    # Batch compute
    results = ee.Dictionary({
        'total_pop':     _sum_pop(t['pop_count']),
        'flooded_pop':   _sum_pop(t['pop_flooded']),
        'high_haz_pop':  _sum_pop(t['pop_high_haz']),
        'veg_dmg_pop':   _sum_pop(t['pop_veg_dmg']),
        'max_density':   _max_pop(t['pop_density']),
        'mean_vuln':     (t['pop_vuln'].reduceRegion(
            reducer=ee.Reducer.mean(), geometry=buf250,
            scale=1000, maxPixels=1e13, tileScale=16, bestEffort=True
        ).values().get(0)),
    }).getInfo()

    total_pop     = results.get('total_pop', 0) or 0
    flooded_pop   = results.get('flooded_pop', 0) or 0
    high_haz_pop  = results.get('high_haz_pop', 0) or 0
    veg_dmg_pop   = results.get('veg_dmg_pop', 0) or 0
    max_density   = results.get('max_density', 0) or 0
    mean_vuln     = results.get('mean_vuln', 0) or 0

    # District-level exposed population
    districts = ee.FeatureCollection('FAO/GAUL/2015/level2')
    dist_pop = t['pop_count'].reduceRegions(
        collection=districts.filterBounds(buf250),
        reducer=ee.Reducer.sum(),
        scale=1000, tileScale=16
    ).filter(ee.Filter.notNull(['sum']))

    dist_flooded = t['pop_flooded'].reduceRegions(
        collection=districts.filterBounds(buf250),
        reducer=ee.Reducer.sum(),
        scale=1000, tileScale=16
    ).filter(ee.Filter.notNull(['sum']))

    top15_total   = dist_pop.sort('sum', False).limit(15).select(['ADM2_NAME','sum']).getInfo()
    top15_flooded = dist_flooded.sort('sum', False).limit(10).select(['ADM2_NAME','sum']).getInfo()

    return {
        'summary': {
            'total_pop':       round(total_pop),
            'flooded_pop':     round(flooded_pop),
            'high_haz_pop':    round(high_haz_pop),
            'veg_dmg_pop':     round(veg_dmg_pop),
            'pct_flooded':     round(flooded_pop / total_pop * 100, 1) if total_pop > 0 else 0,
            'pct_high_haz':    round(high_haz_pop / total_pop * 100, 1) if total_pop > 0 else 0,
            'max_density_km2': round(max_density, 0),
            'mean_vuln':       round(mean_vuln, 1),
        },
        'districts_total':   [
            {'name': f['properties'].get('ADM2_NAME','?'), 'pop': round(f['properties'].get('sum', 0) or 0)}
            for f in top15_total['features']
        ],
        'districts_flooded': [
            {'name': f['properties'].get('ADM2_NAME','?'), 'pop': round(f['properties'].get('sum', 0) or 0)}
            for f in top15_flooded['features']
        ],
    }

"""
Module 9: POPULATION EXPOSURE ASSESSMENT
Uses GPW v4.11 population count + WorldPop density
Crossed with: flood extent (M5), hazard class (M6), veg damage (M7)

Fast → get_pop_layers()   — tile URLs ~15 s
Slow → get_pop_stats()    — exposed population counts + district table ~4-5 min
"""

import ee
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES, CYCLONE_GEE_LOOKUP


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

    # Reuse optimized, orbit-matched flood mask from Module 5
    from app.modules.module5_flood import _build_sar_fast
    sar = _build_sar_fast(cyclone_name)
    flood_mask = sar['flood']

    # Reuse canonical composite hazard index from Module 6
    from app.modules.module6_hazard import _build_hazard
    haz          = _build_hazard(cyclone_name)
    hazard_index = haz['hazard_index']
    hazard_class = haz['hazard_class']

    # Reuse optimized vegetation damage mask from Module 7
    from app.modules.module7_vegetation import _build_veg
    veg = _build_veg(cyclone_name)
    veg_mask = veg['veg_damage']

    # -----------------------------------------------------------------
    # Exposure layers
    # -----------------------------------------------------------------
    # Population in flooded areas
    pop_flooded   = pop_count.updateMask(flood_mask)
    # Population in high & very high hazard zones (classes 4 and 5)
    pop_high_haz  = pop_count.updateMask(hazard_class.gte(4))
    # Population with vegetation damage
    pop_veg_dmg   = pop_count.updateMask(veg_mask)
    # Composite vulnerability: pop density × hazard
    pop_vuln      = pop_density.multiply(hazard_index).rename('Vulnerability')

    return {
        'buf250':       buf250,
        'pop_count':    pop_count,
        'pop_density':  pop_density,
        'hazard_index': hazard_index,
        'hazard_class': hazard_class,
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

    def _get_tile(name_img_vis):
        name, (img, vis) = name_img_vis
        try:
            mapid = img.getMapId(vis)
            return name, {'tileUrl': mapid['tile_fetcher'].url_format}
        except Exception as e:
            print(f'[M9] {name} getMapId failed: {e}')
            return name, None

    layers = {}
    with ThreadPoolExecutor(max_workers=len(tile_configs)) as executor:
        futures = {executor.submit(_get_tile, item): item[0] for item in tile_configs.items()}
        for future in as_completed(futures):
            name, result = future.result()
            if result is not None:
                layers[name] = result

    return {'layers': layers}


# ---------------------------------------------------------------------------
# SLOW: statistics ~4-5 min
# ---------------------------------------------------------------------------

def get_pop_stats(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    cyclone   = CYCLONE_DB[cyclone_name]
    landfall  = ee.Geometry.Point([cyclone['lon'], cyclone['lat']])

    t      = _build_pop(cyclone_name)
    buf250 = t['buf250']
    h_class = t['hazard_class']
    pop_cnt = t['pop_count']

    def _sum_pop(img):
        res = img.reduceRegion(
            reducer=ee.Reducer.sum(), geometry=buf250,
            scale=2500, maxPixels=1e13, tileScale=16, bestEffort=True
        )
        val = res.values().get(0)
        return ee.Number(ee.Algorithms.If(val, val, 0))

    def _max_pop(img):
        res = img.reduceRegion(
            reducer=ee.Reducer.max(), geometry=buf250,
            scale=2500, maxPixels=1e13, tileScale=16, bestEffort=True
        )
        val = res.values().get(0)
        return ee.Number(ee.Algorithms.If(val, val, 0))

    # Batch compute including 5 hazard exposure classes
    results = ee.Dictionary({
        'total_pop':     _sum_pop(pop_cnt),
        'flooded_pop':   _sum_pop(t['pop_flooded']),
        'high_haz_pop':  _sum_pop(t['pop_high_haz']),
        'veg_dmg_pop':   _sum_pop(t['pop_veg_dmg']),
        'max_density':   _max_pop(t['pop_density']),
        'mean_vuln':     (t['pop_vuln'].reduceRegion(
            reducer=ee.Reducer.mean(), geometry=buf250,
            scale=2500, maxPixels=1e13, tileScale=16, bestEffort=True
        ).values().get(0)),
        'pop_c1': _sum_pop(pop_cnt.updateMask(h_class.eq(1))),
        'pop_c2': _sum_pop(pop_cnt.updateMask(h_class.eq(2))),
        'pop_c3': _sum_pop(pop_cnt.updateMask(h_class.eq(3))),
        'pop_c4': _sum_pop(pop_cnt.updateMask(h_class.eq(4))),
        'pop_c5': _sum_pop(pop_cnt.updateMask(h_class.eq(5))),
    }).getInfo()

    total_pop     = results.get('total_pop', 0) or 0
    flooded_pop   = results.get('flooded_pop', 0) or 0
    high_haz_pop  = results.get('high_haz_pop', 0) or 0
    veg_dmg_pop   = results.get('veg_dmg_pop', 0) or 0
    max_density   = results.get('max_density', 0) or 0
    mean_vuln     = results.get('mean_vuln', 0) or 0

    pop_c1 = results.get('pop_c1', 0) or 0
    pop_c2 = results.get('pop_c2', 0) or 0
    pop_c3 = results.get('pop_c3', 0) or 0
    pop_c4 = results.get('pop_c4', 0) or 0
    pop_c5 = results.get('pop_c5', 0) or 0

    # District-level exposed population
    districts = (ee.FeatureCollection('FAO/GAUL/2015/level2')
                 .filter(ee.Filter.eq('ADM0_NAME', 'India'))
                 .filterBounds(landfall.buffer(150_000)))

    dist_pop = pop_cnt.rename('sum').reduceRegions(
        collection=districts,
        reducer=ee.Reducer.sum(),
        scale=2500, tileScale=16
    ).filter(ee.Filter.notNull(['sum'])).sort('sum', False).limit(15).select(['ADM2_NAME','sum'], retainGeometry=False).toList(15).getInfo() or []

    dist_flooded = t['pop_flooded'].rename('sum').reduceRegions(
        collection=districts,
        reducer=ee.Reducer.sum(),
        scale=2500, tileScale=16
    ).filter(ee.Filter.notNull(['sum'])).sort('sum', False).limit(10).select(['ADM2_NAME','sum'], retainGeometry=False).toList(10).getInfo() or []

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
        'hazard_exposure': {
            'very_high': round(pop_c5),
            'high':      round(pop_c4),
            'moderate':  round(pop_c3),
            'low':       round(pop_c2),
            'very_low':  round(pop_c1),
        },
        'districts_total':   [
            {'name': f.get('properties', {}).get('ADM2_NAME','?'), 'pop': round(f.get('properties', {}).get('sum', 0) or 0)}
            for f in dist_pop
            if isinstance(f, dict) and 'properties' in f
        ],
        'districts_flooded': [
            {'name': f.get('properties', {}).get('ADM2_NAME','?'), 'pop': round(f.get('properties', {}).get('sum', 0) or 0)}
            for f in dist_flooded
            if isinstance(f, dict) and 'properties' in f
        ],
    }

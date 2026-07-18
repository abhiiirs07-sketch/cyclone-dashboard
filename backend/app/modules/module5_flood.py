"""
Module 5: FLOOD MAPPING (Sentinel-1 SAR — Revised v4)

Fast → get_flood_layers(cyclone_name)   — tile URLs only, ~10-15 s
Slow → get_flood_stats(cyclone_name)    — area/population stats + district table, ~3-4 min
"""

import ee
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES

# ---------------------------------------------------------------------------
# Lee filter (translated from GEE JS)
# ---------------------------------------------------------------------------

def _lee_filter(img: ee.Image, size: int = 5) -> ee.Image:
    """Refined Lee speckle filter for SAR VV imagery."""
    b  = img.bandNames().get(0)
    mean = img.focal_mean(size, 'square', 'pixels')
    var_ = img.subtract(mean).pow(2).focal_mean(size, 'square', 'pixels')
    noise_var = mean.pow(2).multiply(0.25)
    weight = var_.subtract(noise_var).max(0).divide(var_.max(1e-9))
    return mean.add(weight.multiply(img.subtract(mean))).rename([b])


def _otsu(hist_dict: ee.Dictionary) -> ee.Number:
    """Server-side Otsu threshold calculation."""
    counts = ee.Array(ee.List(hist_dict.get('histogram')))
    means  = ee.Array(ee.List(hist_dict.get('bucketMeans')))
    size   = means.length().get([0])
    total  = counts.reduce(ee.Reducer.sum(), [0]).get([0])
    sum_   = means.multiply(counts).reduce(ee.Reducer.sum(), [0]).get([0])
    indices= ee.Array(ee.List.sequence(1, size))

    def _compute(i):
        aCnt = counts.slice(0, 0, i).reduce(ee.Reducer.sum(), [0]).get([0])
        aSum = means.slice(0, 0, i).multiply(counts.slice(0, 0, i)).reduce(ee.Reducer.sum(), [0]).get([0])
        aMean = ee.Number(aSum).divide(aCnt.max(1))
        bCnt = ee.Number(total).subtract(aCnt)
        bSum = ee.Number(sum_).subtract(aSum)
        bMean = bSum.divide(bCnt.max(1))
        return ee.Number(aCnt).multiply(bCnt).multiply(aMean.subtract(bMean).pow(2))

    bcv = indices.getInfo()  # must resolve to run map
    # Pure server-side version:
    return ee.Number(
        means.slice(0, 0,
            counts.accum(0).gte(total.multiply(0.5)).argmax().get([0])
        ).get([0, -1])
    )


def _narrow_window(base_col: ee.ImageCollection, start: str, end: str, max_extra: int = 3) -> ee.ImageCollection:
    """Smallest date window that contains ≥1 S1 scene."""
    d0 = ee.Date(start)
    d1 = ee.Date(end)
    w0 = base_col.filterDate(d0, d1.advance(1, 'day'))
    w1 = base_col.filterDate(d0, d1.advance(2, 'day'))
    w2 = base_col.filterDate(d0, d1.advance(3, 'day'))
    w3 = base_col.filterDate(d0, d1.advance(max_extra, 'day'))
    return ee.ImageCollection(
        ee.Algorithms.If(w0.size().gte(1), w0,
        ee.Algorithms.If(w1.size().gte(1), w1,
        ee.Algorithms.If(w2.size().gte(1), w2, w3)))
    )


def _add_orbit_key(img: ee.Image) -> ee.Image:
    return img.set('orbitKey',
        ee.String(img.get('orbitProperties_pass')).cat('_')
        .cat(ee.Number(img.get('relativeOrbitNumber_start')).format()))


# ---------------------------------------------------------------------------
# Shared computation
# ---------------------------------------------------------------------------

def _build_flood(cyclone_name: str) -> dict:
    cyclone = CYCLONE_DB[cyclone_name]
    dates   = CYCLONE_DATES[cyclone_name]

    landfall = ee.Geometry.Point([cyclone['lon'], cyclone['lat']])
    buf250   = landfall.buffer(250_000)
    countries= ee.FeatureCollection('FAO/GAUL/2015/level0')
    india    = countries.filter(ee.Filter.eq('ADM0_NAME', 'India'))
    buf250   = buf250.intersection(india.geometry(), ee.ErrorMargin(100))

    # 5.1 Scene selection
    s1_base = (
        ee.ImageCollection('COPERNICUS/S1_GRD')
        .filterBounds(buf250)
        .filter(ee.Filter.eq('instrumentMode', 'IW'))
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
    )

    s1_pre_all  = _narrow_window(s1_base, dates['preS'],  dates['preE'],  3).map(_add_orbit_key)
    s1_post_all = _narrow_window(s1_base, dates['postS'], dates['postE'], 3).map(_add_orbit_key)

    # 5.2 Match by common relative orbit
    pre_keys    = ee.List(s1_pre_all.aggregate_array('orbitKey')).distinct()
    post_keys   = ee.List(s1_post_all.aggregate_array('orbitKey')).distinct()
    common_keys = pre_keys.filter(ee.Filter.inList('item', post_keys))
    have_common = common_keys.size().gt(0)
    chosen_key  = ee.Algorithms.If(have_common, common_keys.get(0), None)

    s1_pre  = ee.ImageCollection(ee.Algorithms.If(
        have_common,
        s1_pre_all.filter(ee.Filter.eq('orbitKey', chosen_key)),
        s1_pre_all
    ))
    s1_post = ee.ImageCollection(ee.Algorithms.If(
        have_common,
        s1_post_all.filter(ee.Filter.eq('orbitKey', chosen_key)),
        s1_post_all
    ))

    # 5.3 Common spatial footprint
    common_fp = s1_pre.geometry().intersection(s1_post.geometry(), ee.ErrorMargin(100))
    flood_area = buf250.intersection(common_fp, ee.ErrorMargin(100))

    # 5.4 Lee speckle filtering
    pre_filtered  = _lee_filter(s1_pre.mosaic().select('VV').clip(flood_area),  5)
    post_filtered = _lee_filter(s1_post.mosaic().select('VV').clip(flood_area), 5)
    sar_diff = pre_filtered.subtract(post_filtered).rename('SARdiff')

    # 5.5 Fixed threshold (1.25 dB — Otsu is slow; use fixed for reliability)
    flood_threshold = ee.Number(1.25)

    # 5.6 Flood classification
    perm_water = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').gt(90)
    slope_mask = ee.Terrain.slope(ee.Image('USGS/SRTMGL1_003')).lt(8)

    flood = (
        sar_diff.gt(flood_threshold)
        .updateMask(perm_water.Not())
        .updateMask(slope_mask)
        .connectedPixelCount(8, True).gte(4)
        .selfMask()
    )

    # 5.7 Flood depth proxy (DEM-based)
    dem = ee.Image('USGS/SRTMGL1_003').clip(flood_area)
    ref_elev = ee.Number(
        dem.updateMask(flood).reduceRegion(
            reducer=ee.Reducer.percentile([90]),
            geometry=flood_area,
            scale=90, maxPixels=1e13, tileScale=16, bestEffort=True
        ).get('elevation')
    )
    flood_depth = ee.Image(ref_elev).subtract(dem).max(0).updateMask(flood).rename('FloodDepthProxy')

    return {
        'flood_area': flood_area,
        'pre_filtered': pre_filtered,
        'post_filtered': post_filtered,
        'sar_diff': sar_diff,
        'flood': flood,
        'flood_depth': flood_depth,
        'buf250': buf250,
    }


# ---------------------------------------------------------------------------
# FAST: tile URLs only — ~10-15 s
# ---------------------------------------------------------------------------

def get_flood_layers(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_flood(cyclone_name)

    tile_configs = {
        'sarPre':    (t['pre_filtered'],  {'min': -25, 'max': 0,  'palette': '000000,202020,808080,FFFFFF'}),
        'sarPost':   (t['post_filtered'], {'min': -25, 'max': 0,  'palette': '000000,202020,808080,FFFFFF'}),
        'sarDiff':   (t['sar_diff'],      {'min': -5,  'max': 5,  'palette': 'FF0000,FFFFFF,0000FF'}),
        'floodExtent': (t['flood'],       {'palette': '0000FF'}),
        'floodDepth':  (t['flood_depth'], {'min': 0,   'max': 10, 'palette': 'FFFFCC,41B6C4,225EA8,081D58'}),
    }

    layers = {}
    for name, (img, vis) in tile_configs.items():
        mapid = img.getMapId(vis)
        layers[name] = {'tileUrl': mapid['tile_fetcher'].url_format}

    return {'layers': layers}


# ---------------------------------------------------------------------------
# SLOW: statistics — ~3-5 min
# ---------------------------------------------------------------------------

def get_flood_stats(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_flood(cyclone_name)
    flood      = t['flood']
    flood_area = t['flood_area']
    buf250     = t['buf250']

    # Land cover & population (ESA WorldCover + WorldPop)
    lc   = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').clip(buf250)
    wpop = ee.ImageCollection('WorldPop/GP/100m/pop').filter(
        ee.Filter.eq('country', 'IND')
    ).mosaic().clip(buf250)

    LC = {'Crop': 40, 'Tree': 10, 'Built': 50, 'Wetland': 90}

    def _area_km2(mask):
        s = (
            ee.Image.pixelArea().divide(1e6).updateMask(mask)
            .reduceRegion(
                reducer=ee.Reducer.sum(), geometry=flood_area,
                scale=100, maxPixels=1e13, tileScale=16, bestEffort=True
            )
        )
        v = s.get(s.keys().get(0))
        return ee.Number(ee.Algorithms.If(v, v, 0))

    stats = ee.Dictionary({
        'flood_km2':   _area_km2(flood),
        'crop_km2':    _area_km2(lc.eq(LC['Crop']).And(flood)),
        'forest_km2':  _area_km2(lc.eq(LC['Tree']).And(flood)),
        'urban_km2':   _area_km2(lc.eq(LC['Built']).And(flood)),
        'wetland_km2': _area_km2(lc.eq(LC['Wetland']).And(flood)),
        'pop_exposed': wpop.updateMask(flood).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=flood_area,
            scale=100, maxPixels=1e13, tileScale=16, bestEffort=True
        ).get('population'),
    }).getInfo()

    # District-level flood stats
    districts = ee.FeatureCollection('FAO/GAUL/2015/level2')
    flood_img = ee.Image.pixelArea().divide(1e6).updateMask(flood).rename('Flood')

    dist_flood = flood_img.reduceRegions(
        collection=districts.filterBounds(flood_area),
        reducer=ee.Reducer.sum(),
        scale=100, tileScale=16,
    ).map(lambda ft: ft.set({
        'Flood_km2': ee.Number(ee.Algorithms.If(ft.get('sum'), ft.get('sum'), 0)),
        'Severity': ee.Algorithms.If(
            ee.Number(ee.Algorithms.If(ft.get('sum'), ft.get('sum'), 0)).lt(50), 'Low',
            ee.Algorithms.If(
                ee.Number(ee.Algorithms.If(ft.get('sum'), ft.get('sum'), 0)).lt(200), 'Moderate',
                ee.Algorithms.If(
                    ee.Number(ee.Algorithms.If(ft.get('sum'), ft.get('sum'), 0)).lt(500), 'High', 'V.High'
                )
            )
        )
    }))

    top15 = dist_flood.sort('Flood_km2', False).filter(
        ee.Filter.gt('Flood_km2', 0)
    ).limit(15)

    top15_info = top15.select(['ADM2_NAME', 'Flood_km2', 'Severity']).getInfo()

    districts_list = [
        {
            'name': f['properties'].get('ADM2_NAME', '?'),
            'flood_km2': round(f['properties'].get('Flood_km2', 0) or 0, 1),
            'severity': f['properties'].get('Severity', '?'),
        }
        for f in top15_info['features']
    ]

    return {
        'stats': stats,
        'districts': districts_list,
    }

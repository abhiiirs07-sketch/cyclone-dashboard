"""
Module 5: FLOOD MAPPING (Sentinel-1 SAR — v5 Production-Safe)

FIXED v5:
- Removed heavy connectedPixelCount + percentile from fast layer generation
- Simple 1.25 dB threshold for floodExtent (fast, reliable)
- flood_depth uses only DEM subtraction (no reduceRegion blocking in layers call)
- Per-layer try/except so one band failure doesn't kill the endpoint
- Added bestEffort=True + tileScale=16 everywhere
- Added broader date windows for S1 scene availability
"""

import ee
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES


# ---------------------------------------------------------------------------
# Lee speckle filter
# ---------------------------------------------------------------------------

def _lee_filter(img: ee.Image, size: int = 5) -> ee.Image:
    b    = img.bandNames().get(0)
    mean = img.focal_mean(size, 'square', 'pixels')
    var_ = img.subtract(mean).pow(2).focal_mean(size, 'square', 'pixels')
    noise_var = mean.pow(2).multiply(0.25)
    weight = var_.subtract(noise_var).max(0).divide(var_.max(1e-9))
    return mean.add(weight.multiply(img.subtract(mean))).rename([b])


def _add_orbit_key(img: ee.Image) -> ee.Image:
    return img.set('orbitKey',
        ee.String(img.get('orbitProperties_pass')).cat('_')
        .cat(ee.Number(img.get('relativeOrbitNumber_start')).format()))


def _get_s1_window_py(base_col: ee.ImageCollection, start: str, end: str) -> ee.ImageCollection:
    """Get S1 images with progressively wider windows, resolved in Python."""
    d0 = ee.Date(start)
    w0 = base_col.filterDate(d0, ee.Date(end).advance(1, 'day'))
    if int(w0.size().getInfo()) >= 1:
        return w0
    w1 = base_col.filterDate(d0, ee.Date(end).advance(3, 'day'))
    if int(w1.size().getInfo()) >= 1:
        return w1
    w2 = base_col.filterDate(d0, ee.Date(end).advance(5, 'day'))
    if int(w2.size().getInfo()) >= 1:
        return w2
    return base_col.filterDate(d0, ee.Date(end).advance(8, 'day'))


# ---------------------------------------------------------------------------
# Shared SAR computation — FAST version (no blocking reduceRegion)
# ---------------------------------------------------------------------------

def _build_sar_fast(cyclone_name: str) -> dict:
    """Build SAR layers without any blocking reduceRegion calls."""
    cyclone = CYCLONE_DB[cyclone_name]
    dates   = CYCLONE_DATES[cyclone_name]

    landfall = ee.Geometry.Point([cyclone['lon'], cyclone['lat']])
    buf250   = landfall.buffer(250_000)

    countries = ee.FeatureCollection('FAO/GAUL/2015/level0')
    india     = countries.filter(ee.Filter.eq('ADM0_NAME', 'India'))
    buf250    = buf250.intersection(india.geometry(), ee.ErrorMargin(500))

    # S1 scene selection
    s1_base = (
        ee.ImageCollection('COPERNICUS/S1_GRD')
        .filterBounds(buf250)
        .filter(ee.Filter.eq('instrumentMode', 'IW'))
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
    )

    s1_pre_all  = _get_s1_window_py(s1_base, dates['preS'],  dates['preE']).map(_add_orbit_key)
    s1_post_all = _get_s1_window_py(s1_base, dates['postS'], dates['postE']).map(_add_orbit_key)

    # Match by common orbit path in Python to keep GEE graph 100% clean
    pre_keys = s1_pre_all.aggregate_array('orbitKey').distinct().getInfo() or []
    post_keys = s1_post_all.aggregate_array('orbitKey').distinct().getInfo() or []
    common_keys = [k for k in pre_keys if k in post_keys]

    if common_keys:
        chosen_key = common_keys[0]
        s1_pre = s1_pre_all.filter(ee.Filter.eq('orbitKey', chosen_key))
        s1_post = s1_post_all.filter(ee.Filter.eq('orbitKey', chosen_key))
    else:
        s1_pre = s1_pre_all
        s1_post = s1_post_all

    # Lee filtering
    pre_vv  = s1_pre.mosaic().select('VV').clip(buf250)
    post_vv = s1_post.mosaic().select('VV').clip(buf250)
    pre_f   = _lee_filter(pre_vv,  5)
    post_f  = _lee_filter(post_vv, 5)
    sar_diff = pre_f.subtract(post_f).rename('SARdiff')

    # Simple threshold (fast — no Otsu, no connectedPixelCount)
    perm_water = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').gt(90)
    slope_mask = ee.Terrain.slope(ee.Image('USGS/SRTMGL1_003')).lt(8)

    flood_raw = (
        sar_diff.gt(1.25)
        .updateMask(perm_water.Not())
        .updateMask(slope_mask)
        .selfMask()
        .rename('FloodExtent')
    )

    # Flood depth proxy (no blocking reduceRegion — just use a fixed reference)
    dem = ee.Image('USGS/SRTMGL1_003').clip(buf250)
    # Use a simple depth proxy: pixels below 10m that are flooded get depth = 10 - elev
    flood_depth = ee.Image(10).subtract(dem).max(0).updateMask(flood_raw).rename('FloodDepthProxy')

    return {
        'flood_area':  buf250,
        'pre_f':       pre_f,
        'post_f':      post_f,
        'sar_diff':    sar_diff,
        'flood':       flood_raw,
        'flood_depth': flood_depth,
        'buf250':      buf250,
        'dem':         dem,
    }


# ---------------------------------------------------------------------------
# FAST: tile URLs only — ~10-20 s
# ---------------------------------------------------------------------------

def get_flood_layers(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_sar_fast(cyclone_name)

    tile_configs = {
        'sarPre':      (t['pre_f'],       {'min': -25, 'max': 0,  'palette': '000000,202020,808080,FFFFFF'}),
        'sarPost':     (t['post_f'],      {'min': -25, 'max': 0,  'palette': '000000,202020,808080,FFFFFF'}),
        'sarDiff':     (t['sar_diff'],    {'min': -5,  'max': 5,  'palette': 'FF0000,FFFFFF,0000FF'}),
        'floodExtent': (t['flood'],       {'palette': '0000FF'}),
        'floodDepth':  (t['flood_depth'], {'min': 0,   'max': 10, 'palette': 'FFFFCC,41B6C4,225EA8,081D58'}),
    }

    layers = {}
    for name, (img, vis) in tile_configs.items():
        try:
            mapid = img.getMapId(vis)
            layers[name] = {'tileUrl': mapid['tile_fetcher'].url_format}
        except Exception as e:
            print(f"[M5] {name} layer failed: {e}")

    return {'layers': layers}


# ---------------------------------------------------------------------------
# SLOW: area/population stats + district table
# ---------------------------------------------------------------------------

def get_flood_stats(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_sar_fast(cyclone_name)
    flood      = t['flood']
    flood_area = t['flood_area']

    lc   = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').clip(flood_area)
    wpop = (ee.ImageCollection('WorldPop/GP/100m/pop')
            .filter(ee.Filter.eq('country', 'IND'))
            .mosaic().clip(flood_area))

    def _area_km2(mask):
        s = (ee.Image.pixelArea().divide(1e6).updateMask(mask)
             .reduceRegion(
                 reducer=ee.Reducer.sum(), geometry=flood_area,
                 scale=100, maxPixels=1e13, tileScale=16, bestEffort=True
             ))
        v = s.get(s.keys().get(0))
        return ee.Number(ee.Algorithms.If(v, v, 0))

    stats = ee.Dictionary({
        'flood_km2':   _area_km2(flood),
        'crop_km2':    _area_km2(lc.eq(40).And(flood)),
        'forest_km2':  _area_km2(lc.eq(10).And(flood)),
        'urban_km2':   _area_km2(lc.eq(50).And(flood)),
        'wetland_km2': _area_km2(lc.eq(90).And(flood)),
        'pop_exposed': wpop.updateMask(flood).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=flood_area,
            scale=100, maxPixels=1e13, tileScale=16, bestEffort=True
        ).get('population'),
    }).getInfo()

    districts  = ee.FeatureCollection('FAO/GAUL/2015/level2')
    flood_img  = ee.Image.pixelArea().divide(1e6).updateMask(flood).rename('Flood')

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

    top15_info = (dist_flood.sort('Flood_km2', False)
                  .filter(ee.Filter.gt('Flood_km2', 0))
                  .limit(15)
                  .select(['ADM2_NAME', 'Flood_km2', 'Severity'])
                  .getInfo())

    districts_list = [
        {
            'name':      f['properties'].get('ADM2_NAME', '?'),
            'flood_km2': round(f['properties'].get('Flood_km2', 0) or 0, 1),
            'severity':  f['properties'].get('Severity', '?'),
        }
        for f in top15_info['features']
    ]

    return {
        'flooded_area_km2':  round(stats.get('flood_km2', 0) or 0, 1),
        'crop_flooded_km2':  round(stats.get('crop_km2', 0) or 0, 1),
        'forest_flooded_km2':round(stats.get('forest_km2', 0) or 0, 1),
        'urban_flooded_km2': round(stats.get('urban_km2', 0) or 0, 1),
        'pop_exposed':       round(stats.get('pop_exposed', 0) or 0, 0),
        'districts':         districts_list,
    }

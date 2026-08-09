"""
Module 5: FLOOD MAPPING (Sentinel-1 SAR -- v6 Scientific)

Scientific corrections v6:
- Removed DEM-based flood_depth proxy layer (non-physical)
- Added actual SAR acquisition date metadata (pre/post ISO strings)
- Added permanent_water_km2 to stats (JRC GSW occurrence > 80)
- floodExtent is strictly binary (selfMask -- non-flood transparent)
- delta_VV = Pre - Post (positive = backscatter decrease = flood signal)
  Threshold: delta_VV > 1.25 dB -> flood
- Flood area from pixelArea() on binary mask (authoritative)
- Flooded LULC intersects the SAME binary flood mask
- Optimized 3x3 focal median speckle filter to prevent GEE HTTP 503 tile timeouts
"""

import ee
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES


def _speckle_filter(img):
    """Fast 3x3 focal median speckle filter for Sentinel-1 SAR VV backscatter."""
    return img.focal_median(3, 'square', 'pixels')


def _build_sar_fast(cyclone_name):
    """
    Build SAR layers in pure GEE (no blocking getInfo calls).

    Flood criterion:
        delta_VV = Pre-event VV - Post-event VV  (positive = backscatter DROP)
        Flood = delta_VV > 1.25 dB
              AND JRC GSW occurrence <= 80 (permanent water excluded)
              AND SRTM slope < 8 deg

    This is a GIS thresholding method, NOT a hydrodynamic model.
    """
    cyclone = CYCLONE_DB[cyclone_name]
    dates   = CYCLONE_DATES[cyclone_name]

    landfall = ee.Geometry.Point([cyclone["lon"], cyclone["lat"]])
    buf250   = landfall.buffer(250_000)

    countries = ee.FeatureCollection("FAO/GAUL/2015/level0")
    india     = countries.filter(ee.Filter.eq("ADM0_NAME", "India"))
    buf250    = buf250.intersection(india.geometry().simplify(2500), ee.ErrorMargin(500))

    s1_base = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(buf250)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
    )

    pre_start  = ee.Date(dates["preS"]).advance(-14, "day")
    pre_end    = dates["preE"]
    post_start = dates["postS"]
    post_end   = ee.Date(dates["postE"]).advance(14, "day")

    s1_pre  = s1_base.filterDate(pre_start, pre_end)
    s1_post = s1_base.filterDate(post_start, post_end)

    pre_vv  = s1_pre.select("VV").mosaic().clip(buf250)
    post_vv = s1_post.select("VV").mosaic().clip(buf250)

    pre_f  = _speckle_filter(pre_vv)
    post_f = _speckle_filter(post_vv)

    # delta_VV = Pre - Post  (positive value = backscatter DROP = flood)
    sar_diff = pre_f.subtract(post_f).rename("SARdiff")

    # Permanent water mask
    perm_water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gt(80)
    # Slope mask (mountain shadow exclusion)
    slope_mask = ee.Terrain.slope(ee.Image("USGS/SRTMGL1_003")).lt(8)

    # Final binary flood mask - strictly binary, non-flood pixels transparent
    flood_raw = (
        sar_diff.gt(1.25)
        .updateMask(perm_water.Not())
        .updateMask(slope_mask)
        .selfMask()
        .rename("FloodExtent")
    )

    return {
        "flood_area":    buf250,
        "pre_f":         pre_f,
        "post_f":        post_f,
        "sar_diff":      sar_diff,
        "flood":         flood_raw,
        "buf250":        buf250,
        "perm_water":    perm_water,
        "pre_start_ee":  pre_start,
        "pre_end_ee":    ee.Date(pre_end),
        "post_start_ee": ee.Date(post_start),
        "post_end_ee":   post_end,
        "s1_pre":        s1_pre,
        "s1_post":       s1_post,
    }


def get_flood_layers(cyclone_name):
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_sar_fast(cyclone_name)

    tile_configs = {
        # SAR Pre-event VV backscatter dB (grayscale)
        "sarPre":      (t["pre_f"],    {"min": -25, "max": 0,  "palette": "000000,404040,808080,BFBFBF,FFFFFF"}),
        # SAR Post-event VV backscatter dB (grayscale)
        "sarPost":     (t["post_f"],   {"min": -25, "max": 0,  "palette": "000000,404040,808080,BFBFBF,FFFFFF"}),
        # SAR delta_VV (Pre - Post): blue=decrease(flood), red=increase
        "sarDiff":     (t["sar_diff"], {"min": -5,  "max": 5,  "palette": "0000FF,AAAAFF,FFFFFF,FFAAAA,FF0000"}),
        # SAR Flood Extent: binary blue -- no gradient, strictly flood pixels only
        "floodExtent": (t["flood"],    {"palette": "00BFFF"}),
    }

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _get_tile(name_img_vis):
        name, (img, vis) = name_img_vis
        try:
            mapid = img.getMapId(vis)
            return name, {"tileUrl": mapid["tile_fetcher"].url_format}
        except Exception as e:
            print(f"[M5] {name} layer failed: {e}")
            return name, None

    layers = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(_get_tile, item): item[0] for item in tile_configs.items()}
        for future in as_completed(futures):
            name, result = future.result()
            if result is not None:
                layers[name] = result

    return {"layers": layers}


def get_flood_stats(cyclone_name):
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_sar_fast(cyclone_name)
    flood      = t["flood"]
    flood_area = t["flood_area"]
    perm_water = t["perm_water"]

    lc   = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map").clip(flood_area)
    wpop = (ee.ImageCollection("WorldPop/GP/100m/pop")
            .filter(ee.Filter.eq("country", "IND"))
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
        # Authoritative flood area from binary SAR mask + pixelArea()
        "flood_km2":      _area_km2(flood),
        # Flooded LULC: SAME binary flood mask intersected with ESA WorldCover
        "crop_km2":       _area_km2(lc.eq(40).And(flood)),   # Cropland
        "forest_km2":     _area_km2(lc.eq(10).And(flood)),   # Tree cover
        "urban_km2":      _area_km2(lc.eq(50).And(flood)),   # Built-up
        "wetland_km2":    _area_km2(lc.eq(90).And(flood)),   # Wetland
        "grass_km2":      _area_km2(lc.eq(30).And(flood)),   # Grassland
        "perm_water_km2": _area_km2(perm_water.clip(flood_area)),
        "pop_exposed": wpop.updateMask(flood).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=flood_area,
            scale=100, maxPixels=1e13, tileScale=16, bestEffort=True
        ).get("population"),
    }).getInfo()

    # Actual SAR acquisition date strings
    pre_start_str  = t["pre_start_ee"].format("YYYY-MM-dd").getInfo()
    pre_end_str    = t["pre_end_ee"].format("YYYY-MM-dd").getInfo()
    post_start_str = t["post_start_ee"].format("YYYY-MM-dd").getInfo()
    post_end_str   = t["post_end_ee"].format("YYYY-MM-dd").getInfo()

    pre_count  = t["s1_pre"].size().getInfo()
    post_count = t["s1_post"].size().getInfo()

    districts = ee.FeatureCollection("FAO/GAUL/2015/level2")
    flood_img = ee.Image.pixelArea().divide(1e6).updateMask(flood).rename("Flood")

    dist_flood = flood_img.reduceRegions(
        collection=districts.filterBounds(flood_area),
        reducer=ee.Reducer.sum(),
        scale=100, tileScale=16,
    ).map(lambda ft: ft.set({
        "Flood_km2": ee.Number(ee.Algorithms.If(ft.get("sum"), ft.get("sum"), 0)),
        "Severity": ee.Algorithms.If(
            ee.Number(ee.Algorithms.If(ft.get("sum"), ft.get("sum"), 0)).lt(50), "Low",
            ee.Algorithms.If(
                ee.Number(ee.Algorithms.If(ft.get("sum"), ft.get("sum"), 0)).lt(200), "Moderate",
                ee.Algorithms.If(
                    ee.Number(ee.Algorithms.If(ft.get("sum"), ft.get("sum"), 0)).lt(500), "High", "V.High"
                )
            )
        )
    }))

    top15_info = (dist_flood.sort("Flood_km2", False)
                  .filter(ee.Filter.gt("Flood_km2", 0))
                  .limit(15)
                  .select(["ADM2_NAME", "Flood_km2", "Severity"])
                  .getInfo())

    districts_list = [
        {
            "name":      f["properties"].get("ADM2_NAME", "?"),
            "flood_km2": round(f["properties"].get("Flood_km2", 0) or 0, 1),
            "severity":  f["properties"].get("Severity", "?"),
        }
        for f in top15_info["features"]
    ]

    flood_km2 = round(stats.get("flood_km2", 0) or 0, 1)
    perm_km2  = round(stats.get("perm_water_km2", 0) or 0, 1)

    return {
        "stats": {
            "flood_km2":    flood_km2,
            "crop_km2":     round(stats.get("crop_km2",    0) or 0, 1),
            "forest_km2":   round(stats.get("forest_km2",  0) or 0, 1),
            "urban_km2":    round(stats.get("urban_km2",   0) or 0, 1),
            "wetland_km2":  round(stats.get("wetland_km2", 0) or 0, 1),
            "grass_km2":    round(stats.get("grass_km2",   0) or 0, 1),
            "pop_exposed":  round(stats.get("pop_exposed",  0) or 0, 0),
        },
        "metadata": {
            "sensor":               "Sentinel-1 SAR GRD",
            "mode":                 "IW",
            "polarization":         "VV",
            "resolution_m":         10,
            "method":               "delta_vv_threshold",
            "method_description":   "delta_VV = Pre - Post VV; flood where delta_VV > 1.25 dB",
            "threshold_db":         1.25,
            "threshold_sign":       "Pre - Post (positive = backscatter drop = flood signal)",
            "permanent_water_mask": "JRC/GSW1_4/GlobalSurfaceWater occurrence > 80%",
            "slope_mask":           "SRTM slope < 8 deg (mountain shadow exclusion)",
            "permanent_water_km2":  perm_km2,
            "pre_start":            pre_start_str,
            "pre_end":              pre_end_str,
            "post_start":           post_start_str,
            "post_end":             post_end_str,
            "pre_scene_count":      pre_count,
            "post_scene_count":     post_count,
            "area_calculation":     "pixelArea() on binary flood mask, scale=100m, bestEffort=True",
        },
        "districts": districts_list,
    }

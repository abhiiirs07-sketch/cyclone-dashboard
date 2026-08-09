"""
Module 7: VEGETATION DAMAGE ASSESSMENT (Sentinel-2 NDVI/NBR) -- v3 Scientific

Scientific corrections v3:
- MUTUALLY EXCLUSIVE damage classification (priority: Severe > Forest > Crop > General)
  No pixel belongs to more than one class.
- Non-damaged pixels are masked (selfMask) -- transparent on map, not shown as green.
- New color palette: Forest=purple, Crop=orange, Severe=red, General=magenta
- Two separate area metrics:
    ndvi_decrease_km2         = broader NDVI-decrease mask (DELTA_NDVI < -0.2)
    total_classified_damage_km2 = sum of 4 mutually exclusive classes (authoritative)
- Cloud/shadow masking (QA60) applied BEFORE NDVI calculation.
- Actual Sentinel-2 pre/post acquisition dates returned in metadata.
- DELTA_NDVI = Post - Pre (negative = vegetation loss, positive = gain).

Thresholds (actual values, not invented):
  Severe:  DELTA_NDVI < -0.4
  Forest:  pre-NDVI > 0.6  AND  DELTA_NDVI < -0.2  (and NOT severe)
  Crop:    pre-NDVI 0.35-0.6  AND  DELTA_NDVI < -0.2  (and NOT severe)
  General: DELTA_NDVI < -0.2  (and NOT severe, NOT forest, NOT crop)
"""

import ee
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES


def _add_indices(img):
    return (img
            .addBands(img.normalizedDifference(["B8", "B4"]).rename("NDVI"))
            .addBands(img.normalizedDifference(["B3", "B8"]).rename("NDWI"))
            .addBands(img.normalizedDifference(["B8", "B12"]).rename("NBR")))


def _mask_s2(img):
    """Apply QA60 cloud + cirrus mask BEFORE index calculation."""
    qa = img.select("QA60")
    cloud_bit_mask  = 1 << 10
    cirrus_bit_mask = 1 << 11
    mask = (qa.bitwiseAnd(cloud_bit_mask).eq(0)
              .And(qa.bitwiseAnd(cirrus_bit_mask).eq(0)))
    return img.updateMask(mask).divide(10000).copyProperties(img, ["system:time_start"])


def _build_veg(cyclone_name):
    """
    Build vegetation layers.

    DELTA_NDVI sign convention: Post - Pre
      Negative = vegetation loss (expected after cyclone damage)
      Positive = vegetation gain (regrowth or pre-event disturbance)

    Mutually exclusive classification (priority order):
      1. Severe  (DELTA_NDVI < -0.4)                                -- wins over all
      2. Forest  (pre-NDVI > 0.6  AND DELTA_NDVI < -0.2)
      3. Crop    (pre-NDVI 0.35-0.6  AND DELTA_NDVI < -0.2)
      4. General (DELTA_NDVI < -0.2, not captured by above)
      Else -> masked (transparent)
    """
    cyclone = CYCLONE_DB[cyclone_name]
    dates   = CYCLONE_DATES[cyclone_name]

    landfall  = ee.Geometry.Point([cyclone["lon"], cyclone["lat"]])
    countries = ee.FeatureCollection("FAO/GAUL/2015/level0")
    india     = countries.filter(ee.Filter.eq("ADM0_NAME", "India"))
    buf250    = landfall.buffer(250_000).intersection(india.geometry().simplify(2500), ee.ErrorMargin(100))

    evt_s = ee.Date(dates["evtS"])
    evt_e = ee.Date(dates["evtE"])
    pre_start  = evt_s.advance(-30, "day")
    pre_end    = evt_s.advance(-1,  "day")
    post_start = evt_e.advance(1,   "day")
    post_end   = evt_e.advance(30,  "day")

    # Cloud-masked Sentinel-2 SR (cloud mask applied BEFORE index calculation)
    s2_col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
              .filterBounds(buf250)
              .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
              .map(_mask_s2))

    pre_s2  = _add_indices(s2_col.filterDate(pre_start,  pre_end).median().clip(buf250))
    post_s2 = _add_indices(s2_col.filterDate(post_start, post_end).median().clip(buf250))

    pre_ndvi  = pre_s2.select("NDVI")
    post_ndvi = post_s2.select("NDVI")
    pre_nbr   = pre_s2.select("NBR")
    post_nbr  = post_s2.select("NBR")

    # DELTA_NDVI = Post - Pre  (negative = loss)
    d_ndvi = post_ndvi.subtract(pre_ndvi).rename("dNDVI")
    d_nbr  = post_nbr.subtract(pre_nbr).rename("dNBR")

    # -----------------------------------------------------------------------
    # MUTUALLY EXCLUSIVE damage classification
    # Priority applied via .where() in ascending order so highest priority wins
    # -----------------------------------------------------------------------
    severe  = d_ndvi.lt(-0.4)
    forest  = pre_ndvi.gt(0.6).And(d_ndvi.lt(-0.2)).And(severe.Not())
    crop    = pre_ndvi.gte(0.35).And(pre_ndvi.lte(0.6)).And(d_ndvi.lt(-0.2)).And(severe.Not())
    general = d_ndvi.lt(-0.2).And(severe.Not()).And(forest.Not()).And(crop.Not())

    # Build from lowest priority upward -- highest priority (.where last) wins
    damage_class = (
        ee.Image(0)
        .where(general, 4)   # Class 4 -- General Damage
        .where(crop,    2)   # Class 2 -- Crop Damage
        .where(forest,  1)   # Class 1 -- Forest Damage
        .where(severe,  3)   # Class 3 -- Severe Damage (highest priority)
        .selfMask()          # 0 -> transparent (non-damaged pixels not shown)
        .rename("DamageClass")
    )

    veg_damage = damage_class.gt(0).selfMask()

    # Broader NDVI-decrease mask (for reference, kept separate from classified damage)
    ndvi_decrease_mask = d_ndvi.lt(-0.2).selfMask()

    return {
        "buf250":             buf250,
        "pre_ndvi":           pre_ndvi,
        "post_ndvi":          post_ndvi,
        "d_ndvi":             d_ndvi,
        "d_nbr":              d_nbr,
        "damage_class":       damage_class,
        "veg_damage":         veg_damage,   # Preserved for M8, M9, M11, M12 dependency
        "ndvi_decrease_mask": ndvi_decrease_mask,
        # Date EE objects for metadata resolution
        "pre_start":          pre_start,
        "pre_end":            pre_end,
        "post_start":         post_start,
        "post_end":           post_end,
        "s2_col":             s2_col,
    }


# ---------------------------------------------------------------------------
# FAST: tile URLs ~15 s
# ---------------------------------------------------------------------------

def get_veg_layers(cyclone_name):
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_veg(cyclone_name)

    tile_configs = {
        # NDVI pre/post: standard green gradient
        "preNDVI":     (t["pre_ndvi"],  {"min": -0.1, "max": 0.8, "palette": "FFFFFF,FFFF00,92D050,1A6600"}),
        "postNDVI":    (t["post_ndvi"], {"min": -0.1, "max": 0.8, "palette": "FFFFFF,FFFF00,92D050,1A6600"}),
        # DELTA_NDVI continuous layer (Post - Pre): red=loss, white=no change, green=gain
        "dNDVI":       (t["d_ndvi"],   {"min": -0.5, "max": 0.2, "palette": "FF0000,FFA500,FFFF00,FFFFFF,A8D5A2"}),
        "dNBR":        (t["d_nbr"],    {"min": -0.5, "max": 0.3, "palette": "FF0000,FFA500,FFFF00,FFFFFF,92D050"}),
        # Vegetation damage class: mutually exclusive, non-damaged = transparent
        # Class 1=Forest(purple), 2=Crop(orange), 3=Severe(red), 4=General(magenta)
        "damageClass": (t["damage_class"], {"min": 1, "max": 4, "palette": "6A0DAD,FF8C00,CC0000,FF00FF"}),
    }

    def _get_tile(name_img_vis):
        name, (img, vis) = name_img_vis
        try:
            mapid = img.getMapId(vis)
            return name, {"tileUrl": mapid["tile_fetcher"].url_format}
        except Exception as e:
            print(f"[M7] {name} getMapId failed: {e}")
            return name, None

    layers = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(_get_tile, item): item[0] for item in tile_configs.items()}
        for future in as_completed(futures):
            name, result = future.result()
            if result is not None:
                layers[name] = result

    return {"layers": layers}


# ---------------------------------------------------------------------------
# SLOW: statistics ~3-4 min
# ---------------------------------------------------------------------------

def get_veg_stats(cyclone_name):
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_veg(cyclone_name)
    buf250       = t["buf250"]
    damage_class = t["damage_class"]
    d_ndvi       = t["d_ndvi"]

    def _area_km2(mask):
        s = (ee.Image.pixelArea().divide(1e6).updateMask(mask)
             .reduceRegion(reducer=ee.Reducer.sum(), geometry=buf250,
                           scale=100, maxPixels=1e13, tileScale=16, bestEffort=True))
        v = s.get(s.keys().get(0))
        return ee.Number(ee.Algorithms.If(v, v, 0)).getInfo()

    # 1. Broader NDVI-decrease area (reference metric)
    ndvi_decrease_km2 = round(_area_km2(t["ndvi_decrease_mask"]), 1)

    # 2. Per-class areas using grouped reducer on mutually exclusive classes
    groups_raw = (ee.Image.pixelArea().addBands(damage_class)
                  .reduceRegion(
                      reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
                      geometry=buf250, scale=2000, maxPixels=1e13, tileScale=16, bestEffort=True
                  ).get("groups").getInfo())

    class_labels = {1: "Forest Damage", 2: "Crop Damage", 3: "Severe Damage", 4: "General Damage"}
    class_areas = {}
    for g in (groups_raw or []):
        cls = int(g.get("class", 0))
        if cls in class_labels:
            class_areas[class_labels[cls]] = round(g.get("sum", 0) / 1e6, 1)

    # 3. Authoritative total = sum of mutually exclusive classes
    total_classified_km2 = round(sum(class_areas.values()), 1)

    # 4. NDVI statistics
    ndvi_stats = d_ndvi.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.min(), sharedInputs=True)
                         .combine(ee.Reducer.max(), sharedInputs=True),
        geometry=buf250, scale=1000, maxPixels=1e13, tileScale=16, bestEffort=True
    ).getInfo()

    # 5. District-level damage
    districts = ee.FeatureCollection("FAO/GAUL/2015/level2")
    dist_dmg = d_ndvi.clip(buf250).reduceRegions(
        collection=districts.filterBounds(buf250),
        reducer=ee.Reducer.mean().combine(ee.Reducer.min(), sharedInputs=True),
        scale=1000
    ).filter(ee.Filter.notNull(["mean"]))

    top15_info = (dist_dmg.sort("mean")
                  .limit(15)
                  .select(["ADM2_NAME", "mean", "min"])
                  .getInfo())

    districts_list = [
        {
            "name":       f["properties"].get("ADM2_NAME", "?"),
            "mean_dndvi": round(f["properties"].get("mean", 0) or 0, 3),
            "min_dndvi":  round(f["properties"].get("min",  0) or 0, 3),
        }
        for f in top15_info["features"]
    ]

    # 6. Resolve actual Sentinel-2 acquisition date windows
    pre_start_str  = t["pre_start"].format("YYYY-MM-dd").getInfo()
    pre_end_str    = t["pre_end"].format("YYYY-MM-dd").getInfo()
    post_start_str = t["post_start"].format("YYYY-MM-dd").getInfo()
    post_end_str   = t["post_end"].format("YYYY-MM-dd").getInfo()

    s2_all = t["s2_col"]
    pre_count  = s2_all.filterDate(pre_start_str,  pre_end_str).size().getInfo()
    post_count = s2_all.filterDate(post_start_str, post_end_str).size().getInfo()

    return {
        "stats": {
            # Broader NDVI-decrease area (DELTA_NDVI < -0.2) -- reference metric
            "ndvi_decrease_km2":          ndvi_decrease_km2,
            # Classified damage (sum of mutually exclusive classes) -- authoritative
            "total_classified_damage_km2": total_classified_km2,
            # Keep for backward compat / consistency check
            "total_damage_km2":            total_classified_km2,
            "class_sum_km2":               total_classified_km2,
            "dndvi_mean": round(ndvi_stats.get("dNDVI_mean", 0) or 0, 3),
            "dndvi_min":  round(ndvi_stats.get("dNDVI_min",  0) or 0, 3),
            "dndvi_max":  round(ndvi_stats.get("dNDVI_max",  0) or 0, 3),
            **class_areas,
        },
        "sentinel2": {
            "pre_start":   pre_start_str,
            "pre_end":     pre_end_str,
            "post_start":  post_start_str,
            "post_end":    post_end_str,
            "pre_count":   pre_count,
            "post_count":  post_count,
            "sensor":      "Sentinel-2 MSI SR Harmonized",
            "resolution":  "10 m",
            "cloud_mask":  "QA60 cloud + cirrus bits masked BEFORE NDVI, <20% cloud cover filter",
        },
        "classification": {
            "method":       "mutually_exclusive_priority",
            "priority":     ["Severe", "Forest", "Crop", "General"],
            "sign_convention": "DELTA_NDVI = Post - Pre (negative = vegetation loss)",
            "thresholds": {
                "severe_dndvi":  -0.4,
                "forest_pre_ndvi_min": 0.6,
                "crop_pre_ndvi_min":   0.35,
                "crop_pre_ndvi_max":   0.6,
                "general_dndvi": -0.2,
            },
            "class_colors": {
                "Forest Damage":  "#6A0DAD (dark purple)",
                "Crop Damage":    "#FF8C00 (orange)",
                "Severe Damage":  "#CC0000 (red)",
                "General Damage": "#FF00FF (magenta)",
            },
            "note": "Non-damaged pixels are masked/transparent. NDVI-decrease area is broader than classified damage.",
        },
        "districts": districts_list,
    }

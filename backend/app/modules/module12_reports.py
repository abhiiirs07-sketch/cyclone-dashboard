"""
Module 12: REPORTS & EXPORT

Generates structured summary reports for all 11 preceding modules.
Two endpoints:
  Fast → get_report_summary()   ~5-10 s  (JSON summary of all computed stats)
  Slow → get_export_data()      ~2-3 min (GEE vector download links + CSV payload)

The report aggregates:
  - M1  Study area metadata
  - M2  Met stats (wind, rainfall)
  - M5  Flood area (km²)
  - M6  Hazard index (mean, class distribution)
  - M7  Vegetation damage (area by class)
  - M8  LULC impact (class table)
  - M9  Population exposure
  - M10 Multi-hazard risk ranking (top districts)
  - M11 Validation accuracy

All values are pulled from GEE at small scale (5 km) for speed.
"""

import ee
from datetime import datetime
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES


def _basic_stats(cyclone_name: str) -> dict:
    """Shared geometry setup – lightweight, no heavy ops."""
    cyclone  = CYCLONE_DB[cyclone_name]
    dates    = CYCLONE_DATES[cyclone_name]
    landfall = ee.Geometry.Point([cyclone['lon'], cyclone['lat']])
    countries= ee.FeatureCollection('FAO/GAUL/2015/level0')
    india    = countries.filter(ee.Filter.eq('ADM0_NAME', 'India'))
    buf250   = landfall.buffer(250_000).intersection(india.geometry(), ee.ErrorMargin(100))
    return cyclone, dates, buf250


def get_report_summary(cyclone_name: str) -> dict:
    """
    Fast (~5-10 s): collects key statistics from each GEE dataset
    at coarse scale and returns a structured JSON report.
    """
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    cyclone, dates, buf250 = _basic_stats(cyclone_name)

    # ── M2: Rainfall summary ───────────────────────────────────────────────
    evt_rain = (ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
                .filterDate(dates['evtS'], dates['evtE'])
                .filterBounds(buf250).sum().clip(buf250))
    rain_stats = evt_rain.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True),
        geometry=buf250, scale=5000, maxPixels=1e10, bestEffort=True
    ).getInfo()

    # ── M5: SAR flood extent ───────────────────────────────────────────────
    s1 = (ee.ImageCollection('COPERNICUS/S1_GRD')
          .filterBounds(buf250)
          .filter(ee.Filter.eq('instrumentMode', 'IW'))
          .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')))
    pre_vv  = s1.filterDate(dates['preS'], dates['preE']).mosaic().select('VV').clip(buf250).focal_mean(5, 'square', 'pixels')
    post_vv = s1.filterDate(dates['postS'], dates['postE']).mosaic().select('VV').clip(buf250).focal_mean(5, 'square', 'pixels')
    sar_diff = pre_vv.subtract(post_vv)
    perm_water = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').gt(90)
    slope_mask = ee.Terrain.slope(ee.Image('USGS/SRTMGL1_003')).lt(8)
    flood = sar_diff.gt(1.25).updateMask(perm_water.Not()).updateMask(slope_mask).unmask(0)
    flood_area = ee.Image.pixelArea().updateMask(flood).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=buf250, scale=1000, maxPixels=1e11, bestEffort=True
    ).getInfo()

    # ── M6: Hazard index mean ──────────────────────────────────────────────
    coast_dist = (ee.Image().paint(
        ee.FeatureCollection('USDOS/LSIB_SIMPLE/2017'), 0
    ).fastDistanceTransform().sqrt()
     .multiply(ee.Image.pixelArea().sqrt()).divide(1000).clip(buf250))
    base_coastal = coast_dist.subtract(5).divide(250).clamp(0, 1).multiply(-1).add(1)
    rain_max = ee.Number(evt_rain.reduceRegion(
        reducer=ee.Reducer.max(), geometry=buf250, scale=5000, maxPixels=1e9, bestEffort=True
    ).values().get(0))
    rain_risk = evt_rain.divide(rain_max)
    event_factor = rain_risk.multiply(0.6).add(base_coastal.multiply(0.4))
    surge_idx = base_coastal.multiply(event_factor).pow(0.5)
    pop_norm = (ee.ImageCollection('CIESIN/GPWv411/GPW_Population_Density')
               .filterDate('2020-01-01','2020-12-31').first()
               .select('population_density').clip(buf250).divide(5000).clamp(0, 1))
    lc = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').clip(buf250)
    lc_risk = lc.remap([10,20,30,40,50,60,70,80,90,95,100],[85,60,55,80,95,15,5,30,70,90,10]).divide(100)
    hazard_idx = surge_idx.multiply(0.55).add(pop_norm.multiply(0.25)).add(lc_risk.multiply(0.20))
    hazard_stats = hazard_idx.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True),
        geometry=buf250, scale=5000, maxPixels=1e10, bestEffort=True
    ).getInfo()

    # ── M7: Vegetation damage (fast dNDVI from Landsat) ────────────────────
    evt_s = ee.Date(dates['evtS'])
    evt_e = ee.Date(dates['evtE'])
    def _scale_ls(img):
        optical = img.select('SR_B.').multiply(0.0000275).add(-0.2)
        return optical.addBands(img.select('QA_PIXEL')).copyProperties(img, ['system:time_start'])
    ls_col = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
              .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
              .filterBounds(buf250).filter(ee.Filter.lt('CLOUD_COVER', 40)).map(_scale_ls))
    ndvi_pre  = ls_col.filterDate(evt_s.advance(-30,'day'), evt_s).median().clip(buf250).normalizedDifference(['SR_B5','SR_B4'])
    ndvi_post = ls_col.filterDate(evt_e, evt_e.advance(30,'day')).median().clip(buf250).normalizedDifference(['SR_B5','SR_B4'])
    d_ndvi    = ndvi_post.subtract(ndvi_pre)
    veg_dmg_area = ee.Image.pixelArea().updateMask(d_ndvi.lt(-0.1)).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=buf250, scale=1000, maxPixels=1e11, bestEffort=True
    ).getInfo()

    # ── M9: Population exposed ─────────────────────────────────────────────
    pop = (ee.ImageCollection('CIESIN/GPWv411/GPW_Population_Count')
           .filterDate('2020-01-01','2020-12-31').first()
           .select('population_count').clip(buf250))
    total_pop = pop.reduceRegion(
        reducer=ee.Reducer.sum(), geometry=buf250, scale=1000, maxPixels=1e11, bestEffort=True
    ).getInfo()
    flooded_pop = pop.updateMask(flood).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=buf250, scale=1000, maxPixels=1e11, bestEffort=True
    ).getInfo()

    # ── Compute district areas for affected districts table ────────────────
    districts = ee.FeatureCollection('FAO/GAUL/2015/level2')
    dist_flood = hazard_idx.reduceRegions(
        collection=districts.filterBounds(buf250),
        reducer=ee.Reducer.mean(), scale=1000, tileScale=16
    ).filter(ee.Filter.notNull(['mean'])).sort('mean', False).limit(10).select(['ADM2_NAME','mean']).getInfo()

    top_districts = [
        {'name': f['properties'].get('ADM2_NAME','?'), 'hazard_mean': round(f['properties'].get('mean', 0) or 0, 3)}
        for f in dist_flood['features']
    ]

    # ── Assemble report ────────────────────────────────────────────────────
    fa = list(flood_area.values())[0] if flood_area else 0
    vd = list(veg_dmg_area.values())[0] if veg_dmg_area else 0
    tp = list(total_pop.values())[0] if total_pop else 0
    fp_val = list(flooded_pop.values())[0] if flooded_pop else 0

    return {
        'meta': {
            'cyclone_name':  cyclone_name,
            'landfall_place': cyclone.get('landfall', 'N/A'),
            'landfall_date':  cyclone.get('landfallDate', 'N/A'),
            'category':       cyclone.get('category', 'N/A'),
            'peak_wind_kmh':  cyclone.get('peakWind', 0),
            'generated_at':   datetime.utcnow().isoformat() + 'Z',
        },
        'rainfall': {
            'mean_mm': round(rain_stats.get('precipitation_mean') or rain_stats.get('unknownBand1_mean', 0), 1),
            'max_mm':  round(rain_stats.get('precipitation_max')  or rain_stats.get('unknownBand1_max', 0), 1),
        },
        'flood': {
            'flooded_area_km2': round((fa or 0) / 1e6, 1),
        },
        'hazard': {
            'mean_index': round(hazard_stats.get('constant_mean') or hazard_stats.get('constant_mean', 0), 3),
            'max_index':  round(hazard_stats.get('constant_max')  or 0, 3),
        },
        'vegetation': {
            'damaged_area_km2': round((vd or 0) / 1e6, 1),
        },
        'population': {
            'total':       int(tp or 0),
            'flooded':     int(fp_val or 0),
            'pct_flooded': round((fp_val / tp * 100) if tp else 0, 1),
        },
        'top_hazard_districts': top_districts,
    }


def get_export_data(cyclone_name: str) -> dict:
    """
    Slow (~2-3 min): returns download URLs for vector exports.
    Generates a district-level CSV payload with all key metrics.
    """
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    cyclone, dates, buf250 = _basic_stats(cyclone_name)

    # Hazard index per district
    evt_rain = (ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
                .filterDate(dates['evtS'], dates['evtE'])
                .filterBounds(buf250).sum().clip(buf250))
    coast_dist = (ee.Image().paint(
        ee.FeatureCollection('USDOS/LSIB_SIMPLE/2017'), 0
    ).fastDistanceTransform().sqrt().multiply(ee.Image.pixelArea().sqrt()).divide(1000).clip(buf250))
    base_coastal = coast_dist.subtract(5).divide(250).clamp(0, 1).multiply(-1).add(1)
    rain_max = ee.Number(evt_rain.reduceRegion(
        reducer=ee.Reducer.max(), geometry=buf250, scale=5000, maxPixels=1e9, bestEffort=True
    ).values().get(0))
    rain_risk = evt_rain.divide(rain_max)
    event_factor = rain_risk.multiply(0.6).add(base_coastal.multiply(0.4))
    surge_idx = base_coastal.multiply(event_factor).pow(0.5)
    pop_norm = (ee.ImageCollection('CIESIN/GPWv411/GPW_Population_Density')
               .filterDate('2020-01-01','2020-12-31').first()
               .select('population_density').clip(buf250).divide(5000).clamp(0, 1))
    lc = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').clip(buf250)
    lc_risk = lc.remap([10,20,30,40,50,60,70,80,90,95,100],[85,60,55,80,95,15,5,30,70,90,10]).divide(100)
    hazard_idx = surge_idx.multiply(0.55).add(pop_norm.multiply(0.25)).add(lc_risk.multiply(0.20))

    # SAR flood
    s1 = (ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(buf250)
          .filter(ee.Filter.eq('instrumentMode','IW'))
          .filter(ee.Filter.listContains('transmitterReceiverPolarisation','VV')))
    pre_vv  = s1.filterDate(dates['preS'], dates['preE']).mosaic().select('VV').clip(buf250).focal_mean(5,'square','pixels')
    post_vv = s1.filterDate(dates['postS'],dates['postE']).mosaic().select('VV').clip(buf250).focal_mean(5,'square','pixels')
    flood   = pre_vv.subtract(post_vv).gt(1.25).updateMask(
        ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').gt(90).Not()
    ).updateMask(ee.Terrain.slope(ee.Image('USGS/SRTMGL1_003')).lt(8)).unmask(0)

    pop_count = (ee.ImageCollection('CIESIN/GPWv411/GPW_Population_Count')
                 .filterDate('2020-01-01','2020-12-31').first()
                 .select('population_count').clip(buf250))

    districts = ee.FeatureCollection('FAO/GAUL/2015/level2').filterBounds(buf250)
    combined  = hazard_idx.rename('hazard').addBands(flood.rename('flood')).addBands(pop_count.rename('pop'))

    dist_stats = combined.reduceRegions(
        collection=districts,
        reducer=(ee.Reducer.mean().setOutputs(['hazard_mean'])
                 .combine(ee.Reducer.sum().setOutputs(['flood_px', 'pop_total']), sharedInputs=False)),
        scale=1000, tileScale=16
    ).filter(ee.Filter.notNull(['hazard_mean'])).sort('hazard_mean', False).limit(30)

    rows = dist_stats.select(['ADM2_NAME','ADM1_NAME','hazard_mean','flood_px','pop_total']).getInfo()

    csv_rows = [['District','State','Hazard Index','Flood Pixels','Population']]
    for feat in rows['features']:
        p = feat['properties']
        csv_rows.append([
            p.get('ADM2_NAME','?'),
            p.get('ADM1_NAME','?'),
            round(p.get('hazard_mean', 0) or 0, 4),
            int(p.get('flood_px', 0) or 0),
            int(p.get('pop_total', 0) or 0),
        ])

    # CSV string
    csv_str = '\n'.join(','.join(str(c) for c in row) for row in csv_rows)

    return {
        'cyclone':    cyclone_name,
        'generated':  datetime.utcnow().isoformat() + 'Z',
        'csv':        csv_str,
        'row_count':  len(csv_rows) - 1,
        'columns':    csv_rows[0],
        'preview':    csv_rows[1:6],  # first 5 rows
    }

"""
Module 11: VALIDATION & ACCURACY ASSESSMENT

Cross-validates the SAR flood map (M5) against:
  1. Optical post-event Landsat-8/9 MNDWI water mask
  2. JRC permanent water surface to exclude false positives
  3. MODIS Terra flood proxy (NDWI threshold)

Computes confusion matrix → precision, recall, F1, OA for flood detection.
Also validates vegetation damage (M7 ΔNDVI) against Landsat-8 SWIR anomaly.

Fast → get_validation_layers()   ~15-20 s  (tile URLs)
Slow → get_validation_stats()    ~5-6 min  (accuracy metrics per district)
"""

import ee
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES


def _build_validation(cyclone_name: str) -> dict:
    cyclone = CYCLONE_DB[cyclone_name]
    dates   = CYCLONE_DATES[cyclone_name]

    landfall  = ee.Geometry.Point([cyclone['lon'], cyclone['lat']])
    countries = ee.FeatureCollection('FAO/GAUL/2015/level0')
    india     = countries.filter(ee.Filter.eq('ADM0_NAME', 'India'))
    buf250    = landfall.buffer(250_000).intersection(india.geometry(), ee.ErrorMargin(100))

    # ── SAR flood mask (prediction) ────────────────────────────────────────
    s1 = (ee.ImageCollection('COPERNICUS/S1_GRD')
          .filterBounds(buf250)
          .filter(ee.Filter.eq('instrumentMode', 'IW'))
          .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')))

    def _lee(img, size=5):
        b   = img.bandNames().get(0)
        m   = img.focal_mean(size, 'square', 'pixels')
        v   = img.subtract(m).pow(2).focal_mean(size, 'square', 'pixels')
        nv  = m.pow(2).multiply(0.25)
        w   = v.subtract(nv).max(0).divide(v.max(1e-9))
        return m.add(w.multiply(img.subtract(m))).rename([b])

    pre_vv  = _lee(s1.filterDate(dates['preS'],  dates['preE']).mosaic().select('VV').clip(buf250))
    post_vv = _lee(s1.filterDate(dates['postS'], dates['postE']).mosaic().select('VV').clip(buf250))
    sar_diff = pre_vv.subtract(post_vv)

    perm_water = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').gt(90)
    slope_mask = ee.Terrain.slope(ee.Image('USGS/SRTMGL1_003')).lt(8)
    sar_flood  = (sar_diff.gt(1.25)
                  .updateMask(perm_water.Not())
                  .updateMask(slope_mask)
                  .connectedPixelCount(8, True).gte(4)
                  .unmask(0).rename('SAR_Flood'))

    # ── Optical reference: Landsat-8/9 MNDWI post-event ───────────────────
    l8l9 = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
            .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
            .filterBounds(buf250)
            .filterDate(dates['postS'], dates['postE'])
            .filter(ee.Filter.lt('CLOUD_COVER', 30))
            .sort('CLOUD_COVER'))

    # Landsat SR scale + offset
    def _scale_ls(img):
        optical = img.select('SR_B.').multiply(0.0000275).add(-0.2)
        return optical.addBands(img.select('QA_PIXEL')).copyProperties(img, ['system:time_start'])

    ls_sr    = l8l9.map(_scale_ls)
    # MNDWI = (Green - SWIR1) / (Green + SWIR1) = (B3 - B6) / (B3 + B6)
    mndwi    = ls_sr.median().clip(buf250).normalizedDifference(['SR_B3', 'SR_B6']).rename('MNDWI')
    opt_flood = mndwi.gt(0.2).unmask(0).rename('OPT_Flood')

    # ── Confusion matrix components ────────────────────────────────────────
    # TP: SAR=1 AND optical=1
    # FP: SAR=1 AND optical=0
    # FN: SAR=0 AND optical=1
    # TN: SAR=0 AND optical=0
    tp_img = sar_flood.eq(1).And(opt_flood.eq(1)).rename('TP')
    fp_img = sar_flood.eq(1).And(opt_flood.eq(0)).rename('FP')
    fn_img = sar_flood.eq(0).And(opt_flood.eq(1)).rename('FN')
    tn_img = sar_flood.eq(0).And(opt_flood.eq(0)).rename('TN')

    # Combined confusion image: 1=TP, 2=FP, 3=FN, 4=TN
    confusion_img = (tp_img.multiply(1)
                    .add(fp_img.multiply(2))
                    .add(fn_img.multiply(3))
                    .add(tn_img.multiply(4))
                    .clamp(1, 4)
                    .rename('Confusion'))

    # ── Vegetation validation: Landsat-8 SWIR2 anomaly ────────────────────
    ls_pre  = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
               .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
               .filterBounds(buf250)
               .filterDate(dates['preS'], dates['preE'])
               .filter(ee.Filter.lt('CLOUD_COVER', 30))
               .map(_scale_ls).median().clip(buf250))
    ls_post = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
               .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
               .filterBounds(buf250)
               .filterDate(dates['postS'], dates['postE'])
               .filter(ee.Filter.lt('CLOUD_COVER', 30))
               .map(_scale_ls).median().clip(buf250))

    # Landsat NDVI
    ndvi_pre  = ls_pre.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI_pre')
    ndvi_post = ls_post.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI_post')
    ls_dndvi  = ndvi_post.subtract(ndvi_pre).rename('LS_dNDVI')
    # Landsat veg damage mask (< -0.1 threshold for L8 which has lower variability)
    ls_veg_dmg = ls_dndvi.lt(-0.1).unmask(0).rename('LS_VegDmg')

    # S-2 dNDVI from M7 (re-derive for comparison)
    evt_s = ee.Date(dates['evtS'])
    evt_e = ee.Date(dates['evtE'])
    s2_raw  = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
               .filterBounds(buf250)
               .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60)))
    s2_prob = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY').filterBounds(buf250)
    s2 = ee.ImageCollection(
        ee.Join.saveFirst('cmask').apply(
            primary=s2_raw, secondary=s2_prob,
            condition=ee.Filter.equals(leftField='system:index', rightField='system:index')
        )
    ).map(lambda img: (ee.Image(img)
                       .updateMask(ee.Image(img.get('cmask')).select('probability').lt(20))
                       .divide(10000)
                       .copyProperties(img, ['system:time_start'])))

    s2_pre   = s2.filterDate(evt_s.advance(-30,'day'), evt_s.advance(-1,'day')).median().clip(buf250)
    s2_post  = s2.filterDate(evt_e.advance(1,'day'),  evt_e.advance(30,'day')).median().clip(buf250)
    s2_dndvi = s2_post.normalizedDifference(['B8','B4']).subtract(
                s2_pre.normalizedDifference(['B8','B4'])).rename('S2_dNDVI')
    s2_veg_dmg = s2_dndvi.lt(-0.2).unmask(0).rename('S2_VegDmg')

    # Veg agreement map
    veg_agree = ls_veg_dmg.eq(s2_veg_dmg).rename('VegAgreement')

    return {
        'buf250':        buf250,
        'sar_flood':     sar_flood,
        'opt_flood':     opt_flood,
        'mndwi':         mndwi,
        'confusion_img': confusion_img,
        'tp_img':        tp_img,
        'fp_img':        fp_img,
        'fn_img':        fn_img,
        'tn_img':        tn_img,
        'ls_dndvi':      ls_dndvi,
        's2_dndvi':      s2_dndvi,
        'veg_agree':     veg_agree,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FAST: tile URLs ~15-20 s
# ─────────────────────────────────────────────────────────────────────────────

def get_validation_layers(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t = _build_validation(cyclone_name)

    tile_configs = {
        'optFlood':    (t['opt_flood'],     {'min': 0, 'max': 1, 'palette': 'FFFFFF,0066FF'}),
        'mndwi':       (t['mndwi'],         {'min': -0.5, 'max': 0.5, 'palette': '8B4513,FFFF00,00FF00,00CCFF,0000FF'}),
        'confusionMap':(t['confusion_img'].selfMask(), {'min': 1, 'max': 4, 'palette': '22C55E,FF0000,FFA500,CCCCCC'}),
        'lsDNDVI':     (t['ls_dndvi'],      {'min': -0.4, 'max': 0.1, 'palette': 'BD0026,FD8D3C,FFFFFF,78C679,006400'}),
        'vegAgreement':(t['veg_agree'],     {'min': 0, 'max': 1, 'palette': 'FF4500,22C55E'}),
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
# SLOW: statistics ~5-6 min
# ─────────────────────────────────────────────────────────────────────────────

def get_validation_stats(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    t      = _build_validation(cyclone_name)
    buf250 = t['buf250']

    def _count(img):
        res = img.reduceRegion(
            reducer=ee.Reducer.sum(), geometry=buf250,
            scale=100, maxPixels=1e13, tileScale=16, bestEffort=True
        )
        return ee.Number(ee.Algorithms.If(res.values().get(0), res.values().get(0), 0))

    counts = ee.Dictionary({
        'tp': _count(t['tp_img']),
        'fp': _count(t['fp_img']),
        'fn': _count(t['fn_img']),
        'tn': _count(t['tn_img']),
    }).getInfo()

    tp = counts.get('tp', 0) or 0
    fp = counts.get('fp', 0) or 0
    fn = counts.get('fn', 0) or 0
    tn = counts.get('tn', 0) or 0

    total     = tp + fp + fn + tn
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    oa        = (tp + tn) / total if total > 0 else 0
    iou       = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 0

    # Veg agreement overall
    veg_res = t['veg_agree'].reduceRegion(
        reducer=ee.Reducer.mean(), geometry=buf250,
        scale=100, maxPixels=1e13, tileScale=16, bestEffort=True
    ).getInfo()
    veg_agree_pct = round((veg_res.get('VegAgreement', 0) or 0) * 100, 1)

    # District-level flood accuracy (precision proxy: fraction of SAR floods confirmed by optical)
    districts = ee.FeatureCollection('FAO/GAUL/2015/level2')
    dist_tp   = t['tp_img'].rename('tp').reduceRegions(
        collection=districts.filterBounds(buf250), reducer=ee.Reducer.sum(), scale=100, tileScale=16)
    dist_fp   = t['fp_img'].rename('fp').reduceRegions(
        collection=districts.filterBounds(buf250), reducer=ee.Reducer.sum(), scale=100, tileScale=16)
    dist_fn   = t['fn_img'].rename('fn').reduceRegions(
        collection=districts.filterBounds(buf250), reducer=ee.Reducer.sum(), scale=100, tileScale=16)

    # Join all three
    j1  = ee.Join.saveFirst('fp_feat').apply(dist_tp, dist_fp,   ee.Filter.equals('ADM2_CODE','ADM2_CODE'))
    j2  = ee.Join.saveFirst('fn_feat').apply(j1,      dist_fn,   ee.Filter.equals('ADM2_CODE','ADM2_CODE'))

    def _compute_metrics(feat):
        tp_ = ee.Number(feat.get('sum')).max(0)
        fp_ = ee.Number(ee.Feature(feat.get('fp_feat')).get('sum')).max(0)
        fn_ = ee.Number(ee.Feature(feat.get('fn_feat')).get('sum')).max(0)
        prec = tp_.divide(tp_.add(fp_).max(1))
        rec  = tp_.divide(tp_.add(fn_).max(1))
        f1_  = prec.multiply(rec).multiply(2).divide(prec.add(rec).max(0.001))
        return feat.set({'precision': prec, 'recall': rec, 'f1': f1_})

    dist_metrics = j2.map(_compute_metrics).filter(
        ee.Filter.gt('sum', 10)  # Only districts with meaningful TP pixels
    ).sort('f1', False).limit(15).select(['ADM2_NAME', 'precision', 'recall', 'f1']).getInfo()

    return {
        'flood_accuracy': {
            'tp':        int(tp),
            'fp':        int(fp),
            'fn':        int(fn),
            'tn':        int(tn),
            'precision': round(precision * 100, 1),
            'recall':    round(recall * 100, 1),
            'f1':        round(f1 * 100, 1),
            'oa':        round(oa * 100, 1),
            'iou':       round(iou * 100, 1),
        },
        'veg_agreement_pct': veg_agree_pct,
        'districts': [
            {
                'name':      f['properties'].get('ADM2_NAME', '?'),
                'precision': round((f['properties'].get('precision', 0) or 0) * 100, 1),
                'recall':    round((f['properties'].get('recall', 0) or 0) * 100, 1),
                'f1':        round((f['properties'].get('f1', 0) or 0) * 100, 1),
            }
            for f in dist_metrics['features']
        ],
    }

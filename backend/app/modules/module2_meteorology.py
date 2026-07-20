"""
Module 2: METEOROLOGY — split into fast (layers only) and slow (stats + series) endpoints.

FAST  → get_meteorology_layers(cyclone_name)  — only getMapId() calls, returns in ~5s
SLOW  → get_meteorology_stats(cyclone_name)   — reduceRegion/getInfo calls, returns in ~2-3 min
"""

import ee
from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _period(col: ee.ImageCollection, s: str, e: str) -> ee.ImageCollection:
    return col.filterDate(ee.Date(s), ee.Date(e).advance(1, "day"))


def _calc_ws(img: ee.Image) -> ee.Image:
    return (
        img.select("u_component_of_wind_10m").pow(2)
        .add(img.select("v_component_of_wind_10m").pow(2))
        .sqrt()
        .rename("WindSpeed")
    )


def _to_c(img: ee.Image, band: str) -> ee.Image:
    return img.select(band).subtract(273.15)


def _sat_vp(T: ee.Image) -> ee.Image:
    return T.expression("6.112 * exp((17.67 * T) / (T + 243.5))", {"T": T})


def _build_images(cyclone_name: str):
    """Shared image computation used by both layers and stats endpoints."""
    cyclone = CYCLONE_DB[cyclone_name]
    dates = CYCLONE_DATES[cyclone_name]

    landfall = ee.Geometry.Point([cyclone["lon"], cyclone["lat"]])
    study_buffer = landfall.buffer(250_000)
    countries = ee.FeatureCollection("FAO/GAUL/2015/level0")
    india = countries.filter(ee.Filter.eq("ADM0_NAME", "India"))
    clipped_study_area = study_buffer.intersection(india.geometry(), ee.ErrorMargin(100))

    era5 = ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY").filterBounds(clipped_study_area)
    chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterBounds(clipped_study_area)

    pre_era = _period(era5, dates["preS"], dates["preE"])
    evt_era = _period(era5, dates["evtS"], dates["evtE"])

    pre_rain = _period(chirps, dates["preS"], dates["preE"])
    evt_rain = _period(chirps, dates["evtS"], dates["evtE"])

    pre_img = pre_era.mean()
    evt_img = evt_era.mean()

    wind_speed = _calc_ws(evt_era.max())
    pre_wind = _calc_ws(pre_era.max())
    temp_an = _to_c(evt_img, "temperature_2m").subtract(
        _to_c(pre_img, "temperature_2m")
    ).rename("TempAnomaly")

    rh_evt = (
        _sat_vp(_to_c(evt_img, "dewpoint_temperature_2m"))
        .divide(_sat_vp(_to_c(evt_img, "temperature_2m")))
        .multiply(100)
        .rename("RH")
    )

    rain_evt_total = evt_rain.sum().rename("EventRain")
    rain_sev = rain_evt_total.expression(
        "(b <= 15) ? 1 : (b <= 64) ? 2 : (b <= 115) ? 3 : (b <= 204) ? 4 : 5",
        {"b": rain_evt_total.select("EventRain")},
    ).rename("RainSeverity")
    heavy_r = rain_evt_total.gt(100)
    v_heavy_r = rain_evt_total.gt(150)

    return {
        "clipped_study_area": clipped_study_area,
        "evt_era": evt_era,
        "evt_rain": evt_rain,
        "pre_era": pre_era,
        "pre_rain": pre_rain,
        "evt_img": evt_img,
        "pre_img": pre_img,
        "wind_speed": wind_speed,
        "pre_wind": pre_wind,
        "temp_an": temp_an,
        "rh_evt": rh_evt,
        "rain_evt_total": rain_evt_total,
        "rain_sev": rain_sev,
        "heavy_r": heavy_r,
        "v_heavy_r": v_heavy_r,
    }


# ---------------------------------------------------------------------------
# FAST: returns only map tile URLs — no getInfo() → ~5 seconds
# ---------------------------------------------------------------------------

def get_meteorology_layers(cyclone_name: str) -> dict:
    """Returns GEE XYZ tile URLs for all Module-2 layers. Parallelized for speed."""
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    imgs = _build_images(cyclone_name)

    tile_configs = {
        "peakWind": (imgs["wind_speed"], {"min": 0, "max": 30, "palette": "0000FF,00FFFF,00FF00,FFFF00,FFA500,FF0000,800000"}),
        "tempAnomaly": (imgs["temp_an"], {"min": -5, "max": 5, "palette": "00008B,00BFFF,FFFFFF,FFD700,FF0000"}),
        "humidity": (imgs["rh_evt"], {"min": 40, "max": 100, "palette": "8B4513,FFA500,FFFF00,7CFC00,00CED1,0000FF"}),
        "eventRainfall": (imgs["rain_evt_total"], {"min": 0, "max": 300, "palette": "FFFFFF,B3E5FC,4FC3F7,0288D1,01579B,FFFF00,FFA000,FF0000,800000"}),
        "rainSeverity": (imgs["rain_sev"], {"min": 1, "max": 5, "palette": "FFF7EC,A1D99B,FED976,FD8D3C,BD0026"}),
        "heavyRain": (imgs["heavy_r"].selfMask(), {"palette": "FF0000"}),
        "vHeavyRain": (imgs["v_heavy_r"].selfMask(), {"palette": "800000"}),
    }

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _get_tile(name_img_vis):
        name, (img, vis) = name_img_vis
        try:
            mapid = img.getMapId(vis)
            return name, {"tileUrl": mapid["tile_fetcher"].url_format}
        except Exception as e:
            print(f"[M2] {name} getMapId failed: {e}")
            return name, None

    layers = {}
    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = {executor.submit(_get_tile, item): item[0] for item in tile_configs.items()}
        for future in as_completed(futures):
            name, result = future.result()
            if result is not None:
                layers[name] = result

    return {"layers": layers}


# ---------------------------------------------------------------------------
# SLOW: returns stats + time-series — has getInfo() calls → 2-3 minutes
# ---------------------------------------------------------------------------

def get_meteorology_stats(cyclone_name: str) -> dict:
    """Returns area statistics and event time-series. Slow (~2-3 min)."""
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'")

    imgs = _build_images(cyclone_name)
    clipped = imgs["clipped_study_area"]
    evt_img = imgs["evt_img"]
    pre_img = imgs["pre_img"]
    evt_era = imgs["evt_era"]
    evt_rain = imgs["evt_rain"]

    temp = _to_c(evt_img, "temperature_2m").rename("Temp")
    pres = evt_img.select("surface_pressure").divide(100).rename("Pressure")
    rh_evt = imgs["rh_evt"]
    wind_speed = imgs["wind_speed"]
    rain_evt_total = imgs["rain_evt_total"]
    heavy_r = imgs["heavy_r"]
    v_heavy_r = imgs["v_heavy_r"]

    def _reduce(img, band, scale):
        r = ee.Reducer.minMax().combine(reducer2=ee.Reducer.mean(), sharedInputs=True)
        return img.reduceRegion(
            reducer=r, geometry=clipped, scale=scale, maxPixels=1e13, tileScale=16, bestEffort=True
        )

    def _area_km2(mask, scale):
        s = (
            ee.Image.pixelArea()
            .updateMask(mask)
            .reduceRegion(
                reducer=ee.Reducer.sum(), geometry=clipped, scale=scale,
                maxPixels=1e13, tileScale=16, bestEffort=True
            )
        )
        v = s.get("area")
        return ee.Number(ee.Algorithms.If(v, v, 0)).divide(1e6)

    stats = ee.Dictionary({
        "wind_min": _reduce(wind_speed, "WindSpeed", 9000).get("WindSpeed_min"),
        "wind_max": _reduce(wind_speed, "WindSpeed", 9000).get("WindSpeed_max"),
        "wind_mean": _reduce(wind_speed, "WindSpeed", 9000).get("WindSpeed_mean"),
        "temp_min": _reduce(temp, "Temp", 9000).get("Temp_min"),
        "temp_max": _reduce(temp, "Temp", 9000).get("Temp_max"),
        "temp_mean": _reduce(temp, "Temp", 9000).get("Temp_mean"),
        "pres_min": _reduce(pres, "Pressure", 9000).get("Pressure_min"),
        "pres_max": _reduce(pres, "Pressure", 9000).get("Pressure_max"),
        "pres_mean": _reduce(pres, "Pressure", 9000).get("Pressure_mean"),
        "humidity_min": _reduce(rh_evt, "RH", 9000).get("RH_min"),
        "humidity_max": _reduce(rh_evt, "RH", 9000).get("RH_max"),
        "humidity_mean": _reduce(rh_evt, "RH", 9000).get("RH_mean"),
        "mean_rain": rain_evt_total.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=clipped, scale=5500,
            maxPixels=1e13, tileScale=16, bestEffort=True
        ).get("EventRain"),
        "heavy_rain_area_km2": _area_km2(heavy_r, 5500),
        "v_heavy_rain_area_km2": _area_km2(v_heavy_r, 5500),
    }).getInfo()

    # Time-series (sampled at 6-hour intervals for speed)
    def set_hour(img):
        return img.set("hour", ee.Date(img.get("system:time_start")).get("hour"))

    era_sampled = evt_era.map(set_hour).filter(ee.Filter.inList("hour", [0, 6, 12, 18]))

    wind_fc = era_sampled.map(lambda img: ee.Feature(None, {
        "timestamp": img.get("system:time_start"),
        "value": _calc_ws(img).reduceRegion(
            reducer=ee.Reducer.mean(), geometry=clipped,
            scale=20000, maxPixels=1e13, bestEffort=True
        ).get("WindSpeed")
    })).filter(ee.Filter.notNull(["value"]))

    rain_fc = evt_rain.map(lambda img: ee.Feature(None, {
        "timestamp": img.get("system:time_start"),
        "value": img.select("precipitation").reduceRegion(
            reducer=ee.Reducer.mean(), geometry=clipped,
            scale=15000, maxPixels=1e13, bestEffort=True
        ).get("precipitation")
    })).filter(ee.Filter.notNull(["value"]))

    wind_series = [
        {"timestamp": f["properties"]["timestamp"], "value": f["properties"]["value"]}
        for f in wind_fc.getInfo()["features"]
    ]
    rain_series = [
        {"timestamp": f["properties"]["timestamp"], "value": f["properties"]["value"]}
        for f in rain_fc.getInfo()["features"]
    ]

    return {
        "stats": stats,
        "series": {"wind": wind_series, "rain": rain_series},
    }

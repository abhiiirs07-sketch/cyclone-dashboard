import os
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.data.cyclone_db import CYCLONE_DB, CYCLONE_DATES
from app.ee_client import EENotConfiguredError, ensure_initialized
from app.modules import (
    module1_study_area,
    module2_meteorology,
    module3_track,
    module5_flood,
    module6_hazard,
    module7_vegetation,
    module8_lulc,
    module9_population,
    module10_multihazard,
    module11_validation,
    module12_reports,
)

load_dotenv()

app = FastAPI(
    title="Cyclone Intelligence Dashboard API",
    description=(
        "Wraps the GEE cyclone impact-assessment script as JSON + XYZ tile "
        "endpoints. Every number and every tile comes straight from Earth "
        "Engine — nothing here is computed, estimated, or mocked."
    ),
    version="0.1.0",
)

origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Local caching configuration
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cached_response(endpoint: str, cyclone_name: str, compute_func):
    """
    Cache helper for heavy GEE statistic computations.
    Since past cyclone statistics are completely static, we store them forever.
    """
    cache_path = CACHE_DIR / f"{endpoint}_{cyclone_name.lower()}.json"
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    result = compute_func(cyclone_name)

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return result


def get_cached_response_ttl(endpoint: str, cyclone_name: str, compute_func, ttl_seconds: int = 43200):
    """
    Cache helper for GEE layers containing dynamic XYZ tile URLs.
    These MapIDs expire after ~20-24 hours in GEE, so we cache them with a 12-hour TTL.
    """
    cache_path = CACHE_DIR / f"{endpoint}_{cyclone_name.lower()}.json"
    if cache_path.exists():
        try:
            mtime = cache_path.stat().st_mtime
            if time.time() - mtime < ttl_seconds:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass

    result = compute_func(cyclone_name)

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return result


@app.get("/api/health")
def health():
    try:
        ensure_initialized()
        return {"status": "ok", "earthEngine": "connected"}
    except EENotConfiguredError as e:
        return {"status": "degraded", "earthEngine": "not configured", "detail": str(e)}


@app.get("/api/cyclones")
def list_cyclones():
    """Straight from cycloneDB / cycloneDates in your script — no EE call needed."""
    return [
        {"id": name, "label": f"{name} ({info['year']})", **info, "dates": CYCLONE_DATES[name]}
        for name, info in CYCLONE_DB.items()
    ]


@app.get("/api/modules/1/study-area/{cyclone_name}")
def study_area(cyclone_name: str):
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response("study_area", cyclone_name, module1_study_area.get_study_area)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/2/meteorology/{cyclone_name}/layers")
def meteorology_layers(cyclone_name: str):
    """Fast (~5 s): returns GEE XYZ tile URLs for all Module-2 map layers (12-hour TTL cache)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response_ttl("met_layers", cyclone_name, module2_meteorology.get_meteorology_layers)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/2/meteorology/{cyclone_name}/stats")
def meteorology_stats(cyclone_name: str):
    """Slow (~2-3 min): returns area statistics and time-series from GEE (permanently cached)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response("met_stats", cyclone_name, module2_meteorology.get_meteorology_stats)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/3/track/{cyclone_name}/layers")
def track_layers(cyclone_name: str):
    """Fast (~10 s): IBTrACS track GeoJSON + corridor + rainfall tile URLs (12-hour TTL cache)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response_ttl("track_layers", cyclone_name, module3_track.get_track_layers)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/3/track/{cyclone_name}/stats")
def track_stats(cyclone_name: str):
    """Slow (~2-3 min): track statistics + corridor areas + district/state rainfall (permanently cached)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response("track_stats", cyclone_name, module3_track.get_track_stats)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/5/flood/{cyclone_name}/layers")
def flood_layers(cyclone_name: str):
    """Fast (~10-15 s): Sentinel-1 SAR tile URLs — pre/post SAR, diff, flood extent, depth proxy (12-hour TTL)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response_ttl("flood_layers", cyclone_name, module5_flood.get_flood_layers)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/5/flood/{cyclone_name}/stats")
def flood_stats(cyclone_name: str):
    """Slow (~3-5 min): flood area, land cover breakdown, population exposure, district table (permanently cached)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response("flood_stats", cyclone_name, module5_flood.get_flood_stats)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/6/hazard/{cyclone_name}/layers")
def hazard_layers(cyclone_name: str):
    """Fast (~15-20 s): DEM/slope/hillshade/coastal/surge/hazard tile URLs (12-hour TTL cache)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response_ttl("hazard_layers", cyclone_name, module6_hazard.get_hazard_layers)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/6/hazard/{cyclone_name}/stats")
def hazard_stats(cyclone_name: str):
    """Slow (~4-6 min): terrain stats + hazard/surge scores + district ranking (permanently cached)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response("hazard_stats", cyclone_name, module6_hazard.get_hazard_stats)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/7/vegetation/{cyclone_name}/layers")
def veg_layers(cyclone_name: str):
    """Fast (~15 s): Sentinel-2 NDVI pre/post/diff + damage class tile URLs (12-hour TTL cache)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response_ttl("veg_layers", cyclone_name, module7_vegetation.get_veg_layers)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/7/vegetation/{cyclone_name}/stats")
def veg_stats(cyclone_name: str):
    """Slow (~3-4 min): damage class areas + district-level dNDVI stats (permanently cached)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response("veg_stats", cyclone_name, module7_vegetation.get_veg_stats)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/8/lulc/{cyclone_name}/layers")
def lulc_layers(cyclone_name: str):
    """Fast (~15 s): ESA WorldCover + impact-type + flooded/damaged LULC tile URLs (12-hour TTL cache)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response_ttl("lulc_layers", cyclone_name, module8_lulc.get_lulc_layers)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/8/lulc/{cyclone_name}/stats")
def lulc_stats(cyclone_name: str):
    """Slow (~4-5 min): per-class flood/veg-damage areas + district LULC impact scores (permanently cached)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response("lulc_stats", cyclone_name, module8_lulc.get_lulc_stats)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/9/population/{cyclone_name}/layers")
def pop_layers(cyclone_name: str):
    """Fast (~15 s): GPW population count/density + exposure layer tile URLs (12-hour TTL cache)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response_ttl("pop_layers", cyclone_name, module9_population.get_pop_layers)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/9/population/{cyclone_name}/stats")
def pop_stats(cyclone_name: str):
    """Slow (~4-5 min): total/flooded/high-haz population counts + district table (permanently cached)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response("pop_stats", cyclone_name, module9_population.get_pop_stats)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/10/multihazard/{cyclone_name}/layers")
def multihazard_layers(cyclone_name: str):
    """Fast (~15 s): composite multi-hazard index + component risk layer tile URLs (12-hour TTL cache)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response_ttl("mh_layers", cyclone_name, module10_multihazard.get_multihazard_layers)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/10/multihazard/{cyclone_name}/stats")
def multihazard_stats(cyclone_name: str):
    """Slow (~5 min): class area breakdown + district risk ranking (top 20) (permanently cached)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response("mh_stats", cyclone_name, module10_multihazard.get_multihazard_stats)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/11/validation/{cyclone_name}/layers")
def validation_layers(cyclone_name: str):
    """Fast (~20 s): SAR vs optical confusion map + Landsat dNDVI + veg agreement tile URLs (12-hour TTL cache)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response_ttl("val_layers", cyclone_name, module11_validation.get_validation_layers)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/11/validation/{cyclone_name}/stats")
def validation_stats(cyclone_name: str):
    """Slow (~5-6 min): flood accuracy metrics (precision/recall/F1/OA/IoU) + district table (permanently cached)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response("val_stats", cyclone_name, module11_validation.get_validation_stats)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/12/reports/{cyclone_name}/summary")
def report_summary(cyclone_name: str):
    """Fast (~5-10 s): JSON summary report aggregating all module stats (permanently cached)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response("report_summary", cyclone_name, module12_reports.get_report_summary)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/modules/12/reports/{cyclone_name}/export")
def report_export(cyclone_name: str):
    """Slow (~2-3 min): district-level CSV with hazard, flood, and population metrics (permanently cached)."""
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        return get_cached_response("report_export", cyclone_name, module12_reports.get_export_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

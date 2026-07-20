import os
import json
import time
import threading
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
    version="0.3.0",
)

# Public dashboard — allow requests from any origin (Netlify, mobile, etc.)
# No sensitive user data or auth here, so open CORS is safe.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "DELETE"],
    allow_headers=["*"],
)


# Local caching configuration
CACHE_DIR = Path(__file__).parent / "cache_v2"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Layer caches expire after 1.5 hours (GEE MapIDs typically expire in ~2 hours)
LAYER_TTL = int(1.5 * 3600)

# Track which endpoints are currently being computed (to avoid duplicate work)
_computing = {}
_computing_lock = threading.Lock()


def _cache_path(endpoint: str, cyclone_name: str) -> Path:
    return CACHE_DIR / f"{endpoint}_{cyclone_name.lower()}.json"


def get_cached_response(endpoint: str, cyclone_name: str, compute_func):
    """
    Permanent cache for slow statistics (past cyclones never change).
    Clears cache and retries once if a cached error is detected.
    """
    path = _cache_path(endpoint, cyclone_name)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Don't serve cached error responses
            if isinstance(data, dict) and data.get("error"):
                path.unlink(missing_ok=True)
            else:
                return data
        except Exception:
            path.unlink(missing_ok=True)

    result = compute_func(cyclone_name)

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return result


def get_cached_response_ttl(endpoint: str, cyclone_name: str, compute_func,
                             ttl_seconds: int = LAYER_TTL):
    """
    TTL cache for fast layer responses (GEE tile URLs expire ~24h).
    Clears cache if stale or if a cached error is detected.
    """
    path = _cache_path(endpoint, cyclone_name)
    if path.exists():
        try:
            mtime = path.stat().st_mtime
            if time.time() - mtime < ttl_seconds:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Don't serve cached error responses
                if isinstance(data, dict) and data.get("error"):
                    path.unlink(missing_ok=True)
                else:
                    return data
            else:
                path.unlink(missing_ok=True)
        except Exception:
            path.unlink(missing_ok=True)

    result = compute_func(cyclone_name)

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return result


def _safe_run(endpoint: str, cyclone_name: str, compute_func, use_ttl: bool = False):
    """
    Wraps a module call with EE init check + comprehensive error handling.
    Returns an HTTP 200 with error details rather than crashing, so the
    frontend can show a graceful error rather than a spinner forever.
    """
    try:
        ensure_initialized()
    except EENotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    try:
        if use_ttl:
            return get_cached_response_ttl(endpoint, cyclone_name, compute_func)
        return get_cached_response(endpoint, cyclone_name, compute_func)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        # Log the real error but return a structured 500 with details
        import traceback
        tb = traceback.format_exc()
        print(f"[ERROR] {endpoint}/{cyclone_name}: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e


def _warmup_layers(cyclone_name: str):
    """
    Pre-compute and cache all layer endpoints for a cyclone.
    Runs in a background thread at startup.
    """
    fast_endpoints = [
        ("study_area",  module1_study_area.get_study_area,       False),
        ("met_layers",  module2_meteorology.get_meteorology_layers, True),
        ("track_layers",module3_track.get_track_layers,           True),
        ("flood_layers", module5_flood.get_flood_layers,          True),
        ("hazard_layers",module6_hazard.get_hazard_layers,        True),
        ("veg_layers",  module7_vegetation.get_veg_layers,        True),
        ("lulc_layers", module8_lulc.get_lulc_layers,             True),
        ("pop_layers",  module9_population.get_pop_layers,        True),
        ("mh_layers",   module10_multihazard.get_multihazard_layers, True),
        ("val_layers",  module11_validation.get_validation_layers,   True),
    ]

    for endpoint, func, use_ttl in fast_endpoints:
        path = _cache_path(endpoint, cyclone_name)
        # Skip if already freshly cached
        if path.exists():
            try:
                mtime = path.stat().st_mtime
                age = time.time() - mtime
                if not use_ttl or age < LAYER_TTL:
                    print(f"[WARMUP] {endpoint}/{cyclone_name}: already cached (age {age:.0f}s)")
                    continue
            except Exception:
                pass
        try:
            print(f"[WARMUP] Computing {endpoint}/{cyclone_name}...")
            t0 = time.time()
            if use_ttl:
                get_cached_response_ttl(endpoint, cyclone_name, func)
            else:
                get_cached_response(endpoint, cyclone_name, func)
            print(f"[WARMUP] {endpoint}/{cyclone_name} done in {time.time()-t0:.1f}s")
        except Exception as e:
            print(f"[WARMUP] {endpoint}/{cyclone_name} failed: {e}")


def _run_warmup():
    """Background thread that pre-warms all cyclone layer caches on startup."""
    try:
        print("[WARMUP] Waiting 5s for EE initialization...")
        time.sleep(5)
        ensure_initialized()
        print("[WARMUP] EE ready. Starting cache warmup for all cyclones...")
        # Fani first (most common/default), then others
        priority = ["Fani", "Amphan", "Yaas", "Phailin", "Hudhud", "Biparjoy", "Michaung", "Mocha"]
        for name in priority:
            if name in CYCLONE_DB:
                _warmup_layers(name)
        print("[WARMUP] All cyclones warmed up!")
    except Exception as e:
        print(f"[WARMUP] Background warmup failed: {e}")


# ---------------------------------------------------------------------------
# Health & metadata
# ---------------------------------------------------------------------------

@app.get("/api/ping")
def ping():
    """Ultra-lightweight keep-alive endpoint — no EE call needed."""
    return {"pong": True}


@app.get("/api/health")
def health():
    try:
        ensure_initialized()
        return {"status": "ok", "earthEngine": "connected"}
    except EENotConfiguredError as e:
        return {"status": "degraded", "earthEngine": "not configured", "detail": str(e)}


@app.get("/api/test-gee")
def test_gee():
    try:
        ensure_initialized()
        import ee
        res = ee.Image(1).getInfo()
        return {"status": "success", "info": res}
    except Exception as e:
        import traceback
        return {"status": "error", "exception": str(e), "traceback": traceback.format_exc()}


@app.get("/api/warmup-status")
def warmup_status():
    """Check which cyclone caches are ready."""
    status = {}
    for cyclone in CYCLONE_DB:
        endpoints = ["study_area", "met_layers", "track_layers", "flood_layers",
                     "hazard_layers", "veg_layers", "lulc_layers", "pop_layers",
                     "mh_layers", "val_layers"]
        ready = []
        missing = []
        for ep in endpoints:
            path = _cache_path(ep, cyclone)
            if path.exists():
                age = time.time() - path.stat().st_mtime
                ready.append(f"{ep} ({age:.0f}s ago)")
            else:
                missing.append(ep)
        status[cyclone] = {"ready": len(ready), "missing": missing}
    return status


@app.on_event("startup")
async def startup_event():
    """Launch background warmup thread when the server starts."""
    t = threading.Thread(target=_run_warmup, daemon=True)
    t.start()
    print("[STARTUP] Background warmup thread started.")


@app.get("/api/cyclones")
def list_cyclones():
    return [
        {"id": name, "label": f"{name} ({info['year']})", **info, "dates": CYCLONE_DATES[name]}
        for name, info in CYCLONE_DB.items()
    ]


@app.delete("/api/cache/{cyclone_name}")
def clear_cache(cyclone_name: str):
    """Clear all cached responses for a cyclone (forces fresh GEE computation)."""
    deleted = []
    for path in CACHE_DIR.glob(f"*_{cyclone_name.lower()}.json"):
        path.unlink(missing_ok=True)
        deleted.append(path.name)
    return {"deleted": deleted, "count": len(deleted)}


@app.delete("/api/cache")
def clear_all_cache():
    """Clear ALL cached responses (forces fresh GEE computation for everything)."""
    deleted = []
    for path in CACHE_DIR.glob("*.json"):
        path.unlink(missing_ok=True)
        deleted.append(path.name)
    return {"deleted": deleted, "count": len(deleted)}


# ---------------------------------------------------------------------------
# Module 1 — Study Area
# ---------------------------------------------------------------------------

@app.get("/api/modules/1/study-area/{cyclone_name}")
def study_area(cyclone_name: str):
    return _safe_run("study_area", cyclone_name, module1_study_area.get_study_area)


# ---------------------------------------------------------------------------
# Module 2 — Meteorology
# ---------------------------------------------------------------------------

@app.get("/api/modules/2/meteorology/{cyclone_name}/layers")
def meteorology_layers(cyclone_name: str):
    return _safe_run("met_layers", cyclone_name, module2_meteorology.get_meteorology_layers, use_ttl=True)


@app.get("/api/modules/2/meteorology/{cyclone_name}/stats")
def meteorology_stats(cyclone_name: str):
    return _safe_run("met_stats", cyclone_name, module2_meteorology.get_meteorology_stats)


# ---------------------------------------------------------------------------
# Module 3 — Cyclone Track
# ---------------------------------------------------------------------------

@app.get("/api/modules/3/track/{cyclone_name}/layers")
def track_layers(cyclone_name: str):
    return _safe_run("track_layers", cyclone_name, module3_track.get_track_layers, use_ttl=True)


@app.get("/api/modules/3/track/{cyclone_name}/stats")
def track_stats(cyclone_name: str):
    return _safe_run("track_stats", cyclone_name, module3_track.get_track_stats)


# ---------------------------------------------------------------------------
# Module 5 — Flood Mapping
# ---------------------------------------------------------------------------

@app.get("/api/modules/5/flood/{cyclone_name}/layers")
def flood_layers(cyclone_name: str):
    return _safe_run("flood_layers", cyclone_name, module5_flood.get_flood_layers, use_ttl=True)


@app.get("/api/modules/5/flood/{cyclone_name}/stats")
def flood_stats(cyclone_name: str):
    return _safe_run("flood_stats", cyclone_name, module5_flood.get_flood_stats)


# ---------------------------------------------------------------------------
# Module 6 — Terrain, Storm Surge & Hazard
# ---------------------------------------------------------------------------

@app.get("/api/modules/6/hazard/{cyclone_name}/layers")
def hazard_layers(cyclone_name: str):
    return _safe_run("hazard_layers", cyclone_name, module6_hazard.get_hazard_layers, use_ttl=True)


@app.get("/api/modules/6/hazard/{cyclone_name}/stats")
def hazard_stats(cyclone_name: str):
    return _safe_run("hazard_stats", cyclone_name, module6_hazard.get_hazard_stats)


# ---------------------------------------------------------------------------
# Module 7 — Vegetation Damage
# ---------------------------------------------------------------------------

@app.get("/api/modules/7/vegetation/{cyclone_name}/layers")
def veg_layers(cyclone_name: str):
    return _safe_run("veg_layers", cyclone_name, module7_vegetation.get_veg_layers, use_ttl=True)


@app.get("/api/modules/7/vegetation/{cyclone_name}/stats")
def veg_stats(cyclone_name: str):
    return _safe_run("veg_stats", cyclone_name, module7_vegetation.get_veg_stats)


# ---------------------------------------------------------------------------
# Module 8 — LULC Impact
# ---------------------------------------------------------------------------

@app.get("/api/modules/8/lulc/{cyclone_name}/layers")
def lulc_layers(cyclone_name: str):
    return _safe_run("lulc_layers", cyclone_name, module8_lulc.get_lulc_layers, use_ttl=True)


@app.get("/api/modules/8/lulc/{cyclone_name}/stats")
def lulc_stats(cyclone_name: str):
    return _safe_run("lulc_stats", cyclone_name, module8_lulc.get_lulc_stats)


# ---------------------------------------------------------------------------
# Module 9 — Population Exposure
# ---------------------------------------------------------------------------

@app.get("/api/modules/9/population/{cyclone_name}/layers")
def pop_layers(cyclone_name: str):
    return _safe_run("pop_layers", cyclone_name, module9_population.get_pop_layers, use_ttl=True)


@app.get("/api/modules/9/population/{cyclone_name}/stats")
def pop_stats(cyclone_name: str):
    return _safe_run("pop_stats", cyclone_name, module9_population.get_pop_stats)


# ---------------------------------------------------------------------------
# Module 10 — Multi-Hazard Summary
# ---------------------------------------------------------------------------

@app.get("/api/modules/10/multihazard/{cyclone_name}/layers")
def multihazard_layers(cyclone_name: str):
    return _safe_run("mh_layers", cyclone_name, module10_multihazard.get_multihazard_layers, use_ttl=True)


@app.get("/api/modules/10/multihazard/{cyclone_name}/stats")
def multihazard_stats(cyclone_name: str):
    return _safe_run("mh_stats", cyclone_name, module10_multihazard.get_multihazard_stats)


# ---------------------------------------------------------------------------
# Module 11 — Validation
# ---------------------------------------------------------------------------

@app.get("/api/modules/11/validation/{cyclone_name}/layers")
def validation_layers(cyclone_name: str):
    return _safe_run("val_layers", cyclone_name, module11_validation.get_validation_layers, use_ttl=True)


@app.get("/api/modules/11/validation/{cyclone_name}/stats")
def validation_stats(cyclone_name: str):
    return _safe_run("val_stats", cyclone_name, module11_validation.get_validation_stats)


# ---------------------------------------------------------------------------
# Module 12 — Reports & Export
# ---------------------------------------------------------------------------

@app.get("/api/modules/12/reports/{cyclone_name}/summary")
def report_summary(cyclone_name: str):
    return _safe_run("report_summary", cyclone_name, module12_reports.get_report_summary)


@app.get("/api/modules/12/reports/{cyclone_name}/export")
def report_export(cyclone_name: str):
    return _safe_run("report_export", cyclone_name, module12_reports.get_export_data)

# Cyclone Intelligence Dashboard — backend

FastAPI service that wraps your Earth Engine cyclone-assessment script and
exposes it as JSON + XYZ tile endpoints for the Next.js frontend. Nothing
here recomputes or approximates your analysis — every endpoint runs the
same `ee.*` operations your GEE script does, translated 1:1 into the Python
Earth Engine API, then hands back whatever Earth Engine actually returns.

## Status

- Module 1 — Study Area: fully wired → `GET /api/modules/1/study-area/{cyclone}`
- Modules 2–12: not built yet (see the root README for the full roadmap)

## 1. Connect your Earth Engine account

The backend authenticates as a **service account** (not your personal
Google login) — the standard pattern for a server calling Earth Engine on
its own, without a human signing in interactively.

1. In the [Google Cloud Console](https://console.cloud.google.com/), pick
   or create a project, then enable the **Earth Engine API** for it.
2. If that project hasn't been used with Earth Engine before, register it
   at https://code.earthengine.google.com/register — skip this if it's
   already the project behind your Code Editor account.
3. Create a service account (IAM & Admin → Service Accounts), grant it the
   **Earth Engine Resource Viewer** role, and download a JSON key.
4. `cp .env.example .env` and fill in:
   - `EE_SERVICE_ACCOUNT` — the service account's email
   - `EE_PRIVATE_KEY_FILE` — path to the JSON key you downloaded
   - `EE_PROJECT` — your GCP project ID

## 2. Run it

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Visit http://localhost:8000/api/health — it should report
`"earthEngine": "connected"`. If it says "not configured", double-check
the `.env` values from step 1.

## 3. Verify Module 1 against your Code Editor

```bash
curl http://localhost:8000/api/modules/1/study-area/Fani
```

Compare `studyArea_km2`, `reportingArea_km2` and `districtCount` against
what Module 1 prints in your Code Editor console for the same cyclone.
They should match closely — small differences from `bestEffort`/`tileScale`
choices are expected; anything larger means the translation needs a look,
and I'd want to know before we build Module 2 on top of it.

## A note on your script

Your script calls `Map.addLayer` for India / Landfall / Affected Districts
/ Study Area **twice** — once in Module 1's own "MAP" section, once again
in section 6 "MAP SETUP" — with different colors/widths the second time,
and section 6 also adds the States/Districts boundary outlines that aren't
in the first block. `app/modules/module1_study_area.py` uses section 6's
version, since it runs later and is the only block that defines the
boundary layers at all. If that's not the one you meant to keep, it's a
one-line change in `_rasterize_layers()`.

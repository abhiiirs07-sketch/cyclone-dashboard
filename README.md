# Cyclone Intelligence & Impact Assessment Dashboard

Google Earth Engine powered disaster monitoring system — a Next.js frontend
over a FastAPI backend that translates your GEE script into the Python
Earth Engine API, module by module. Every number and every map tile is
produced by calling Earth Engine directly; nothing in this codebase mocks,
estimates, or hardcodes a scientific value.

## Quick start

```bash
# backend
cd backend
python -m venv venv && source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env        # then fill in your GEE service account — see backend/README.md
uvicorn app.main:app --reload --port 8000

# frontend, in a second terminal
cd frontend
npm install
npm run dev                 # http://localhost:3000
```

Until `.env` has real Earth Engine credentials, the app runs and the UI
loads fully — the map shows a "waiting for Earth Engine layers" state and
the header shows "Earth Engine not connected" instead of any invented
numbers. That's deliberate: see backend/README.md to connect it for real.

## What's actually live right now

- **Module 1 — Study area**: backend endpoint, real tiles, real stats,
  wired end-to-end into the map, both sidebars, and the layer toggles.
- **Frontend shell**: header, both sidebars, map, bottom panel — laid out
  per the spec, dark theme, glassmorphism, with honest "not wired yet"
  states everywhere a module hasn't been built, instead of placeholder data.
- **Cyclone selector, event-window display, affected-district list**: all
  pulled from your real `cycloneDB` / `cycloneDates` and Module 1's real
  `reduceRegion` output — none of it is sample data.

## Roadmap — modules 2 through 12

Same pattern each time: translate the module's `ee.*` calls into
`backend/app/modules/moduleN_*.py` 1:1, verify its numbers against your
Code Editor console, add a FastAPI route, then wire the frontend panel
that consumes it.

| # | Module | Notes |
|---|--------|-------|
| 1 | Study area | ✅ done this pass |
| 2 | Meteorology (wind/pressure/humidity/temp/rainfall) | straightforward — mirrors Module 1's pattern |
| 3 | Cyclone track (IBTrACS) | vector-only, low risk; unlocks the header's animated track + timeline |
| 4 | Rainfall footprint | depends on Module 2's CHIRPS pull |
| 5 | Flood mapping (SAR) | most complex piece — adaptive threshold, Lee filter, orbit-matching logic. Needs careful line-by-line verification given how much this module changed v3→v4 in your script |
| 6 | Storm surge & composite hazard | second most complex — vector-based coastal distance, percentile classification. Also heavily revised v3→v4 |
| 7 | Vegetation damage | see note below — your script never calls `Map.addLayer` for this module's outputs |
| 8 | LULC impact | reuses Module 5's flood mask, should be quick once 5 is solid |
| 9 | Population exposure | reuses Module 6's `hazardIndex` |
| 10 | Multi-hazard impact index | composite of 2, 5, 6, 7, 9 — build last among the analysis modules |
| 11 | Validation | sampled stats, low risk |
| 12 | Reports & export | PDF/CSV/GeoJSON/TIFF export, depends on everything above |

I'd suggest going in roughly this order — 2 and 3 are quick wins that make
the header/timeline feel real, 5 and 6 need the most care, and 12 only
makes sense once there's something to export. Happy to jump around if you
have a demo deadline that needs a specific module first.

## Two things I noticed while translating Module 1

1. **Duplicate `Map.addLayer` calls.** Your script adds India / Landfall /
   Affected Districts / Study Area to the map twice — once in Module 1's
   own "MAP" section, once again in section 6 "MAP SETUP" — with different
   colors and widths the second time. I used section 6's version as
   canonical (it runs later and is the only block that also defines the
   States/Districts boundary layers). Flagging in case that wasn't
   intentional — it's a one-line fix in `module1_study_area.py` if you want
   the first block's styling instead.

2. **Module 7 (Vegetation Damage) has no map visualization at all** —
   `damageClass`, `dNDVI`, `preNDVI`, `postNDVI` are all computed and fed
   into tables/stats, but none of them ever hits `Map.addLayer` in your
   script. When we get to Module 7, I'll need you to either point me to
   the vis params you want (e.g. a diverging palette for dNDVI, categorical
   colors for DamageClass) or confirm you're fine with me proposing
   reasonable ones — didn't want to invent colors for a layer you never
   specified without checking first.

## Stack notes

- Deck.GL is in your original spec but isn't used yet — Module 1's layers
  are simple polygons/points/rasters that MapLibre handles natively. I'll
  bring in Deck.GL for Module 2/3's animated track and wind-field
  rendering, where its GPU-accelerated overlays actually add something.
- shadcn/ui components aren't scaffolded yet (the CLI is interactive and
  didn't fit a first automated pass) — current components use Tailwind +
  the same visual language shadcn uses, so migrating individual components
  over later is straightforward.
- `frontend/lib/gee-palettes.ts` has every `Map.addLayer` palette from your
  script transcribed already, ready for Modules 2–6 to use without
  re-deriving them.

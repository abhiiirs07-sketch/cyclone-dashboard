"""
Direct translation of MODULE 1 : STUDY AREA from the source .js script.

Every ee.* call below has a 1:1 counterpart in the original JavaScript —
same collections, same filters, same reducers, same scale (100 m for the
area reducers, matching `.area(100)` in the source). Only the syntax
changed (JS -> Python Earth Engine API); no calculation was altered.

Source correspondence:
  countries/states/districts filters   -> section 5, "ADMINISTRATIVE BOUNDARIES"
  landfall / studyBuffer                -> "LANDFALL LOCATION" / "PRIMARY STUDY BUFFER"
  affectedDistricts / clippedStudyArea  -> "AFFECTED DISTRICTS" / "STUDY AREA"
  reportingArea                         -> "REPORTING AREA"
  studyAreaKm2 / reportingAreaKm2 / ... -> "STATISTICS"
"""

import ee

from app.data.cyclone_db import CYCLONE_DB, STUDY_BUFFER_KM

# Keys must match what the frontend's StudyAreaResponse['layers'] expects.
_LAYER_KEYS = ("india", "landfall", "affectedDistricts", "studyArea", "reportingArea", "states", "districts")


def get_study_area(cyclone_name: str) -> dict:
    if cyclone_name not in CYCLONE_DB:
        raise ValueError(f"Unknown cyclone '{cyclone_name}'. Available: {', '.join(CYCLONE_DB)}")
    cyclone = CYCLONE_DB[cyclone_name]

    # ---- administrative boundaries (FAO/GAUL/2015) ----
    countries = ee.FeatureCollection("FAO/GAUL/2015/level0")
    states = ee.FeatureCollection("FAO/GAUL/2015/level1")
    districts = ee.FeatureCollection("FAO/GAUL/2015/level2")

    india = countries.filter(ee.Filter.eq("ADM0_NAME", "India"))
    india_states = states.filter(ee.Filter.eq("ADM0_NAME", "India"))
    india_districts = districts.filter(ee.Filter.eq("ADM0_NAME", "India"))

    # ---- landfall location + study buffer ----
    landfall = ee.Geometry.Point([cyclone["lon"], cyclone["lat"]])
    study_buffer = landfall.buffer(STUDY_BUFFER_KM * 1000)

    # ---- affected districts / study area / reporting area ----
    affected_districts = india_districts.filterBounds(study_buffer)
    clipped_study_area = study_buffer.intersection(india.geometry(), ee.ErrorMargin(100))
    reporting_area = affected_districts.geometry().dissolve()

    # ---- statistics (identical reducers & scale to the source script) ----
    study_area_km2 = ee.Number(clipped_study_area.area(100)).divide(1e6)
    reporting_area_km2 = ee.Number(reporting_area.area(100)).divide(1e6)
    district_names = affected_districts.aggregate_array("ADM2_NAME")
    state_names = affected_districts.aggregate_array("ADM1_NAME").distinct()

    # One combined getInfo() = one server round trip instead of five.
    stats = ee.Dictionary({
        "studyArea_km2": study_area_km2,
        "reportingArea_km2": reporting_area_km2,
        "districtCount": affected_districts.size(),
        "districtNames": district_names,
        "stateNames": state_names,
    }).getInfo()

    stats.update({
        "cyclone": cyclone_name,
        "landfall": cyclone["landfall"],
        "landfallDate": cyclone["date"],
        "landfallLon": cyclone["lon"],
        "landfallLat": cyclone["lat"],
    })

    layers = _rasterize_layers(
        india=india,
        india_states=india_states,
        india_districts=india_districts,
        reporting_area=reporting_area,
        clipped_study_area=clipped_study_area,
        affected_districts=affected_districts,
        landfall=landfall,
    )

    return {"stats": stats, "layers": layers}


def _rasterize_layers(*, india, india_states, india_districts, reporting_area,
                       clipped_study_area, affected_districts, landfall) -> dict:
    """
    Converts each vector layer into a rendered Image so it can be served as
    XYZ tiles via getMapId(). The Code Editor does this "vector -> styled
    raster" conversion invisibly whenever you call Map.addLayer on a
    FeatureCollection or Geometry; the REST/Python getMapId() endpoint only
    accepts Images, so it's made explicit here.

    NOTE ON YOUR SCRIPT: Module 1 calls Map.addLayer for India / Landfall /
    Affected Districts / Study Area TWICE — once in Module 1's own "MAP"
    section, once again in section 6 "MAP SETUP" — with different colors
    and widths the second time, and section 6 also adds the States/
    Districts boundary outlines that the first block doesn't have. I used
    section 6's styling below since it runs later (so it's what would
    visually sit on top) and it's the only block that defines the States/
    Districts layers at all. If you intended the FIRST block's styling to
    be canonical instead, it's a one-line change to each `.style(...)` call
    below — happy to swap it.
    """
    def outline_fill(fc, color, fill_color="00000000", width=1):
        return fc.style(color=color, fillColor=fill_color, width=width).getMapId({})

    tiles = {
        "india": outline_fill(india, "000000", width=1),
        "landfall": ee.FeatureCollection([ee.Feature(landfall)])
            .style(color="FFFF00", pointSize=8).getMapId({}),
        "affectedDistricts": outline_fill(affected_districts, "FFFF00", "FFFF0033", 2),
        "studyArea": outline_fill(
            ee.FeatureCollection([ee.Feature(clipped_study_area)]), "00FFFF", "00FFFF33", 2
        ),
        "reportingArea": outline_fill(
            ee.FeatureCollection([ee.Feature(reporting_area)]), "FFFF00", width=2
        ),
        "states": outline_fill(india_states, "666666", width=1),
        "districts": outline_fill(india_districts, "999999", width=0.5),
    }

    assert set(tiles) == set(_LAYER_KEYS), "layer keys drifted from the frontend contract"

    return {name: {"tileUrl": mapid["tile_fetcher"].url_format} for name, mapid in tiles.items()}

"""
Cyclone reference data — a direct transcription of `cycloneDB`, `cycloneDates`
and `studyBufferKm` from the top of the GEE script (Module 1 / Configuration).

If you change these values in the .js source, mirror the change here — this
file is not derived automatically, it's a manual 1:1 copy.
"""

from typing import TypedDict


class CycloneInfo(TypedDict):
    year: int
    landfall: str
    state: str
    country: str
    date: str
    lon: float
    lat: float
    affectedStates: list[str]


class CycloneDates(TypedDict):
    preS: str
    preE: str
    evtS: str
    evtE: str
    postS: str
    postE: str


STUDY_BUFFER_KM = 250

CYCLONE_DB: dict[str, CycloneInfo] = {
    "Fani": {
        "year": 2019, "landfall": "Puri", "state": "Odisha", "country": "India",
        "date": "2019-05-03", "lon": 85.86, "lat": 19.81,
        "affectedStates": ["Odisha", "West Bengal"],
    },
    "Amphan": {
        "year": 2020, "landfall": "South 24 Parganas", "state": "West Bengal", "country": "India",
        "date": "2020-05-20", "lon": 88.30, "lat": 21.65,
        "affectedStates": ["West Bengal", "Odisha"],
    },
    "Yaas": {
        "year": 2021, "landfall": "Balasore", "state": "Odisha", "country": "India",
        "date": "2021-05-26", "lon": 86.95, "lat": 21.60,
        "affectedStates": ["Odisha", "West Bengal"],
    },
    "Phailin": {
        "year": 2013, "landfall": "Gopalpur", "state": "Odisha", "country": "India",
        "date": "2013-10-12", "lon": 84.92, "lat": 19.27,
        "affectedStates": ["Odisha", "Andhra Pradesh"],
    },
    "Hudhud": {
        "year": 2014, "landfall": "Visakhapatnam", "state": "Andhra Pradesh", "country": "India",
        "date": "2014-10-12", "lon": 83.30, "lat": 17.70,
        "affectedStates": ["Andhra Pradesh", "Odisha"],
    },
    "Biparjoy": {
        "year": 2023, "landfall": "Kutch", "state": "Gujarat", "country": "India",
        "date": "2023-06-15", "lon": 69.90, "lat": 23.30,
        "affectedStates": ["Gujarat", "Rajasthan"],
    },
    "Michaung": {
        "year": 2023, "landfall": "Bapatla", "state": "Andhra Pradesh", "country": "India",
        "date": "2023-12-05", "lon": 80.46, "lat": 15.90,
        "affectedStates": ["Andhra Pradesh", "Tamil Nadu"],
    },
    "Mocha": {
        "year": 2023, "landfall": "Myanmar Coast", "state": "Bay of Bengal", "country": "Myanmar",
        "date": "2023-05-14", "lon": 93.70, "lat": 20.85,
        "affectedStates": ["Andaman and Nicobar Islands"],
    },
}

CYCLONE_DATES: dict[str, CycloneDates] = {
    "Fani":     {"preS": "2019-04-28", "preE": "2019-05-01", "evtS": "2019-05-02", "evtE": "2019-05-04", "postS": "2019-05-05", "postE": "2019-05-08"},
    "Amphan":   {"preS": "2020-05-15", "preE": "2020-05-18", "evtS": "2020-05-19", "evtE": "2020-05-21", "postS": "2020-05-22", "postE": "2020-05-25"},
    "Yaas":     {"preS": "2021-05-22", "preE": "2021-05-24", "evtS": "2021-05-25", "evtE": "2021-05-27", "postS": "2021-05-28", "postE": "2021-05-31"},
    "Phailin":  {"preS": "2013-10-08", "preE": "2013-10-10", "evtS": "2013-10-11", "evtE": "2013-10-13", "postS": "2013-10-14", "postE": "2013-10-17"},
    "Hudhud":   {"preS": "2014-10-08", "preE": "2014-10-10", "evtS": "2014-10-11", "evtE": "2014-10-13", "postS": "2014-10-14", "postE": "2014-10-17"},
    "Biparjoy": {"preS": "2023-06-11", "preE": "2023-06-13", "evtS": "2023-06-14", "evtE": "2023-06-16", "postS": "2023-06-17", "postE": "2023-06-20"},
    "Michaung": {"preS": "2023-12-02", "preE": "2023-12-04", "evtS": "2023-12-05", "evtE": "2023-12-06", "postS": "2023-12-07", "postE": "2023-12-10"},
    "Mocha":    {"preS": "2023-05-10", "preE": "2023-05-12", "evtS": "2023-05-13", "evtE": "2023-05-15", "postS": "2023-05-16", "postE": "2023-05-19"},
}


CYCLONE_GEE_LOOKUP = {
    "Fani": {
        "rain_p95": 132.44930122706515,
        "pop_p95": 6.853883792797915,
        "rain_max": 161.99796295166016
    },
    "Amphan": {
        "rain_p95": 115.500371277184,
        "pop_p95": 19.174132686963755,
        "rain_max": 172.9465390443802
    },
    "Yaas": {
        "rain_p95": 150.4449694056296,
        "pop_p95": 19.233813813071368,
        "rain_max": 184.33577728271484
    },
    "Phailin": {
        "rain_p95": 162.5272380371797,
        "pop_p95": 6.86157032118685,
        "rain_max": 202.79176712036133
    },
    "Hudhud": {
        "rain_p95": 122.29836859865371,
        "pop_p95": 6.8851373531844535,
        "rain_max": 152.0191707611084
    },
    "Biparjoy": {
        "rain_p95": 81.7986553311348,
        "pop_p95": 4.450093452803309,
        "rain_max": 105.30830383300781
    },
    "Michaung": {
        "rain_p95": 22.596885002146887,
        "pop_p95": 8.91344739708401,
        "rain_max": 38.46523094177246
    },
    "Mocha": {
        "rain_p95": 126.28612918730997,
        "pop_p95": 1.1816922499867355,
        "rain_max": 149.29242324829102
    }
}


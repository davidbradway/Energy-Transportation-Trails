# ETT — Energy Transportation Trails

A Leaflet + OpenStreetMap web map, named in the spirit of Durham's American Tobacco Trail (ATT),
that overlays Duke Energy transmission easements on Durham's existing and planned bike/hike
network to show where trails could be built along utility corridors.

Replaces the earlier ArcGIS web map:
https://www.arcgis.com/apps/mapviewer/index.html?webmap=b447aef212cb42c7a365b0ea9184b33f

## Scope

- **Area:** Durham County, plus a 1-mile buffer so corridors that cross the county line and
  connect back in are kept.
- **Hosting:** GitHub Pages from `/docs`; custom domain optional later (add `docs/CNAME`).

## Data

| Layer | Source | Notes |
|---|---|---|
| Duke Transmission Easements | NC OneMap (`6c9a740f143b49f5bfcffe59c082b1c2_0`) | Statewide polygons, Electric + Gas. Clipped spatially (County field is blank on ~half) |
| Existing and Proposed Trails | Durham Open Data | `STATUS` = Existing / Proposed |
| Existing Greenways | Durham Open Data | |
| Existing Bike Facilities | Durham Open Data | |
| Future Bike Facilities | Durham Open Data | |
| Durham County boundary | Census TIGERweb (GEOID 37063) | Fetched and cached by `build.py` |

All local GeoJSON is already WGS84 (CRS84), which Leaflet uses directly. Downloads date from Jan 2023.

## Layout

```
ETT/
├── PLAN.md
├── build.py              # data pipeline: raw GeoJSON -> docs/data/
├── requirements.txt
├── *.geojson, *.csv ...  # raw source data (git-ignored)
└── docs/                 # served by GitHub Pages
    ├── index.html
    ├── app.js
    ├── style.css
    └── data/*.geojson
```

## Steps

1. **Base map** — `build.py` clips easements to Durham + buffer, simplifies geometry, trims
   attributes, and writes compact GeoJSON. Leaflet page shows all layers with a layer toggle,
   legend, popups, and OSM / satellite basemaps.
2. **Corridors + feasibility** — dissolve touching easement parcels into corridors (Electric and
   Gas separately); score each 0–100 on:
   - service type (Electric > Gas, since paving over gas lines may be restricted)
   - estimated width (area ÷ length) vs. a 12 ft trail, which Duke Energy now allows
   - connectivity: endpoints within ~500 ft of existing trails/greenways/bike lanes; bonus for
     linking two otherwise separate networks
   - overlap with proposed trails / future bike facilities
   - length (short pieces discounted unless they close a gap)
   Classify as High / Medium / Low; color the map by tier; popups show the score breakdown.
   Sanity-check against known spots (Winterberry Ridge Dr trail, Avondale Dr spur).
3. **Content + publish** — sidebar with background (Duke Energy shared-use path guidelines,
   Carolina Thread Trail precedent, easement caveats), `git init`, `.gitignore` raw data,
   enable GitHub Pages.
4. **Extras (optional)** — `--refresh` to re-download data from ArcGIS REST endpoints; OSM road
   crossing counts; tree-canopy overlap; custom domain.

## Findings so far

- Step 1 done: 909 easement parcels in Durham + 1 mi buffer — **all Electric, no Gas**, so the
  gas paving concern doesn't apply here (gas layer/legend hide automatically when empty).
- Sidewalks, crosswalks and driveways are filtered out of the trails layer (`NON_TRAIL_TYPES`
  in `build.py`); revisit in Step 2 if they matter for connectivity.
- Published data totals ~1.3 MB (from 58 MB raw easements).
- Step 2 done (`corridors.py`): 287 segments, ~180 corridor miles — High 102 segs / 78 mi,
  Medium 115 / 77 mi, Low 70 / 24 mi. Only 6 segments link two or more separate networks.
- Deviations from the original Step 2 design:
  - Half the `Grantor` fields are blank, so "landowners" is scored as **easement deeds per
    mile** (each parcel is a separate deed/negotiation), not distinct owners.
  - Connectivity counts planned facilities as well as existing ones, so links between planned
    projects (e.g. the Avondale Dr spur near the Belt Line) score as gap closers.
  - Length is estimated from each merged shape's area and perimeter (rectangle fit); branched
    segments still overstate it somewhat.
- Sanity checks: Winterberry Ridge Dr segment -> High 66, already ~2,700 ft of trail inside;
  Avondale Dr spur (segment 45) -> High 72.
- Weights and thresholds live at the top of `corridors.py` for tuning.
- Step 3 publish done: https://davidbradway.github.io/Energy-Transportation-Trails/ (Actions
  workflow tests, then deploys `docs/`).
- `--refresh` done (2026-10-26). `build.py` now downloads from the ArcGIS services into `raw/`
  instead of reading the Jan 2023 files. Source changes since 2023:
  - "Existing Greenways" is no longer published; greenways are now `Facility_Type = Greenway`
    in the Existing Bike Facilities layer.
  - Existing Bike Facilities has a new schema and 614 records (was 67), adding shared-use paths
    and protected bike lanes.
  - Trails moved to `CityworksServices/Parks_and_Recreation/MapServer/8` (same schema).
  - Easements barely changed in Durham (~3 acres added).
  - Result: 301 segments; High 128 / 92 mi, Medium 114 / 73 mi, Low 59 / 19 mi. Segments
    linking 2+ networks rose from 6 to 20, almost all from the fuller bike data.
- Remaining: sidebar content, top-segments list, road crossings, tree canopy, custom domain.

## Notes

- `notes.md` has personal contact info — keep it out of the public repo (it's git-ignored).
- Landowner names (`Grantor`) are dropped from the published easement data.
- Preview locally: `python -m http.server -d docs 8000` then open http://localhost:8000
  (opening `index.html` directly from disk blocks the data fetches).
- Python env: `%USERPROFILE%\.venvs\ett` (kept outside Dropbox).

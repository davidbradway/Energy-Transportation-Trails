# ETT — Energy Transportation Trails

**Live map: https://davidbradway.github.io/Energy-Transportation-Trails/**

An interactive map of Duke Energy transmission easements in Durham County, NC, scored for how
feasible each corridor would be as a bike and hike trail. The name follows Durham's American
Tobacco Trail (ATT).

Power line corridors are long, mostly cleared, and already continuous, and Duke Energy allows
shared-use paths up to 12 ft wide inside its easements. This map overlays those corridors on
Durham's existing and planned trails, greenways and bike facilities to show where a trail in an
easement could close a gap in the network.

## What the map shows

- **Easement corridors**, split into segments of about half a mile and colored by feasibility:
  High (60+), Medium (40–59), Low (under 40).
- **Existing and proposed trails, greenways, bike facilities and future bike projects** from the
  City of Durham.
- Click a segment to see its score breakdown, length, width, which networks it reaches, and
  which planned projects are nearby.
- A **sidebar** explains the project and how scores work, lists the top 10 corridors (click one
  to zoom to it), sets out the caveats, and links to further reading. On phones it slides over
  the map from the "About & top corridors" button.
- The header shows the date the source data was downloaded.

## How segments are scored

Each segment gets up to 100 points:

| Factor | Points | What it measures |
|---|---|---|
| Connects networks | 35 | Separate trail/bike networks (existing or planned) within 500 ft. Two or more means the segment closes a gap. |
| Few easement deeds | 20 | Easement deeds per mile. Each deed is a separate agreement to renegotiate for trail use. |
| Near planned facility | 15 | How much of the segment runs alongside, or touches, a proposed trail or bike project. |
| Corridor width | 15 | Room for a 12 ft trail plus clearance (full points at 50 ft). |
| Length | 15 | Full points at half a mile; short pieces score well only if they connect something. |

Gas easements would be scored at half value because paving over gas lines may be restricted.
There are none in the Durham area. Weights and thresholds are at the top of
[corridors.py](corridors.py).

**This is a screening tool, not an engineering study.** A high score means a corridor is worth a
closer look. It says nothing about terrain, stream crossings, road crossings or tree cover, and
every trail in an easement needs new agreements with the property owners and Duke Energy.

## Running it locally

Requires Python 3.10+.

```sh
python -m venv .venv
.venv/Scripts/activate          # Windows; use `source .venv/bin/activate` elsewhere
pip install -r requirements-dev.txt

python build.py --refresh       # download source data to raw/, build docs/data/
python -m http.server -d docs 8000
```

Then open http://localhost:8000. Opening `docs/index.html` directly from disk won't work, because
the browser blocks the data requests.

`--refresh` downloads the latest version of every layer from its ArcGIS service (about 15 seconds)
and records the date in `raw/sources.json`, which the map shows as "Data as of". Run
`python build.py` without the flag to rebuild from the copies already in `raw/`, for example
after changing the scoring. `raw/` is not committed.

## Tests

```sh
pytest
```

- `tests/test_corridors.py`: segmentation and scoring on small synthetic corridors.
- `tests/test_build.py`: geometry cleanup and attribute tidying.
- `tests/test_fetch.py`: paged downloads from ArcGIS services (with the network faked), and
  that no personal fields are ever requested.
- `tests/test_data.py`: checks on the published files in `docs/data/`: geometry types,
  coordinates, file size, score consistency, and that no landowner names are published. These
  are skipped if `docs/data/` hasn't been built.

## Deployment

Every push to `main` runs the tests and then publishes `docs/` to GitHub Pages
([.github/workflows/pages.yml](.github/workflows/pages.yml)). CI doesn't download or rebuild the
data, so after refreshing the data or changing the pipeline, run `python build.py` (with
`--refresh` for new data) locally and commit the updated `docs/data/`.

## Project layout

```
build.py            data pipeline: download (--refresh), clip, simplify, score, write docs/data/
corridors.py        corridor segmentation and feasibility scoring
docs/               the static site served by GitHub Pages
  index.html        page and sidebar text
  app.js            map, popups, legend, sidebar lists
  style.css
  data/             generated GeoJSON + meta.json (committed)
raw/                downloaded source data (not committed)
tests/              pytest suite
PLAN.md             project plan and findings so far
.github/workflows/  test-and-deploy workflow
```

## Data sources

| Layer | Source |
|---|---|
| Duke Energy transmission easements | [NC OneMap](https://www.nconemap.gov/datasets/6c9a740f143b49f5bfcffe59c082b1c2_0/explore) |
| Existing and proposed trails | City of Durham, [Parks and Recreation: Trails and Paths](https://webgis2.durhamnc.gov/server/rest/services/CityworksServices/Parks_and_Recreation/MapServer/8) |
| Existing bike facilities and greenways | [City of Durham Open Data](https://live-durhamnc.opendata.arcgis.com/datasets/DurhamNC::existing-bike-facilities) |
| Future bike facilities | [City of Durham Open Data](https://live-durhamnc.opendata.arcgis.com/datasets/DurhamNC::future-bike-facilities) |
| Durham County boundary | [U.S. Census TIGERweb](https://tigerweb.geo.census.gov/) |
| Base map | © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors; satellite imagery © Esri |

The exact service URLs are in `SOURCES` in [build.py](build.py). Only the fields the map needs
are downloaded, so landowner names in the easement data and staff contact details in the
project data are never fetched or published.

## Further reading

- [Working with Duke Energy](https://www.carolinathreadtrail.org/wp-content/uploads/2018/12/Working-with-Duke-Energy.pdf),
  Carolina Thread Trail
- [Durham Trails and Greenways Master Plan](https://www.durhamnc.gov/2854/Trails-Greenways-Master-Plan-2011)
- [Durham Hike & Bike Map](https://live-durhamnc.opendata.arcgis.com/maps/durham-hike-bike-web-map/about)

## License

Code is released under the [MIT License](LICENSE). Data in `docs/data/` is derived from the sources
above and remains subject to their terms.

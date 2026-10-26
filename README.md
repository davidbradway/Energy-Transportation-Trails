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
- **Existing and proposed trails, greenways, bike lanes and future bike facilities** from the
  City of Durham.
- Click a segment to see its score breakdown, length, width, which networks it reaches, and
  which planned projects are nearby.

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

python build.py                 # raw GeoJSON -> docs/data/
python -m http.server -d docs 8000
```

Then open http://localhost:8000. Opening `docs/index.html` directly from disk won't work, because
the browser blocks the data requests.

`build.py` expects the raw GeoJSON downloads (listed below) in the repository root. They are not
committed because of their size.

## Tests

```sh
pytest
```

- `tests/test_corridors.py`: segmentation and scoring on small synthetic corridors.
- `tests/test_build.py`: geometry cleanup and attribute tidying.
- `tests/test_data.py`: checks on the published files in `docs/data/`: geometry types,
  coordinates, file size, score consistency, and that no landowner names are published. These
  tests are skipped until `build.py` has been run.

## Deployment

Every push to `main` runs the tests and then publishes `docs/` to GitHub Pages
([.github/workflows/pages.yml](.github/workflows/pages.yml)). CI doesn't have the raw data, so
after changing the pipeline, run `python build.py` locally and commit the updated `docs/data/`.

## Project layout

```
build.py            data pipeline: clip, simplify, score, write docs/data/
corridors.py        corridor segmentation and feasibility scoring
docs/               the static site served by GitHub Pages
  index.html, app.js, style.css
  data/             generated GeoJSON + meta.json
tests/
```

## Data sources

| Layer | Source |
|---|---|
| Duke Energy transmission easements | [NC OneMap](https://www.nconemap.gov/datasets/6c9a740f143b49f5bfcffe59c082b1c2_0/explore) |
| Existing and proposed trails | [City of Durham Open Data](https://live-durhamnc.opendata.arcgis.com/datasets/DurhamNC::existing-and-proposed-trails) |
| Existing greenways | [City of Durham Open Data](https://live-durhamnc.opendata.arcgis.com/datasets/DurhamNC::existing-greenways) |
| Existing bike facilities | [City of Durham Open Data](https://live-durhamnc.opendata.arcgis.com/datasets/DurhamNC::existing-bike-facilities) |
| Future bike facilities | [City of Durham Open Data](https://live-durhamnc.opendata.arcgis.com/datasets/DurhamNC::future-bike-facilities) |
| Durham County boundary | [U.S. Census TIGERweb](https://tigerweb.geo.census.gov/) |
| Base map | © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors; satellite imagery © Esri |

The source data was downloaded in January 2023. Landowner names in the easement data are
deliberately left out of everything published here.

## Further reading

- [Working with Duke Energy](https://www.carolinathreadtrail.org/wp-content/uploads/2018/12/Working-with-Duke-Energy.pdf),
  Carolina Thread Trail
- [Durham Trails and Greenways Master Plan](https://www.durhamnc.gov/2854/Trails-Greenways-Master-Plan-2011)

## License

Code is released under the [MIT License](LICENSE). Data in `docs/data/` is derived from the sources
above and remains subject to their terms.

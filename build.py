"""Build the ETT web map data.

Downloads source layers from their ArcGIS services into raw/, clips them to
Durham County (plus a buffer), simplifies and trims them, scores the easement
corridors, and writes compact GeoJSON to docs/data/ for the Leaflet page.

Usage:
    python build.py --refresh   # download the latest source data, then build
    python build.py             # build from the copies already in raw/
"""

import argparse
import json
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
import shapely

import corridors

ROOT = Path(__file__).parent
RAW = ROOT / "raw"
OUT = ROOT / "docs" / "data"

WGS84 = "EPSG:4326"
NC_FEET = "EPSG:2264"  # NC State Plane (US ft), for distances and simplification

BUFFER_FT = 5280  # keep easements within 1 mile of the county line
SIMPLIFY_FT = 5
PRECISION = 6  # decimal degrees, ~0.1 m
PAGE_SIZE = 1000  # below every source's maxRecordCount

COUNTY_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/"
    "MapServer/1/query?where=GEOID%3D%2737063%27&outFields=NAME,GEOID&outSR=4326&f=geojson"
)
DURHAM = "https://webgis2.durhamnc.gov/server/rest/services"

# raw file name -> ArcGIS layer and the fields to download. Only listed fields are fetched,
# so landowner names and staff contact details never leave the source servers.
SOURCES = {
    "easements": {
        "url": "https://services3.arcgis.com/oX5r75R7mapdoI2F/arcgis/rest/services/DukeTransmission/FeatureServer/0",
        "fields": ["OBJECTID", "Service"],
        "near_county": True,  # statewide layer: only download around Durham
    },
    "trails": {
        "url": f"{DURHAM}/CityworksServices/Parks_and_Recreation/MapServer/8",
        "fields": ["OBJECTID", "NAME", "SYSTEMNAME", "STATUS", "TRAILTYPE", "SURFTYPE", "WIDTH",
                   "LENGTH", "OWNEDBY"],
    },
    "bike_facilities": {
        "url": f"{DURHAM}/ProjectServices/Trans_ExistingFutureBikePedFacilities/MapServer/4",
        "fields": ["OBJECTID", "On_Road", "From_Road", "To_Road", "SideOfRoad", "Facility_Type",
                   "Date_Completed_Year"],
    },
    "bike_future": {
        "url": f"{DURHAM}/ProjectServices/Trans_ExistingFutureBikePedFacilities/MapServer/3",
        "fields": ["OBJECTID", "Project_Name", "Project_Description", "From_Road", "To_Road",
                   "Facility_Type_Entire_Project", "Phase_Status", "Est_Construction_Comp_Date",
                   "Department"],
    },
}

# Sidewalks, crosswalks and driveways are in the trails layer but aren't trails.
NON_TRAIL_TYPES = {"Sidewalk", "Crosswalk", "Driveway"}

# output name -> (raw file name, row filter, {source column: output column})
LAYERS = {
    "trails": ("trails", lambda g: ~g["TRAILTYPE"].isin(NON_TRAIL_TYPES), {
        "NAME": "name",
        "SYSTEMNAME": "system",
        "STATUS": "status",
        "TRAILTYPE": "type",
        "SURFTYPE": "surface",
        "WIDTH": "width_ft",
        "LENGTH": "miles",
        "OWNEDBY": "owner",
    }),
    "greenways": ("bike_facilities", lambda g: g["Facility_Type"] == "Greenway", {
        "On_Road": "name",
        "extent": "extent",
        "Date_Completed_Year": "year",
    }),
    "bike_existing": ("bike_facilities", lambda g: g["Facility_Type"] != "Greenway", {
        "On_Road": "name",
        "extent": "extent",
        "Facility_Type": "facility",
        "SideOfRoad": "side",
        "Date_Completed_Year": "year",
    }),
    "bike_future": ("bike_future", None, {
        "Project_Name": "name",
        "extent": "extent",
        "Project_Description": "description",
        "Facility_Type_Entire_Project": "facility",
        "Phase_Status": "status",
        "Est_Construction_Comp_Date": "year",
        "Department": "dept",
    }),
}


def fetch(url, fields, envelope=None):
    """All features of an ArcGIS layer as a GeoJSON dict, paging past the server's limit."""
    params = {
        "where": "1=1",
        "outFields": ",".join(fields),
        "outSR": 4326,
        "orderByFields": "OBJECTID",
        "resultRecordCount": PAGE_SIZE,
        "f": "geojson",
    }
    if envelope is not None:
        xmin, ymin, xmax, ymax = envelope
        params |= {
            "geometry": f"{xmin},{ymin},{xmax},{ymax}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
        }
    features = []
    while True:
        resp = requests.get(f"{url}/query", params=params | {"resultOffset": len(features)}, timeout=120)
        resp.raise_for_status()
        page = resp.json()
        if "error" in page:
            raise RuntimeError(f"{url}: {page['error']}")
        features += page["features"]
        if len(page["features"]) < PAGE_SIZE:
            return {"type": "FeatureCollection", "features": features}


def refresh():
    """Download the latest source layers into raw/ and record when."""
    RAW.mkdir(exist_ok=True)
    resp = requests.get(COUNTY_URL, timeout=60)
    resp.raise_for_status()
    (RAW / "durham_county.geojson").write_text(resp.text, encoding="utf-8")
    envelope = durham_county().buffer(BUFFER_FT).to_crs(WGS84).total_bounds

    manifest = {}
    print("Downloading to raw/")
    for name, src in SOURCES.items():
        data = fetch(src["url"], src["fields"], envelope if src.get("near_county") else None)
        (RAW / f"{name}.geojson").write_text(json.dumps(data), encoding="utf-8")
        manifest[name] = {"url": src["url"], "features": len(data["features"]), "downloaded": str(date.today())}
        print(f"  {name:15} {len(data['features']):6,} features")
    (RAW / "sources.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def durham_county():
    return read_raw("durham_county")


def read_raw(name):
    path = RAW / f"{name}.geojson"
    if not path.exists():
        raise SystemExit(f"{path} is missing: run `python build.py --refresh` first.")
    return gpd.read_file(path).to_crs(NC_FEET)


def add_extent(gdf):
    """'From Rd – To Rd' description of where a facility runs, when the source gives one."""
    if "From_Road" in gdf:
        ends = gdf[["From_Road", "To_Road"]].apply(lambda col: col.str.strip())
        gdf["extent"] = ends["From_Road"].str.cat(ends["To_Road"], sep=" – ")
    return gdf


def tidy(gdf, columns):
    gdf = gdf[list(columns) + ["geometry"]].rename(columns=columns)
    for col in gdf.columns.drop("geometry"):
        if pd.api.types.is_string_dtype(gdf[col]):
            gdf[col] = gdf[col].str.strip().replace("", None)
        elif pd.api.types.is_float_dtype(gdf[col]):
            gdf[col] = gdf[col].round(2)
    kind = "Polygon" if "Polygon" in gdf.geom_type.iloc[0] else "LineString"
    gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_FT, preserve_topology=True).apply(only_parts, kind=kind)
    return gdf[~gdf.geometry.is_empty]


def only_parts(geom, kind):
    """Drop stray points and sub-foot slivers, which collapse to points or lines once coordinates
    are rounded, so a layer holds only its own geometry type (Leaflet draws points as markers)."""

    def size(p):  # length of a line, approximate width of a polygon
        return 2 * p.area / p.length if kind == "Polygon" else p.length

    parts = [p for p in shapely.get_parts(geom) if p.geom_type == kind and size(p) >= 1]
    if len(parts) == 1:
        return parts[0]
    multi = shapely.MultiPolygon if kind == "Polygon" else shapely.MultiLineString
    return multi(parts)


def write(gdf, name):
    path = OUT / f"{name}.geojson"
    gdf = gdf.to_crs(WGS84)
    # Snap to the output grid ourselves so anything that collapses is dropped cleanly
    # instead of GDAL writing it as a stray line or point.
    gdf["geometry"] = shapely.set_precision(gdf.geometry.values, 10**-PRECISION)
    gdf = gdf[~gdf.geometry.is_empty]
    gdf.to_file(
        path, driver="GeoJSON", engine="pyogrio",
        layer_options={"COORDINATE_PRECISION": PRECISION, "RFC7946": "YES"},
    )
    print(f"  {name:15} {len(gdf):6,} features  {path.stat().st_size / 1e6:6.2f} MB")


def build_segments(county, layers):
    area = county.buffer(BUFFER_FT).union_all()
    parcels = read_raw("easements")
    parcels = parcels.loc[parcels.intersects(area), ["OBJECTID", "Service", "geometry"]]

    trails, bike_future = layers["trails"], layers["bike_future"]
    existing = pd.concat([
        trails[trails["status"] == "Existing"],
        layers["greenways"],
        layers["bike_existing"],
    ])
    planned = pd.concat([
        trails[trails["status"] == "Proposed"],
        bike_future[bike_future["status"] != "Complete"],
    ])
    segs = corridors.build_segments(parcels, county, existing, planned)
    segs["geometry"] = segs.geometry.simplify(SIMPLIFY_FT).apply(only_parts, kind="Polygon")
    return segs


def summarize(segs):
    by_tier = segs.groupby("tier").agg(segments=("id", "size"), miles=("miles", "sum")).round(1)
    return {
        "segments": len(segs),
        "miles": round(segs["miles"].sum(), 1),
        "tiers": by_tier.to_dict(orient="index"),
        "weights": corridors.WEIGHTS,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="download the latest source data first")
    if parser.parse_args().refresh:
        refresh()

    OUT.mkdir(parents=True, exist_ok=True)
    county = durham_county()
    print("Writing docs/data/")

    write(county[["NAME", "geometry"]].rename(columns={"NAME": "name"}), "county")

    layers = {}
    for name, (raw, keep, columns) in LAYERS.items():
        gdf = add_extent(read_raw(raw))
        if keep is not None:
            gdf = gdf[keep(gdf)]
        layers[name] = tidy(gdf, columns)
        write(layers[name], name)

    segs = build_segments(county, layers)
    write(segs, "segments")

    sources = json.loads((RAW / "sources.json").read_text(encoding="utf-8"))
    bounds = county.to_crs(WGS84).total_bounds
    meta = {
        "bounds": [[bounds[1], bounds[0]], [bounds[3], bounds[2]]],
        "data_as_of": min(s["downloaded"] for s in sources.values()),
        "summary": summarize(segs),
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(json.dumps(meta["summary"], indent=1))


if __name__ == "__main__":
    main()

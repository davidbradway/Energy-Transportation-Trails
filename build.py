"""Build the ETT web map data.

Reads the raw GeoJSON downloads in this folder, clips them to Durham County
(plus a buffer), simplifies and trims them, and writes compact GeoJSON to
docs/data/ for the Leaflet page.

Usage:
    python build.py
"""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
import shapely

import corridors

ROOT = Path(__file__).parent
RAW = ROOT
CACHE = ROOT / "raw"
OUT = ROOT / "docs" / "data"

WGS84 = "EPSG:4326"
NC_FEET = "EPSG:2264"  # NC State Plane (US ft), for distances and simplification

BUFFER_FT = 5280  # keep easements within 1 mile of the county line
SIMPLIFY_FT = 5
PRECISION = 6  # decimal degrees, ~0.1 m

COUNTY_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/"
    "MapServer/1/query?where=GEOID%3D%2737063%27&outFields=NAME,GEOID&outSR=4326&f=geojson"
)

# Sidewalks, crosswalks and driveways are in the trails layer but aren't trails.
NON_TRAIL_TYPES = {"Sidewalk", "Crosswalk", "Driveway"}

# source file stem -> (output name, {source column: output column})
LAYERS = {
    "Existing_and_Proposed_Trails": ("trails", {
        "NAME": "name",
        "SYSTEMNAME": "system",
        "STATUS": "status",
        "TRAILTYPE": "type",
        "SURFTYPE": "surface",
        "WIDTH": "width_ft",
        "LENGTH": "miles",
        "OWNEDBY": "owner",
    }),
    "Existing_Greenways": ("greenways", {
        "Project_Na": "name",
        "Extent": "extent",
        "Status": "status",
        "LENGTH": "miles",
        "Install_Yr": "year",
    }),
    "Existing_Bike_Facilities": ("bike_existing", {
        "Project_Na": "name",
        "Extent": "extent",
        "Descript": "description",
        "Facility": "facility",
        "Length_mi": "miles",
        "Install_Yr": "year",
    }),
    "Future_Bike_Facilities": ("bike_future", {
        "Proj_Name": "name",
        "Descript": "description",
        "Facility": "facility",
        "Project_St": "status",
        "Est_Constr": "year",
        "Dept": "dept",
    }),
}


def durham_county():
    """Durham County boundary, downloaded once and cached in raw/."""
    path = CACHE / "durham_county.geojson"
    if not path.exists():
        CACHE.mkdir(exist_ok=True)
        resp = requests.get(COUNTY_URL, timeout=60)
        resp.raise_for_status()
        path.write_text(resp.text, encoding="utf-8")
    return gpd.read_file(path).to_crs(NC_FEET)


def read_raw(stem):
    return gpd.read_file(RAW / f"{stem}.geojson").to_crs(NC_FEET)


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
    parcels = read_raw("DukeTransmissionEasements")
    # Grantor (landowner name) is never read into the published data.
    parcels = parcels.loc[parcels.intersects(area), ["OBJECTID", "Service", "geometry"]]

    trails, bike_future = layers["trails"], layers["bike_future"]
    existing = pd.concat([
        trails[trails["status"] == "Existing"],
        layers["greenways"],
        layers["bike_existing"],
        bike_future[bike_future["status"] == "Complete"],
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
    OUT.mkdir(parents=True, exist_ok=True)
    county = durham_county()
    print("Writing docs/data/")

    write(county[["NAME", "geometry"]].rename(columns={"NAME": "name"}), "county")

    layers = {}
    for stem, (name, columns) in LAYERS.items():
        gdf = read_raw(stem)
        if name == "trails":
            gdf = gdf[~gdf["TRAILTYPE"].isin(NON_TRAIL_TYPES)]
        layers[name] = tidy(gdf, columns)
        write(layers[name], name)

    segs = build_segments(county, layers)
    write(segs, "segments")
    (OUT / "easements.geojson").unlink(missing_ok=True)  # superseded by segments

    bounds = county.to_crs(WGS84).total_bounds
    meta = {"bounds": [[bounds[1], bounds[0]], [bounds[3], bounds[2]]], "summary": summarize(segs)}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(json.dumps(meta["summary"], indent=1))


if __name__ == "__main__":
    main()

"""Unit tests for helpers in build.py."""

import geopandas as gpd
import shapely
from shapely.geometry import GeometryCollection, LineString, MultiLineString, Point, box

import build


def test_only_parts_drops_points_from_line_layer():
    geom = GeometryCollection([Point(0, 0), LineString([(0, 0), (100, 0)])])
    assert build.only_parts(geom, "LineString").equals(LineString([(0, 0), (100, 0)]))


def test_only_parts_drops_sub_foot_slivers():
    geom = MultiLineString([[(0, 0), (100, 0)], [(0, 0), (0.5, 0)]])
    assert build.only_parts(geom, "LineString").geom_type == "LineString"


def test_only_parts_keeps_multi_geometry():
    geom = MultiLineString([[(0, 0), (100, 0)], [(0, 50), (100, 50)]])
    assert build.only_parts(geom, "LineString").geom_type == "MultiLineString"


def test_only_parts_drops_hairline_polygon_slivers():
    geom = shapely.MultiPolygon([box(0, 0, 100, 100), box(200, 0, 300, 0.2)])
    assert build.only_parts(geom, "Polygon").equals(box(0, 0, 100, 100))


def test_only_parts_returns_empty_when_nothing_left():
    assert build.only_parts(Point(0, 0), "LineString").is_empty


def test_tidy_renames_strips_and_drops_unlisted_columns():
    gdf = gpd.GeoDataFrame(
        {"NAME": ["  Trail A ", " "], "SECRET": ["x", "y"], "LENGTH": [1.23456, 2.0]},
        geometry=[LineString([(0, 0), (100, 0)]), LineString([(0, 10), (100, 10)])],
        crs=build.NC_FEET,
    )
    out = build.tidy(gdf, {"NAME": "name", "LENGTH": "miles"})
    assert list(out.columns) == ["name", "miles", "geometry"]
    assert out["name"].iloc[0] == "Trail A"
    assert out["name"].isna().iloc[1]
    assert out["miles"].tolist() == [1.23, 2.0]


def test_tidy_drops_features_that_vanish():
    gdf = gpd.GeoDataFrame(
        {"NAME": ["keep", "drop"]},
        geometry=[box(0, 0, 100, 100), GeometryCollection([Point(0, 0)])],
        crs=build.NC_FEET,
    )
    out = build.tidy(gdf, {"NAME": "name"})
    assert out["name"].tolist() == ["keep"]

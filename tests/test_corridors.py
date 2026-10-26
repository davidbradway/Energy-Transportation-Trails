"""Unit tests for corridors.py on small synthetic geometries (NC State Plane feet)."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, box

import corridors

CRS = "EPSG:2264"


def parcels_row(n, length=500, width=100, x0=0, y0=0, service="Electric", start_id=1):
    """n touching rectangular parcels laid end to end along the x axis."""
    return gpd.GeoDataFrame(
        {"OBJECTID": range(start_id, start_id + n), "Service": service},
        geometry=[box(x0 + i * length, y0, x0 + (i + 1) * length, y0 + width) for i in range(n)],
        crs=CRS,
    )


def lines(*geoms, names=None):
    names = names or [f"Line {i}" for i in range(len(geoms))]
    return gpd.GeoDataFrame({"name": names}, geometry=list(geoms), crs=CRS)


def county_around(*frames, pad=10_000):
    xmin, ymin, xmax, ymax = np.array([f.total_bounds for f in frames]).T
    return gpd.GeoDataFrame(
        geometry=[box(xmin.min() - pad, ymin.min() - pad, xmax.max() + pad, ymax.max() + pad)], crs=CRS
    )


FAR_PLANNED = lines(LineString([(90_000, 90_000), (91_000, 90_000)]))


def test_corridor_length_of_rectangle():
    geoms = gpd.GeoSeries([box(0, 0, 500, 100), box(0, 0, 100, 100)], crs=CRS)
    assert corridor_lengths(geoms) == pytest.approx([500, 100])


def corridor_lengths(geoms):
    return list(corridors.corridor_length(geoms))


def test_neighbors_links_touching_parcels_only():
    parcels = parcels_row(3)
    nbrs = corridors.neighbors(parcels)
    assert nbrs == {0: {1}, 1: {0, 2}, 2: {1}}


def test_segment_splits_long_corridor_into_half_mile_pieces():
    parcels = parcels_row(20)  # 10,000 ft
    parcels["length_ft"] = corridors.corridor_length(parcels.geometry)
    seg, corridor = corridors.segment(parcels)

    assert corridor.nunique() == 1
    lengths = parcels.groupby(seg)["length_ft"].sum()
    assert len(lengths) == 4
    assert (lengths >= corridors.MIN_SEGMENT_FT).all()
    # Each segment is a contiguous run of parcels.
    for s in seg.unique():
        members = sorted(seg[seg == s].index)
        assert members == list(range(members[0], members[-1] + 1))


def test_segment_merges_short_leftover_into_neighbor():
    parcels = parcels_row(7)  # 3,500 ft: one 3,000 ft segment + a 500 ft leftover
    parcels["length_ft"] = corridors.corridor_length(parcels.geometry)
    seg, _ = corridors.segment(parcels)
    assert seg.nunique() == 1


def test_segment_keeps_separate_corridors_apart():
    parcels = pd.concat([parcels_row(2), parcels_row(2, y0=5_000, start_id=10)], ignore_index=True)
    parcels["length_ft"] = corridors.corridor_length(parcels.geometry)
    seg, corridor = corridors.segment(parcels)
    assert corridor.nunique() == 2
    assert seg.nunique() == 2


def test_segment_linking_two_networks_scores_full_connectivity():
    parcels = parcels_row(6)  # one 3,000 ft segment
    existing = lines(
        LineString([(-100, -1_000), (-100, 1_000)]),
        LineString([(3_100, -1_000), (3_100, 1_000)]),
        names=["West Trail", "East Trail"],
    )
    segs = corridors.build_segments(parcels, county_around(parcels), existing, FAR_PLANNED)

    assert len(segs) == 1
    s = segs.iloc[0]
    assert s["networks"] == 2
    assert s["pts_connectivity"] == corridors.WEIGHTS["connectivity"]
    assert s["pts_planned"] == 0
    assert s["width_ft"] == 100
    assert s["miles"] == pytest.approx(3_000 / 5280, abs=0.01)
    assert s["connects"] == "East Trail; West Trail"
    assert s["tier"] == "High"


def test_isolated_segment_scores_no_connectivity():
    parcels = parcels_row(6)
    existing = lines(LineString([(0, 20_000), (1_000, 20_000)]))
    segs = corridors.build_segments(parcels, county_around(parcels, existing), existing, FAR_PLANNED)
    assert segs.iloc[0]["networks"] == 0
    assert segs.iloc[0]["pts_connectivity"] == 0


def test_planned_facility_alongside_scores_full_planned_points():
    parcels = parcels_row(6)
    existing = lines(LineString([(0, 20_000), (1_000, 20_000)]))
    planned = lines(LineString([(0, 150), (3_000, 150)]), names=["Planned Greenway"])
    segs = corridors.build_segments(parcels, county_around(parcels, existing), existing, planned)
    s = segs.iloc[0]
    assert s["pts_planned"] == corridors.WEIGHTS["planned"]
    assert s["planned"] == "Planned Greenway"


def test_gas_corridor_score_is_discounted():
    existing = lines(LineString([(-100, -1_000), (-100, 1_000)]), LineString([(3_100, -1_000), (3_100, 1_000)]))
    electric = corridors.build_segments(parcels_row(6), county_around(existing), existing, FAR_PLANNED)
    gas = corridors.build_segments(parcels_row(6, service="Gas"), county_around(existing), existing, FAR_PLANNED)
    expected = round(electric.iloc[0]["score"] * corridors.SERVICE_FACTOR["Gas"])
    assert gas.iloc[0]["score"] == pytest.approx(expected, abs=1)


def test_corridors_outside_county_are_dropped():
    inside = parcels_row(6)
    outside = parcels_row(6, y0=50_000, start_id=100)
    parcels = pd.concat([inside, outside], ignore_index=True)
    county = gpd.GeoDataFrame(geometry=[box(-1_000, -1_000, 4_000, 1_000)], crs=CRS)
    segs = corridors.build_segments(parcels, county, lines(LineString([(0, 500), (10, 500)])), FAR_PLANNED)
    assert len(segs) == 1
    assert segs.iloc[0]["in_county"]


def test_corridor_crossing_county_line_is_kept_whole():
    parcels = parcels_row(12)  # 6,000 ft; county covers only the first 1,000 ft
    county = gpd.GeoDataFrame(geometry=[box(-1_000, -1_000, 1_000, 1_000)], crs=CRS)
    segs = corridors.build_segments(parcels, county, lines(LineString([(0, 500), (10, 500)])), FAR_PLANNED)
    assert segs["deeds"].sum() == 12
    assert (~segs["in_county"]).any()


def test_scores_and_points_are_within_bounds():
    parcels = parcels_row(20, width=15)  # narrow: below MIN_WIDTH_FT
    existing = lines(LineString([(0, 400), (10_000, 400)]))
    segs = corridors.build_segments(parcels, county_around(parcels), existing, FAR_PLANNED)
    for factor, weight in corridors.WEIGHTS.items():
        assert segs[f"pts_{factor}"].between(0, weight).all()
    assert segs["score"].between(0, 100).all()
    assert (segs["pts_width"] == 0).all()
    assert list(segs["id"]) == list(range(1, len(segs) + 1))
    assert segs["score"].is_monotonic_decreasing

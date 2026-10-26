"""Checks on the published data in docs/data/ (run `python build.py` first)."""

import json
from pathlib import Path

import pytest

import corridors

DATA = Path(__file__).parent.parent / "docs" / "data"
LAYERS = ["county", "segments", "trails", "greenways", "bike_existing", "bike_future"]
GEOMETRY = {"county": "Polygon", "segments": "Polygon"}  # everything else is lines
MAX_TOTAL_MB = 5

pytestmark = pytest.mark.skipif(not (DATA / "meta.json").exists(), reason="run build.py first")


def load(name):
    return json.loads((DATA / f"{name}.geojson").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", LAYERS)
def test_layer_has_only_expected_geometry(name):
    kind = GEOMETRY.get(name, "LineString")
    features = load(name)["features"]
    assert features
    types = {f["geometry"]["type"] for f in features}
    assert types <= {kind, f"Multi{kind}"}, f"{name} has {types}"


def test_coordinates_are_wgs84_around_durham():
    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    (south, west), (north, east) = meta["bounds"]
    assert 35.5 < south < north < 36.5
    assert -79.5 < west < east < -78.5


def test_no_landowner_names_published():
    for path in DATA.glob("*.geojson"):
        assert "grantor" not in path.read_text(encoding="utf-8").lower(), path.name


def test_published_data_stays_small():
    total = sum(p.stat().st_size for p in DATA.iterdir()) / 1e6
    assert total < MAX_TOTAL_MB


def test_segments_have_consistent_scores():
    tiers = {t for _, t in corridors.TIERS}
    for f in load("segments")["features"]:
        p = f["properties"]
        assert p["tier"] in tiers
        assert 0 <= p["score"] <= 100
        points = sum(p[f"pts_{k}"] for k in corridors.WEIGHTS)
        factor = corridors.SERVICE_FACTOR.get(p["service"], 1)
        assert p["score"] == round(points * factor)
        cutoff = next(cut for cut, t in corridors.TIERS if t == p["tier"])
        assert p["score"] >= cutoff


def test_summary_matches_segments():
    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    segments = load("segments")["features"]
    assert meta["summary"]["segments"] == len(segments)
    assert sum(t["segments"] for t in meta["summary"]["tiers"].values()) == len(segments)
    assert meta["summary"]["weights"] == corridors.WEIGHTS

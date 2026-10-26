"""Tests for downloading source layers (network calls are faked)."""

import geopandas as gpd
import pytest

import build


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def fake_server(total, calls):
    """A requests.get stand-in that serves `total` features in pages."""

    def get(url, params, timeout):
        calls.append(params)
        start = params["resultOffset"]
        ids = range(start, min(start + params["resultRecordCount"], total))
        return FakeResponse({"features": [{"type": "Feature", "properties": {"OBJECTID": i}} for i in ids]})

    return get


@pytest.mark.parametrize("total", [0, 5, build.PAGE_SIZE, 2 * build.PAGE_SIZE + 3])
def test_fetch_pages_through_all_features(monkeypatch, total):
    calls = []
    monkeypatch.setattr(build.requests, "get", fake_server(total, calls))
    data = build.fetch("https://example.test/layer/0", ["OBJECTID"])
    ids = [f["properties"]["OBJECTID"] for f in data["features"]]
    assert ids == list(range(total))
    assert all(c["orderByFields"] == "OBJECTID" for c in calls)


def test_fetch_requests_only_listed_fields_and_envelope(monkeypatch):
    calls = []
    monkeypatch.setattr(build.requests, "get", fake_server(1, calls))
    build.fetch("https://example.test/layer/0", ["OBJECTID", "Service"], envelope=(-79, 35, -78, 36))
    assert calls[0]["outFields"] == "OBJECTID,Service"
    assert calls[0]["geometry"] == "-79,35,-78,36"
    assert calls[0]["outSR"] == 4326


def test_fetch_raises_on_server_error(monkeypatch):
    error = {"error": {"code": 400, "message": "Invalid query"}}
    monkeypatch.setattr(build.requests, "get", lambda url, params, timeout: FakeResponse(error))
    with pytest.raises(RuntimeError, match="Invalid query"):
        build.fetch("https://example.test/layer/0", ["OBJECTID"])


def test_sources_never_request_personal_fields():
    for src in build.SOURCES.values():
        fields = {f.lower() for f in src["fields"]}
        assert not fields & {"grantor", "project_manager_name", "project_manager_email"}


def test_add_extent_joins_from_and_to():
    gdf = gpd.GeoDataFrame({"From_Road": [" Main St", "Elm St", None], "To_Road": ["Oak St ", None, "Pine St"]})
    out = build.add_extent(gdf)
    assert out["extent"].iloc[0] == "Main St – Oak St"
    assert out["extent"].iloc[1:].isna().all()


def test_add_extent_leaves_layers_without_roads_alone():
    gdf = gpd.GeoDataFrame({"NAME": ["Trail"]})
    assert "extent" not in build.add_extent(gdf)

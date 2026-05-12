"""Tests for load_estate_sites() and compute_estate_proximity()."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

from webapp.data_access import compute_estate_proximity, load_estate_sites


def _write_estate_csv(path: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def test_load_returns_geodataframe(tmp_path):
    csv = tmp_path / "sites.csv"
    _write_estate_csv(csv, [
        {"site_name": "Test Hospital", "trust_name": "Test Trust", "postcode": "E1 4DG", "latitude": 51.5, "longitude": -0.07, "geocode_source": "test"},
    ])
    result = load_estate_sites(csv)
    assert isinstance(result, gpd.GeoDataFrame)
    assert len(result) == 1


def test_load_drops_nan_coords(tmp_path):
    csv = tmp_path / "sites.csv"
    _write_estate_csv(csv, [
        {"site_name": "Good", "latitude": 51.5, "longitude": -0.07},
        {"site_name": "Bad", "latitude": None, "longitude": -0.07},
    ])
    result = load_estate_sites(csv)
    assert len(result) == 1
    assert result.iloc[0]["site_name"] == "Good"


def test_proximity_returns_null_when_no_sites():
    result = compute_estate_proximity(51.5, -0.1, None, 1000)
    assert result["nearby_nhs_estate_flag"] is False
    assert result["nearby_estate_count"] == 0
    assert result["nearest_estate_name"] is None
    assert result["nearest_estate_distance_m"] is None


def test_proximity_returns_null_for_empty_sites():
    empty = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    result = compute_estate_proximity(51.5, -0.1, empty, 1000)
    assert result["nearby_nhs_estate_flag"] is False


def test_proximity_flags_nearby_site(tmp_path):
    csv = tmp_path / "sites.csv"
    # St Thomas' Hospital — very close to Waterloo
    _write_estate_csv(csv, [
        {"site_name": "St Thomas", "latitude": 51.4985, "longitude": -0.1174},
    ])
    sites = load_estate_sites(csv)
    result = compute_estate_proximity(51.4985, -0.1174, sites, 1000)
    assert result["nearby_nhs_estate_flag"] is True
    assert result["nearby_estate_count"] == 1
    assert result["nearest_estate_name"] == "St Thomas"
    assert result["nearest_estate_distance_m"] == pytest.approx(0.0, abs=1.0)


def test_proximity_excludes_distant_site(tmp_path):
    csv = tmp_path / "sites.csv"
    # Site in central London; candidate far away
    _write_estate_csv(csv, [
        {"site_name": "Far Hospital", "latitude": 51.5, "longitude": -0.1},
    ])
    sites = load_estate_sites(csv)
    # Candidate is ~15 km away in Romford area
    result = compute_estate_proximity(51.575, 0.185, sites, 1000)
    assert result["nearby_nhs_estate_flag"] is False

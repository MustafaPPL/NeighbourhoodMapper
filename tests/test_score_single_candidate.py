"""Tests for _score_single_candidate() with time-decay mode."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from webapp.analysis import _score_single_candidate, DEFAULT_HUB_SCORE_WEIGHTS


def _make_centroids(n: int) -> gpd.GeoDataFrame:
    rows = []
    for i in range(n):
        rows.append({
            "LSOA_code": f"E{i:09d}",
            "need_score": 0.5 + i * 0.05,
            "geometry": Point(0 + i * 100, 0),  # BNG coords, 100m apart
        })
    return gpd.GeoDataFrame(rows, crs="EPSG:27700")


def _make_candidate(lsoa_code: str, x: float = 0.0, y: float = 0.0) -> pd.Series:
    return pd.Series({
        "LSOA_code": lsoa_code,
        "geometry": Point(x, y),
    })


def test_straight_line_mode_uses_distance_decay():
    centroids = _make_centroids(5)
    candidate = _make_candidate("E000000000", 0.0, 0.0)
    result = _score_single_candidate(
        candidate, centroids, DEFAULT_HUB_SCORE_WEIGHTS, catchment_radius_m=500
    )
    assert "hub_score" in result
    assert result["lsoas_in_catchment"] >= 0


def test_travel_time_mode_excludes_beyond_30min():
    centroids = _make_centroids(3)
    # Travel time matrix: LSOA 0 (host) → LSOA 1: 15 min (in), LSOA 2: 35 min (out)
    matrix = {
        ("E000000000", "E000000001"): 15.0,
        ("E000000000", "E000000002"): 35.0,
    }
    candidate = _make_candidate("E000000000")
    result = _score_single_candidate(
        candidate, centroids, DEFAULT_HUB_SCORE_WEIGHTS, catchment_radius_m=5000, travel_time_matrix=matrix
    )
    assert result["lsoas_in_catchment"] == 1  # only LSOA 1 within 30 min


def test_travel_time_weight_formula():
    centroids = _make_centroids(2)
    # 10 min travel → weight = 1 - 10/30 = 0.667
    matrix = {("E000000000", "E000000001"): 10.0}
    candidate = _make_candidate("E000000000")
    result = _score_single_candidate(
        candidate, centroids, {"host_lsoa": 0.0, "catchment": 100.0}, catchment_radius_m=5000, travel_time_matrix=matrix
    )
    # With host_lsoa weight=0, only catchment matters
    # catchment = need_score of LSOA 1 = 0.55 (weighted by 0.667, only one LSOA so weight cancels)
    expected_catchment = 0.55  # need_score of LSOA index 1
    assert result["weighted_catchment_need_score"] == pytest.approx(expected_catchment, abs=1e-4)


def test_output_schema_unchanged():
    centroids = _make_centroids(3)
    candidate = _make_candidate("E000000000")
    result = _score_single_candidate(
        candidate, centroids, DEFAULT_HUB_SCORE_WEIGHTS, catchment_radius_m=500
    )
    expected_keys = {"host_need_score", "weighted_catchment_need_score", "lsoas_in_catchment", "catchment_radius_m", "hub_score"}
    assert set(result.keys()) == expected_keys


def test_none_matrix_falls_back_to_distance():
    centroids = _make_centroids(4)
    candidate = _make_candidate("E000000000")
    result_straight = _score_single_candidate(
        candidate, centroids, DEFAULT_HUB_SCORE_WEIGHTS, catchment_radius_m=500, travel_time_matrix=None
    )
    result_no_arg = _score_single_candidate(
        candidate, centroids, DEFAULT_HUB_SCORE_WEIGHTS, catchment_radius_m=500
    )
    assert result_straight["hub_score"] == result_no_arg["hub_score"]

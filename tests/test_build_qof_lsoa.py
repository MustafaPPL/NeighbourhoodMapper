"""Tests for the QOF LSOA attribution script."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.analysis.build_qof_lsoa import (
    INDICATOR_FAMILIES,
    TOP_N_PRACTICES,
    _haversine_km,
    compute_weighted_prevalence,
    load_gp_geocoded,
    load_list_sizes,
    load_qof_prevalence,
)


# ---------------------------------------------------------------------------
# _haversine_km
# ---------------------------------------------------------------------------

def test_haversine_zero_distance():
    lat = np.array([51.5])
    lon = np.array([-0.1])
    result = _haversine_km(lat, lon, 51.5, -0.1)
    assert result[0] == pytest.approx(0.0, abs=1e-6)


def test_haversine_known_distance():
    # London to Manchester is roughly 262 km
    lat = np.array([51.5074])
    lon = np.array([-0.1278])
    result = _haversine_km(lat, lon, 53.4808, -2.2426)
    assert 255 < result[0] < 270


# ---------------------------------------------------------------------------
# load_qof_prevalence
# ---------------------------------------------------------------------------

def _write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False)


def test_load_qof_prevalence_extracts_four_diseases(tmp_path):
    data = pd.DataFrame({
        "PRACTICE_CODE": ["E001"] * 4 + ["E002"] * 4,
        "INDICATOR_CODE": ["CHD001", "COPD001", "DM001", "DEP001"] * 2,
        "PREVALENCE": [5.0, 3.0, 7.0, 10.0, 6.0, 4.0, 8.0, 11.0],
    })
    path = tmp_path / "qof.csv"
    _write_csv(path, data)
    result = load_qof_prevalence(path)
    assert set(INDICATOR_FAMILIES.keys()).issubset(result.columns)
    assert len(result) == 2  # one row per practice


def test_load_qof_prevalence_raises_on_missing_column(tmp_path):
    data = pd.DataFrame({"PRACTICE_CODE": ["E001"], "PREVALENCE": [5.0]})
    path = tmp_path / "qof.csv"
    _write_csv(path, data)
    with pytest.raises(ValueError, match="INDICATOR_CODE"):
        load_qof_prevalence(path)


# ---------------------------------------------------------------------------
# load_gp_geocoded
# ---------------------------------------------------------------------------

def test_load_gp_geocoded_renames_columns(tmp_path):
    data = pd.DataFrame({
        "Practice code": ["E001", "E002"],
        "Latitude": [51.5, 51.6],
        "Longitude": [-0.1, -0.2],
    })
    path = tmp_path / "gp.csv"
    _write_csv(path, data)
    result = load_gp_geocoded(path)
    assert list(result.columns) == ["practice_code", "gp_lat", "gp_lon"]
    assert len(result) == 2


def test_load_gp_geocoded_drops_nulls(tmp_path):
    data = pd.DataFrame({
        "Practice code": ["E001", "E002"],
        "Latitude": [51.5, None],
        "Longitude": [-0.1, -0.2],
    })
    path = tmp_path / "gp.csv"
    _write_csv(path, data)
    result = load_gp_geocoded(path)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# load_list_sizes
# ---------------------------------------------------------------------------

def test_load_list_sizes_handles_various_column_names(tmp_path):
    data = pd.DataFrame({"PRACTICE_CODE": ["E001"], "TOTAL_LIST_SIZE": [4500]})
    path = tmp_path / "ls.csv"
    _write_csv(path, data)
    result = load_list_sizes(path)
    assert result["list_size"].iloc[0] == 4500


# ---------------------------------------------------------------------------
# compute_weighted_prevalence
# ---------------------------------------------------------------------------

def _make_gp_data(n: int, base_lat: float = 51.5, base_lon: float = -0.1) -> pd.DataFrame:
    """Create n synthetic GP practices spread around a point."""
    disease_cols = list(INDICATOR_FAMILIES.keys())
    rows = []
    for i in range(n):
        row = {
            "practice_code": f"E{i:03d}",
            "gp_lat": base_lat + i * 0.01,
            "gp_lon": base_lon + i * 0.01,
            "list_size": float(1000 + i * 100),
        }
        for col in disease_cols:
            row[col] = 5.0 + i * 0.5  # increasing prevalence with distance
        rows.append(row)
    return pd.DataFrame(rows)


def test_every_lsoa_gets_a_value():
    gp_data = _make_gp_data(TOP_N_PRACTICES + 2)
    lsoa_centroids = pd.DataFrame({
        "LSOA_code": ["E01000001", "E01000002", "E01000003"],
        "lsoa_lat": [51.5, 51.52, 51.48],
        "lsoa_lon": [-0.1, -0.12, -0.08],
    })
    disease_cols = list(INDICATOR_FAMILIES.keys())
    result = compute_weighted_prevalence(lsoa_centroids, gp_data, disease_cols)
    assert len(result) == 3
    for col in disease_cols:
        assert result[col].notna().all(), f"Null values found in {col}"


def test_closer_larger_practice_dominates():
    """A very close, large practice should dominate the weighted average."""
    disease_cols = list(INDICATOR_FAMILIES.keys())
    # One nearby large practice with low prevalence
    # Several distant small practices with high prevalence
    rows = [
        {"practice_code": "NEAR", "gp_lat": 51.5001, "gp_lon": -0.1001, "list_size": 10000.0},
        {"practice_code": "FAR1", "gp_lat": 51.55, "gp_lon": -0.15, "list_size": 100.0},
        {"practice_code": "FAR2", "gp_lat": 51.56, "gp_lon": -0.16, "list_size": 100.0},
        {"practice_code": "FAR3", "gp_lat": 51.57, "gp_lon": -0.17, "list_size": 100.0},
        {"practice_code": "FAR4", "gp_lat": 51.58, "gp_lon": -0.18, "list_size": 100.0},
    ]
    for row in rows:
        for col in disease_cols:
            row[col] = 2.0 if row["practice_code"] == "NEAR" else 50.0

    gp_data = pd.DataFrame(rows)
    lsoa = pd.DataFrame({"LSOA_code": ["E01X"], "lsoa_lat": [51.5], "lsoa_lon": [-0.1]})
    result = compute_weighted_prevalence(lsoa, gp_data, disease_cols)

    for col in disease_cols:
        # Weighted result should be much closer to 2.0 than to 50.0
        assert result[col].iloc[0] < 10.0, f"{col}: expected near-practice to dominate, got {result[col].iloc[0]}"


def test_output_has_required_columns():
    gp_data = _make_gp_data(TOP_N_PRACTICES)
    lsoa = pd.DataFrame({"LSOA_code": ["E01000001"], "lsoa_lat": [51.5], "lsoa_lon": [-0.1]})
    disease_cols = list(INDICATOR_FAMILIES.keys())
    result = compute_weighted_prevalence(lsoa, gp_data, disease_cols)
    assert "LSOA_code" in result.columns
    for col in disease_cols:
        assert col in result.columns

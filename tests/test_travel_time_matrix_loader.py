"""Tests for load_travel_time_matrix in webapp/data_access.py."""

from __future__ import annotations

import pandas as pd
import pytest
from pathlib import Path

from webapp.data_access import load_travel_time_matrix


def _write_parquet(path: Path, df: pd.DataFrame) -> None:
    df.to_parquet(path, index=False)


def _make_matrix_df(n: int = 4) -> pd.DataFrame:
    rows = []
    codes = [f"E{i:09d}" for i in range(n)]
    for o in codes:
        for d in codes:
            rows.append({"origin_lsoa": o, "destination_lsoa": d, "travel_time_minutes": 10.0})
    return pd.DataFrame(rows)


def test_returns_none_for_none_path():
    result = load_travel_time_matrix(None)
    assert result is None


def test_returns_none_for_missing_file(tmp_path):
    result = load_travel_time_matrix(tmp_path / "nonexistent.parquet")
    assert result is None


def test_returns_dict_for_valid_file(tmp_path):
    path = tmp_path / "matrix.parquet"
    _write_parquet(path, _make_matrix_df(3))
    result = load_travel_time_matrix(path)
    assert isinstance(result, dict)


def test_keys_are_origin_destination_tuples(tmp_path):
    path = tmp_path / "matrix.parquet"
    df = pd.DataFrame([
        {"origin_lsoa": "E000000001", "destination_lsoa": "E000000002", "travel_time_minutes": 5.0},
    ])
    _write_parquet(path, df)
    result = load_travel_time_matrix(path)
    assert ("E000000001", "E000000002") in result
    assert result[("E000000001", "E000000002")] == pytest.approx(5.0)


def test_nan_rows_excluded(tmp_path):
    path = tmp_path / "matrix.parquet"
    df = pd.DataFrame([
        {"origin_lsoa": "A", "destination_lsoa": "B", "travel_time_minutes": 12.0},
        {"origin_lsoa": "A", "destination_lsoa": "C", "travel_time_minutes": float("nan")},
    ])
    _write_parquet(path, df)
    result = load_travel_time_matrix(path)
    assert ("A", "B") in result
    assert ("A", "C") not in result


def test_full_matrix_size(tmp_path):
    path = tmp_path / "matrix.parquet"
    n = 5
    _write_parquet(path, _make_matrix_df(n))
    result = load_travel_time_matrix(path)
    assert len(result) == n * n

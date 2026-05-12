"""Tests for assign_travel_time_bands()."""

from __future__ import annotations

import pandas as pd
import pytest

from webapp.analysis import assign_travel_time_bands


def test_four_bands_assigned_correctly():
    matrix = {
        ("HUB", "A"): 5.0,
        ("HUB", "B"): 15.0,
        ("HUB", "C"): 25.0,
        ("HUB", "D"): 35.0,
    }
    codes = pd.Series(["A", "B", "C", "D"])
    result = assign_travel_time_bands(codes, "HUB", matrix)
    assert result.tolist() == ["inner", "middle", "outer", "beyond"]


def test_boundary_values_inclusive():
    # 10 min → inner (boundary), 20 min → middle (boundary), 30 min → outer (boundary)
    matrix = {("H", "A"): 10.0, ("H", "B"): 20.0, ("H", "C"): 30.0}
    codes = pd.Series(["A", "B", "C"])
    result = assign_travel_time_bands(codes, "H", matrix)
    assert result.tolist() == ["inner", "middle", "outer"]


def test_missing_lsoa_becomes_beyond():
    matrix: dict[tuple[str, str], float] = {}
    codes = pd.Series(["UNKNOWN_LSOA"])
    result = assign_travel_time_bands(codes, "HUB", matrix)
    assert result.iloc[0] == "beyond"


def test_host_lsoa_with_zero_travel_time_is_inner():
    matrix = {("HUB", "HUB"): 0.0}
    codes = pd.Series(["HUB"])
    result = assign_travel_time_bands(codes, "HUB", matrix)
    assert result.iloc[0] == "inner"


def test_returns_series_aligned_to_input_index():
    matrix = {("H", "A"): 5.0, ("H", "B"): 25.0}
    codes = pd.Series(["A", "B"], index=[10, 20])
    result = assign_travel_time_bands(codes, "H", matrix)
    assert list(result.index) == [10, 20]
    assert result[10] == "inner"
    assert result[20] == "outer"


def test_empty_series_returns_empty():
    matrix = {("H", "A"): 5.0}
    codes = pd.Series([], dtype=str)
    result = assign_travel_time_bands(codes, "H", matrix)
    assert len(result) == 0

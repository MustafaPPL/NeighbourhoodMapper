"""Tests for the ethnicity LSOA attribution script."""

from __future__ import annotations

import pandas as pd
import pytest
from pathlib import Path

from scripts.analysis.build_ethnicity_lsoa import (
    OUTPUT_COLUMNS,
    load_ts021,
)


def _make_ts021_csv(path: Path, n: int = 5) -> None:
    rows = []
    for i in range(n):
        total = 1000 + i * 100
        rows.append({
            "geography code": f"E0100{i:04d}",
            "geography": f"LSOA {i}",
            "Ethnic group: Total; measures: Value": str(total),
            "Ethnic group: Asian, Asian British or Asian Welsh: Total; measures: Value": str(int(total * 0.15)),
            "Ethnic group: Black, Black British, Black Welsh, Caribbean or African: Total; measures: Value": str(int(total * 0.10)),
            "Ethnic group: Mixed or Multiple ethnic groups: Total; measures: Value": str(int(total * 0.05)),
            "Ethnic group: Other ethnic group: Total; measures: Value": str(int(total * 0.03)),
            "Ethnic group: White: Other White; measures: Value": str(int(total * 0.08)),
        })
    pd.DataFrame(rows).to_csv(path, index=False)


def test_load_ts021_returns_expected_columns(tmp_path):
    path = tmp_path / "ts021.csv"
    _make_ts021_csv(path)
    result = load_ts021(path)
    assert list(result.columns) == OUTPUT_COLUMNS


def test_load_ts021_proportions_in_range(tmp_path):
    path = tmp_path / "ts021.csv"
    _make_ts021_csv(path, n=10)
    result = load_ts021(path)
    for col in OUTPUT_COLUMNS[1:]:
        assert result[col].between(0.0, 1.0).all(), f"{col} has values outside [0, 1]"


def test_load_ts021_correct_row_count(tmp_path):
    path = tmp_path / "ts021.csv"
    _make_ts021_csv(path, n=7)
    result = load_ts021(path)
    assert len(result) == 7


def test_load_ts021_raises_on_missing_geo_column(tmp_path):
    df = pd.DataFrame({"no_geo_col": ["E01000001"], "Ethnic group: Total; measures: Value": ["1000"]})
    path = tmp_path / "ts021.csv"
    df.to_csv(path, index=False)
    with pytest.raises(ValueError, match="geography code"):
        load_ts021(path)


def test_load_ts021_raises_on_missing_group_column(tmp_path):
    df = pd.DataFrame({
        "geography code": ["E01000001"],
        "geography": ["LSOA A"],
        "Ethnic group: Total; measures: Value": ["1000"],
        # Asian column deliberately missing
        "Ethnic group: Black, Black British, Black Welsh, Caribbean or African: Total; measures: Value": ["100"],
        "Ethnic group: Mixed or Multiple ethnic groups: Total; measures: Value": ["50"],
        "Ethnic group: Other ethnic group: Total; measures: Value": ["30"],
        "Ethnic group: White: Other White; measures: Value": ["80"],
    })
    path = tmp_path / "ts021.csv"
    df.to_csv(path, index=False)
    with pytest.raises(ValueError, match="pct_asian_residents"):
        load_ts021(path)


def test_load_ts021_filters_non_lsoa_rows(tmp_path):
    rows = [
        {
            "geography code": "E01000001",
            "geography": "LSOA 1",
            "Ethnic group: Total; measures: Value": "1000",
            "Ethnic group: Asian, Asian British or Asian Welsh: Total; measures: Value": "150",
            "Ethnic group: Black, Black British, Black Welsh, Caribbean or African: Total; measures: Value": "100",
            "Ethnic group: Mixed or Multiple ethnic groups: Total; measures: Value": "50",
            "Ethnic group: Other ethnic group: Total; measures: Value": "30",
            "Ethnic group: White: Other White; measures: Value": "80",
        },
        {
            "geography code": "K04000001",  # National total — not an LSOA
            "geography": "England and Wales",
            "Ethnic group: Total; measures: Value": "59000000",
            "Ethnic group: Asian, Asian British or Asian Welsh: Total; measures: Value": "5000000",
            "Ethnic group: Black, Black British, Black Welsh, Caribbean or African: Total; measures: Value": "2000000",
            "Ethnic group: Mixed or Multiple ethnic groups: Total; measures: Value": "1000000",
            "Ethnic group: Other ethnic group: Total; measures: Value": "500000",
            "Ethnic group: White: Other White; measures: Value": "3000000",
        },
    ]
    path = tmp_path / "ts021.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    result = load_ts021(path)
    assert len(result) == 1
    assert result["LSOA_code"].iloc[0] == "E01000001"


def test_load_ts021_deduplicates_lsoa(tmp_path):
    rows = []
    base = {
        "geography code": "E01000001",
        "geography": "LSOA 1",
        "Ethnic group: Total; measures: Value": "1000",
        "Ethnic group: Asian, Asian British or Asian Welsh: Total; measures: Value": "150",
        "Ethnic group: Black, Black British, Black Welsh, Caribbean or African: Total; measures: Value": "100",
        "Ethnic group: Mixed or Multiple ethnic groups: Total; measures: Value": "50",
        "Ethnic group: Other ethnic group: Total; measures: Value": "30",
        "Ethnic group: White: Other White; measures: Value": "80",
    }
    rows = [base, base]
    path = tmp_path / "ts021.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    result = load_ts021(path)
    assert len(result) == 1

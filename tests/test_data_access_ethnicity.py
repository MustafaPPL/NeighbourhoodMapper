"""Tests for ethnicity data loader in webapp/data_access.py."""

from __future__ import annotations

import pandas as pd
import pytest
from pathlib import Path

from webapp.data_access import load_ethnicity_data, _ETHNICITY_COLUMNS


def _write_eth_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False)


def _valid_eth_df(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame({
        "LSOA_code": [f"E0100{i:04d}" for i in range(n)],
        "pct_asian_residents": [0.15 + i * 0.01 for i in range(n)],
        "pct_black_residents": [0.10 + i * 0.01 for i in range(n)],
        "pct_mixed_residents": [0.05 + i * 0.01 for i in range(n)],
        "pct_other_ethnic_group_residents": [0.03 + i * 0.01 for i in range(n)],
        "pct_white_other_residents": [0.08 + i * 0.01 for i in range(n)],
    })


def test_load_ethnicity_data_returns_expected_columns(tmp_path):
    path = tmp_path / "eth.csv"
    _write_eth_csv(path, _valid_eth_df())
    result = load_ethnicity_data(path)
    assert list(result.columns) == _ETHNICITY_COLUMNS


def test_load_ethnicity_data_numeric_proportions(tmp_path):
    path = tmp_path / "eth.csv"
    _write_eth_csv(path, _valid_eth_df(5))
    result = load_ethnicity_data(path)
    for col in _ETHNICITY_COLUMNS[1:]:
        assert pd.api.types.is_float_dtype(result[col]), f"{col} should be float"


def test_load_ethnicity_data_raises_on_missing_column(tmp_path):
    df = _valid_eth_df().drop(columns=["pct_black_residents"])
    path = tmp_path / "eth.csv"
    _write_eth_csv(path, df)
    with pytest.raises(ValueError, match="pct_black_residents"):
        load_ethnicity_data(path)


def test_load_ethnicity_data_drops_duplicate_lsoa(tmp_path):
    df = _valid_eth_df(3)
    df = pd.concat([df, df.iloc[:1]], ignore_index=True)
    path = tmp_path / "eth.csv"
    _write_eth_csv(path, df)
    result = load_ethnicity_data(path)
    assert len(result) == 3
    assert result["LSOA_code"].is_unique


def test_load_ethnicity_data_coerces_non_numeric_to_nan(tmp_path):
    path = tmp_path / "eth.csv"
    path.write_text(
        "LSOA_code,pct_asian_residents,pct_black_residents,pct_mixed_residents,"
        "pct_other_ethnic_group_residents,pct_white_other_residents\n"
        "E01000001,N/A,0.10,0.05,0.03,0.08\n"
        "E01000002,0.16,0.11,0.06,0.04,0.09\n"
    )
    result = load_ethnicity_data(path)
    assert pd.isna(result.loc[result["LSOA_code"] == "E01000001", "pct_asian_residents"].iloc[0])

"""Tests for QOF data loader in webapp/data_access.py."""

from __future__ import annotations

import pandas as pd
import pytest
from pathlib import Path

from webapp.data_access import load_qof_data, _QOF_COLUMNS


def _write_qof_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False)


def _valid_qof_df(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame({
        "LSOA_code": [f"E0100{i:04d}" for i in range(n)],
        "qof_chd_prevalence": [5.0 + i for i in range(n)],
        "qof_copd_prevalence": [3.0 + i for i in range(n)],
        "qof_diabetes_prevalence": [7.0 + i for i in range(n)],
        "qof_depression_prevalence": [10.0 + i for i in range(n)],
    })


def test_load_qof_data_returns_expected_columns(tmp_path):
    path = tmp_path / "qof_lsoa.csv"
    _write_qof_csv(path, _valid_qof_df())
    result = load_qof_data(path)
    assert list(result.columns) == _QOF_COLUMNS


def test_load_qof_data_numeric_prevalence(tmp_path):
    path = tmp_path / "qof_lsoa.csv"
    _write_qof_csv(path, _valid_qof_df(5))
    result = load_qof_data(path)
    for col in _QOF_COLUMNS[1:]:
        assert pd.api.types.is_float_dtype(result[col]), f"{col} should be float"


def test_load_qof_data_raises_on_missing_column(tmp_path):
    df = _valid_qof_df()
    df = df.drop(columns=["qof_chd_prevalence"])
    path = tmp_path / "qof_lsoa.csv"
    _write_qof_csv(path, df)
    with pytest.raises(ValueError, match="qof_chd_prevalence"):
        load_qof_data(path)


def test_load_qof_data_drops_duplicate_lsoa(tmp_path):
    df = _valid_qof_df(3)
    df = pd.concat([df, df.iloc[:1]], ignore_index=True)
    path = tmp_path / "qof_lsoa.csv"
    _write_qof_csv(path, df)
    result = load_qof_data(path)
    assert len(result) == 3
    assert result["LSOA_code"].is_unique


def test_load_qof_data_coerces_non_numeric_to_nan(tmp_path):
    path = tmp_path / "qof_lsoa.csv"
    path.write_text(
        "LSOA_code,qof_chd_prevalence,qof_copd_prevalence,qof_diabetes_prevalence,qof_depression_prevalence\n"
        "E01000001,N/A,3.0,7.0,10.0\n"
        "E01000002,6.0,4.0,8.0,11.0\n"
    )
    result = load_qof_data(path)
    assert pd.isna(result.loc[result["LSOA_code"] == "E01000001", "qof_chd_prevalence"].iloc[0])

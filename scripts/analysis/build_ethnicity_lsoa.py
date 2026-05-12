"""
Build LSOA-level ethnicity proportion estimates from Census 2021 TS021.

Expected input
--------------
ONS TS021 CSV (--ts021-csv):
    Downloaded from Nomis (reference C2021TS021), bulk download for LSOAs.
    Typically produced by Nomis with headers like:
        "geography code"           - LSOA 2021 code
        "Ethnic group: Total; measures: Value"
        "Ethnic group: Asian, Asian British or Asian Welsh: Total; measures: Value"
        "Ethnic group: Black, Black British, Black Welsh, Caribbean or African: Total; measures: Value"
        "Ethnic group: Mixed or Multiple ethnic groups: Total; measures: Value"
        "Ethnic group: Other ethnic group: Total; measures: Value"
        "Ethnic group: White: Other White; measures: Value"

Output
------
data/cache/ethnicity_lsoa_2021.csv
Columns: LSOA_code, pct_asian_residents, pct_black_residents,
         pct_mixed_residents, pct_other_ethnic_group_residents,
         pct_white_other_residents
All proportions are in [0.0, 1.0].
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "cache"
DEFAULT_OUTPUT_NAME = "ethnicity_lsoa_2021.csv"

ETHNICITY_GROUPS = {
    "pct_asian_residents": ["asian, asian british", "asian or asian british", "asian british or asian welsh"],
    "pct_black_residents": ["black, black british", "black or black british", "black british, black welsh"],
    "pct_mixed_residents": ["mixed or multiple", "mixed: total", "mixed or multiple ethnic"],
    "pct_other_ethnic_group_residents": ["other ethnic group"],
    "pct_white_other_residents": ["other white", "white: other white", "white other"],
}

OUTPUT_COLUMNS = [
    "LSOA_code",
    "pct_asian_residents",
    "pct_black_residents",
    "pct_mixed_residents",
    "pct_other_ethnic_group_residents",
    "pct_white_other_residents",
]


def _normalise(text: str) -> str:
    return text.strip().lower()


def _detect_geo_column(columns: list[str]) -> str | None:
    priority = ["geography code", "geography_code", "lsoa21cd", "lsoa_code", "geo_code", "code"]
    norm = {_normalise(c): c for c in columns}
    for candidate in priority:
        if candidate in norm:
            return norm[candidate]
    for col in columns:
        if "geography" in _normalise(col) and "code" in _normalise(col):
            return col
    return None


def _detect_total_column(columns: list[str]) -> str | None:
    norm_cols = [_normalise(c) for c in columns]
    for i, norm in enumerate(norm_cols):
        if (
            "total" in norm
            and "ethnic" in norm
            and "asian" not in norm
            and "black" not in norm
            and "mixed" not in norm
            and "other" not in norm
            and "white" not in norm
        ):
            return columns[i]
    for col in columns:
        if _normalise(col) in ("total", "all usual residents"):
            return col
    return None


def _detect_group_column(columns: list[str], keywords: list[str]) -> str | None:
    norm_cols = [(_normalise(c), c) for c in columns]
    for keyword in keywords:
        for norm, original in norm_cols:
            if keyword in norm:
                return original
    return None


def load_ts021(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()

    geo_col = _detect_geo_column(list(df.columns))
    if geo_col is None:
        raise ValueError(
            f"Could not find geography code column in TS021 CSV. "
            f"Available columns: {list(df.columns)[:10]}"
        )

    total_col = _detect_total_column(list(df.columns))
    if total_col is None:
        raise ValueError(
            f"Could not find total population column in TS021 CSV. "
            f"Available columns: {list(df.columns)[:10]}"
        )

    group_cols: dict[str, str] = {}
    missing_groups: list[str] = []
    for output_col, keywords in ETHNICITY_GROUPS.items():
        matched = _detect_group_column(list(df.columns), keywords)
        if matched is None:
            missing_groups.append(output_col)
        else:
            group_cols[output_col] = matched

    if missing_groups:
        raise ValueError(
            f"Could not find columns for ethnic groups: {missing_groups}. "
            f"Available columns: {list(df.columns)}"
        )

    df = df.rename(columns={geo_col: "LSOA_code"})
    df["LSOA_code"] = df["LSOA_code"].str.strip()
    df["_total"] = pd.to_numeric(df[total_col], errors="coerce")

    lsoa_mask = df["LSOA_code"].str.match(r"^E[0-9]", na=False)
    df = df[lsoa_mask].copy()

    result = df[["LSOA_code", "_total"]].copy()
    for output_col, source_col in group_cols.items():
        group_count = pd.to_numeric(df[source_col], errors="coerce")
        result[output_col] = (group_count / df["_total"]).clip(0.0, 1.0)

    result = result.drop(columns=["_total"])
    result = result.dropna(subset=["LSOA_code"]).drop_duplicates("LSOA_code")
    return result.loc[:, OUTPUT_COLUMNS]


def build_ethnicity_lsoa(ts021_csv: Path, output_dir: Path) -> Path:
    print(f"Loading TS021 Census 2021 ethnicity data from {ts021_csv}...")
    result = load_ts021(ts021_csv)
    print(f"  {len(result)} LSOAs with ethnicity data")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / DEFAULT_OUTPUT_NAME
    result.to_csv(output_path, index=False)

    null_counts = result[OUTPUT_COLUMNS[1:]].isna().sum()
    print(f"\nProcessed {len(result)} LSOAs")
    for col, n in null_counts.items():
        print(f"  {col}: {n} null values")
    print(f"\nOutput: {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build LSOA-level ethnicity proportions from Census 2021 TS021."
    )
    parser.add_argument(
        "--ts021-csv",
        required=True,
        type=Path,
        help="ONS TS021 CSV downloaded from Nomis (bulk LSOA download)",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        type=Path,
        help="Output directory (default: data/cache/)",
    )
    args = parser.parse_args()
    build_ethnicity_lsoa(args.ts021_csv, args.output_dir)


if __name__ == "__main__":
    main()

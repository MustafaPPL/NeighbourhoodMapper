"""
Build LSOA-level QOF disease prevalence estimates.

Expected inputs
---------------
Four NHS England QOF 2024-25 practice-level Excel workbooks (--chd-xlsx etc.):
    data/qof/data/qof-2425-prev-ach-pca-cv-prac.xlsx    sheet "CHD"
    data/qof/data/qof-2425-prev-ach-pca-resp-prac.xlsx  sheet "COPD"
    data/qof/data/qof-2425-prev-ach-pca-hd-prac.xlsx    sheet "DM"
    data/qof/data/qof-2425-prev-ach-pca-neu-prac.xlsx   sheet "DEP"

Each sheet has a header at row 11 (0-indexed).  Columns used:
    "Practice code"   GP ODS code (e.g. "A84006")
    "Prevalence (%)"  Crude prevalence rate (0–100 %)

GP list size CSV (--list-size-csv):
    Columns: CODE, SEX, AGE, NUMBER_OF_PATIENTS
    NHS England GP registered patients publication.
    Rows filtered to SEX=ALL, AGE=ALL.

GP geocoded CSV (--gp-csv):
    Columns: "Practice code", Latitude, Longitude
    Default: data/primary_care/gp_practices_tomtom_geocoded.csv

LSOA centroids CSV (--lsoa-csv, optional):
    Columns: LSOA_code, latitude, longitude

Output
------
data/cache/qof_lsoa_{year}.csv
Columns: LSOA_code, qof_chd_prevalence, qof_copd_prevalence,
         qof_diabetes_prevalence, qof_depression_prevalence

Attribution method
------------------
For each LSOA centroid the 5 nearest GP practices are identified.
Each practice contributes a weight = list_size / distance_km^2.
LSOA prevalence = sum(weight * prevalence) / sum(weight)
Every LSOA receives a value (no hard radius cutoff).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GP_CSV = ROOT / "data" / "primary_care" / "gp_practices_tomtom_geocoded.csv"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "cache"
DEFAULT_YEAR = "2024-25"

# Default Excel paths (data downloaded from NHS England QOF 2024-25 publication)
_QOF_DATA_DIR = ROOT / "data" / "qof" / "data"
DEFAULT_CHD_XLSX  = _QOF_DATA_DIR / "qof-2425-prev-ach-pca-cv-prac.xlsx"
DEFAULT_COPD_XLSX = _QOF_DATA_DIR / "qof-2425-prev-ach-pca-resp-prac.xlsx"
DEFAULT_DM_XLSX   = _QOF_DATA_DIR / "qof-2425-prev-ach-pca-hd-prac.xlsx"
DEFAULT_DEP_XLSX  = _QOF_DATA_DIR / "qof-2425-prev-ach-pca-neu-prac.xlsx"
DEFAULT_LIST_SIZE_CSV = ROOT / "data" / "qof" / "gp-reg-pat-prac-all.csv"

# Sheet name for each indicator workbook
_SHEET_MAP = {
    "qof_chd_prevalence":        ("CHD",  DEFAULT_CHD_XLSX),
    "qof_copd_prevalence":       ("COPD", DEFAULT_COPD_XLSX),
    "qof_diabetes_prevalence":   ("DM",   DEFAULT_DM_XLSX),
    "qof_depression_prevalence": ("DEP",  DEFAULT_DEP_XLSX),
}

INDICATOR_FAMILIES = {
    "qof_chd_prevalence": "CHD",
    "qof_copd_prevalence": "COPD",
    "qof_diabetes_prevalence": "DM",
    "qof_depression_prevalence": "DEP",
}

TOP_N_PRACTICES = 5
_EXCEL_HEADER_ROW = 11  # 0-indexed row where column names appear in each QOF sheet


# ---------------------------------------------------------------------------
# Distance helpers
# ---------------------------------------------------------------------------

def _haversine_km(lat1: np.ndarray, lon1: np.ndarray,
                  lat2: float, lon2: float) -> np.ndarray:
    r = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2) ** 2
    return r * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _detect_col(columns: list[str], candidates: list[str]) -> str | None:
    norm = {c.strip().lower().replace(" ", "_"): c for c in columns}
    for candidate in candidates:
        match = norm.get(candidate.strip().lower().replace(" ", "_"))
        if match is not None:
            return match
    return None


def load_qof_prevalence(path: Path) -> pd.DataFrame:
    """Load QOF prevalence from a long-format CSV (PRACTICE_CODE, INDICATOR_CODE, PREVALENCE).

    Returns DataFrame with columns: practice_code, plus one column per disease family.
    """
    df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.strip()

    practice_col  = _detect_col(list(df.columns), ["PRACTICE_CODE", "Practice code", "ORG_CODE"])
    indicator_col = _detect_col(list(df.columns), ["INDICATOR_CODE", "INDICATOR CODE"])
    prevalence_col = _detect_col(list(df.columns), ["PREVALENCE", "PREV_RATE", "CRUDE_RATE"])

    if not practice_col or not indicator_col or not prevalence_col:
        missing = []
        if not practice_col:
            missing.append("PRACTICE_CODE")
        if not indicator_col:
            missing.append("INDICATOR_CODE")
        if not prevalence_col:
            missing.append("PREVALENCE")
        raise ValueError(f"Missing required columns in QOF CSV: {missing}. Available: {list(df.columns)}")

    df = df.rename(columns={practice_col: "practice_code", indicator_col: "indicator_code", prevalence_col: "prevalence"})
    df["practice_code"] = df["practice_code"].str.strip().str.upper()
    df["prevalence"] = pd.to_numeric(df["prevalence"], errors="coerce")

    records = []
    for output_col, prefix in INDICATOR_FAMILIES.items():
        family = df[df["indicator_code"].str.upper().str.startswith(prefix)].copy()
        agg = family.groupby("practice_code", as_index=False)["prevalence"].mean()
        agg = agg.rename(columns={"prevalence": output_col})
        records.append(agg)

    if not records:
        raise ValueError("No indicator rows matched the expected prefixes (CHD, COPD, DM, DEP).")

    result = records[0]
    for extra in records[1:]:
        result = result.merge(extra, on="practice_code", how="outer")
    return result


def load_qof_prevalence_excel(
    chd_xlsx: Path,
    copd_xlsx: Path,
    dm_xlsx: Path,
    dep_xlsx: Path,
) -> pd.DataFrame:
    """Load QOF prevalence from the four NHS England 2024-25 Excel workbooks.

    Returns DataFrame with columns: practice_code, plus one prevalence column per disease.
    """
    sources = {
        "qof_chd_prevalence":        ("CHD",  chd_xlsx),
        "qof_copd_prevalence":       ("COPD", copd_xlsx),
        "qof_diabetes_prevalence":   ("DM",   dm_xlsx),
        "qof_depression_prevalence": ("DEP",  dep_xlsx),
    }

    frames: list[pd.DataFrame] = []
    for output_col, (sheet, path) in sources.items():
        df = pd.read_excel(path, sheet_name=sheet, header=_EXCEL_HEADER_ROW)
        df.columns = df.columns.str.strip()

        practice_col = _detect_col(list(df.columns), ["Practice code", "PRACTICE_CODE"])
        prev_col = next((c for c in df.columns if "prevalence" in c.lower()), None)

        if not practice_col or not prev_col:
            raise ValueError(
                f"Sheet '{sheet}' in {path.name} is missing expected columns. "
                f"Found: {list(df.columns[:12])}"
            )

        sub = df[[practice_col, prev_col]].copy()
        sub.columns = ["practice_code", output_col]
        sub["practice_code"] = sub["practice_code"].astype(str).str.strip().str.upper()
        sub[output_col] = pd.to_numeric(sub[output_col], errors="coerce")
        sub = sub.dropna(subset=["practice_code"]).query("practice_code != 'NAN'")
        frames.append(sub)

    result = frames[0]
    for extra in frames[1:]:
        result = result.merge(extra, on="practice_code", how="outer")
    return result


def load_gp_geocoded(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.strip()

    code_col = _detect_col(list(df.columns), ["Practice code", "PRACTICE_CODE", "ODS_CODE"])
    lat_col  = _detect_col(list(df.columns), ["Latitude", "LAT", "latitude"])
    lon_col  = _detect_col(list(df.columns), ["Longitude", "LON", "longitude"])

    if not code_col or not lat_col or not lon_col:
        raise ValueError(f"GP geocoded CSV missing required columns. Found: {list(df.columns)}")

    df = df.rename(columns={code_col: "practice_code", lat_col: "gp_lat", lon_col: "gp_lon"})
    df["practice_code"] = df["practice_code"].str.strip().str.upper()
    df["gp_lat"] = pd.to_numeric(df["gp_lat"], errors="coerce")
    df["gp_lon"] = pd.to_numeric(df["gp_lon"], errors="coerce")
    return df[["practice_code", "gp_lat", "gp_lon"]].dropna()


def load_list_sizes(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.strip()

    code_col = _detect_col(list(df.columns), ["CODE", "PRACTICE_CODE", "Practice code", "ORG_CODE"])
    size_col = _detect_col(list(df.columns), ["NUMBER_OF_PATIENTS", "TOTAL_LIST_SIZE", "LIST_SIZE", "REGISTERED_PATIENTS"])

    if not code_col or not size_col:
        raise ValueError(f"List size CSV missing required columns. Found: {list(df.columns)}")

    # Filter to total population row (avoids double-counting age/sex breakdowns)
    if "SEX" in df.columns and "AGE" in df.columns:
        df = df[(df["SEX"].str.upper() == "ALL") & (df["AGE"].str.upper() == "ALL")]

    df = df.rename(columns={code_col: "practice_code", size_col: "list_size"})
    df["practice_code"] = df["practice_code"].str.strip().str.upper()
    df["list_size"] = pd.to_numeric(df["list_size"], errors="coerce")
    return df[["practice_code", "list_size"]].dropna()


def load_lsoa_centroids(lsoa_csv: Path | None) -> pd.DataFrame:
    if lsoa_csv is not None:
        df = pd.read_csv(lsoa_csv, dtype=str)
        df.columns = df.columns.str.strip()
        code_col = _detect_col(list(df.columns), ["LSOA_code", "LSOA21CD", "LSOA_CODE"])
        lat_col  = _detect_col(list(df.columns), ["latitude", "lat", "LAT"])
        lon_col  = _detect_col(list(df.columns), ["longitude", "lon", "LON"])
        if not code_col or not lat_col or not lon_col:
            raise ValueError(f"LSOA CSV missing columns. Found: {list(df.columns)}")
        df = df.rename(columns={code_col: "LSOA_code", lat_col: "lsoa_lat", lon_col: "lsoa_lon"})
        df["lsoa_lat"] = pd.to_numeric(df["lsoa_lat"], errors="coerce")
        df["lsoa_lon"] = pd.to_numeric(df["lsoa_lon"], errors="coerce")
        return df[["LSOA_code", "lsoa_lat", "lsoa_lon"]].dropna()

    # Fetch London LSOA boundaries from ArcGIS and compute centroids
    try:
        from scripts.analysis.build_weighted_priority_map import fetch_london_lsoa_boundaries  # noqa: PLC0415
        lsoa_gdf, _, _ = fetch_london_lsoa_boundaries()
        lsoa_gdf = lsoa_gdf.to_crs("EPSG:4326")
        lsoa_gdf["lsoa_lat"] = lsoa_gdf.geometry.centroid.y
        lsoa_gdf["lsoa_lon"] = lsoa_gdf.geometry.centroid.x
        return lsoa_gdf[["LSOA_code", "lsoa_lat", "lsoa_lon"]].dropna()
    except Exception as exc:
        print(f"ERROR: Could not load LSOA centroids from ArcGIS: {exc}", file=sys.stderr)
        print("Provide a local LSOA centroids CSV with --lsoa-csv LSOA_code,latitude,longitude", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------

def compute_weighted_prevalence(
    lsoa_centroids: pd.DataFrame,
    gp_data: pd.DataFrame,
    disease_cols: list[str],
) -> pd.DataFrame:
    gp_lats  = gp_data["gp_lat"].to_numpy()
    gp_lons  = gp_data["gp_lon"].to_numpy()
    gp_sizes = gp_data["list_size"].to_numpy(dtype=float)
    gp_prev  = {col: gp_data[col].to_numpy(dtype=float) for col in disease_cols}

    result_rows = []
    for _, row in lsoa_centroids.iterrows():
        distances = _haversine_km(gp_lats, gp_lons, row["lsoa_lat"], row["lsoa_lon"])
        distances = np.maximum(distances, 0.05)  # avoid division by zero

        top_n_idx = np.argsort(distances)[:TOP_N_PRACTICES]
        top_d     = distances[top_n_idx]
        top_sizes = gp_sizes[top_n_idx]
        weights   = top_sizes / (top_d ** 2)

        record: dict[str, object] = {"LSOA_code": row["LSOA_code"]}
        for col in disease_cols:
            top_prev = gp_prev[col][top_n_idx]
            valid = ~np.isnan(top_prev)
            if valid.any():
                w = weights[valid]
                p = top_prev[valid]
                record[col] = float((w * p).sum() / w.sum()) if w.sum() > 0 else float("nan")
            else:
                record[col] = float("nan")
        result_rows.append(record)

    return pd.DataFrame(result_rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_qof_lsoa(
    chd_xlsx: Path,
    copd_xlsx: Path,
    dm_xlsx: Path,
    dep_xlsx: Path,
    gp_csv: Path,
    list_size_csv: Path,
    lsoa_csv: Path | None,
    year: str,
    output_dir: Path,
) -> Path:
    print("Loading QOF prevalence data from Excel workbooks...")
    qof = load_qof_prevalence_excel(chd_xlsx, copd_xlsx, dm_xlsx, dep_xlsx)
    print(f"  {len(qof)} practices with QOF data")

    print("Loading GP geocoded data...")
    gp_geo = load_gp_geocoded(gp_csv)
    print(f"  {len(gp_geo)} practices with coordinates")

    print("Loading GP list sizes...")
    list_sizes = load_list_sizes(list_size_csv)
    print(f"  {len(list_sizes)} practices with list sizes")

    gp_data = gp_geo.merge(list_sizes, on="practice_code", how="inner")
    gp_data = gp_data.merge(qof, on="practice_code", how="inner")
    gp_data = gp_data.dropna(subset=["gp_lat", "gp_lon", "list_size"])
    print(f"  {len(gp_data)} practices with all required data after joining")

    if len(gp_data) < TOP_N_PRACTICES:
        print(f"WARNING: Only {len(gp_data)} practices; need at least {TOP_N_PRACTICES}.", file=sys.stderr)

    disease_cols = list(INDICATOR_FAMILIES.keys())

    print("Loading LSOA centroids...")
    lsoa_centroids = load_lsoa_centroids(lsoa_csv)
    print(f"  {len(lsoa_centroids)} LSOAs")

    print(f"Computing weighted prevalence (top-{TOP_N_PRACTICES} nearest, weight=list_size/d²)...")
    result = compute_weighted_prevalence(lsoa_centroids, gp_data, disease_cols)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"qof_lsoa_{year}.csv"
    result.to_csv(output_path, index=False)

    null_counts = result[disease_cols].isna().sum()
    print(f"\nProcessed {len(result)} LSOAs")
    for col, n in null_counts.items():
        print(f"  {col}: {n} null values")
    print(f"\nOutput: {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build LSOA-level QOF disease prevalence estimates.")
    parser.add_argument("--chd-xlsx",  default=DEFAULT_CHD_XLSX,  type=Path, help="QOF cardiovascular workbook (CHD sheet)")
    parser.add_argument("--copd-xlsx", default=DEFAULT_COPD_XLSX, type=Path, help="QOF respiratory workbook (COPD sheet)")
    parser.add_argument("--dm-xlsx",   default=DEFAULT_DM_XLSX,   type=Path, help="QOF metabolic workbook (DM sheet)")
    parser.add_argument("--dep-xlsx",  default=DEFAULT_DEP_XLSX,  type=Path, help="QOF mental health workbook (DEP sheet)")
    parser.add_argument("--gp-csv",       default=DEFAULT_GP_CSV,       type=Path, help="GP geocoded CSV")
    parser.add_argument("--list-size-csv", default=DEFAULT_LIST_SIZE_CSV, type=Path, help="GP list size CSV")
    parser.add_argument("--lsoa-csv",  default=None, type=Path, help="LSOA centroids CSV (optional; fetched from ArcGIS if omitted)")
    parser.add_argument("--year",       default=DEFAULT_YEAR, help="QOF reporting year (used in output filename)")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, type=Path, help="Output directory")
    args = parser.parse_args()
    build_qof_lsoa(
        args.chd_xlsx, args.copd_xlsx, args.dm_xlsx, args.dep_xlsx,
        args.gp_csv, args.list_size_csv, args.lsoa_csv, args.year, args.output_dir,
    )


if __name__ == "__main__":
    main()

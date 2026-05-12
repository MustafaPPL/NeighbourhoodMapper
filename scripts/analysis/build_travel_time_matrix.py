"""
Build LSOA-to-LSOA travel time matrix using OSRM (walking mode).

For transit mode, use the R5 Docker setup in scripts/analysis/r5/.

Expected input (optional)
--------------------------
LSOA centroids CSV (--lsoa-csv):
    Columns: LSOA_code, latitude, longitude
    If omitted, centroids are fetched from the ArcGIS LSOA boundaries service
    and computed automatically.

Output
------
data/cache/travel_time_walking.parquet
Columns: origin_lsoa, destination_lsoa, travel_time_minutes (float, NaN = no route)

Method
------
The OSRM /table endpoint is queried in chunks (--chunk-size sources ×
--chunk-size destinations per request). A short delay between requests
avoids overwhelming the public endpoint. For large datasets or production
use, supply --osrm-url pointing at a local OSRM instance.

Usage
-----
    # Walking matrix (public OSRM):
    python scripts/analysis/build_travel_time_matrix.py --mode walking

    # Walking matrix with local OSRM:
    python scripts/analysis/build_travel_time_matrix.py --mode walking \\
        --osrm-url http://localhost:5000

    # Transit: use scripts/analysis/r5/ instead.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "cache"
OSRM_PUBLIC_URL = "https://router.project-osrm.org"
REQUEST_TIMEOUT = 30
USER_AGENT = "LondonHubRanker/1.0 (+python requests)"
DEFAULT_CHUNK_SIZE = 200
REQUEST_DELAY_S = 0.25


def _load_lsoa_centroids(lsoa_csv: Path | None) -> pd.DataFrame:
    if lsoa_csv is not None:
        df = pd.read_csv(lsoa_csv, dtype=str)
        df.columns = df.columns.str.strip()
        code_col = next(
            (c for c in df.columns if c.lower() in {"lsoa_code", "lsoa21cd", "lsoa_code_2021", "geography code"}),
            None,
        )
        lat_col = next((c for c in df.columns if c.lower() in {"latitude", "lat"}), None)
        lon_col = next((c for c in df.columns if c.lower() in {"longitude", "lon", "long"}), None)
        if not code_col or not lat_col or not lon_col:
            raise ValueError(
                f"LSOA CSV must have LSOA_code, latitude, and longitude columns. Found: {list(df.columns)}"
            )
        df = df.rename(columns={code_col: "LSOA_code", lat_col: "lat", lon_col: "lon"})
        df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
        df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
        return df[["LSOA_code", "lat", "lon"]].dropna()

    print("  Fetching LSOA boundaries from ArcGIS and computing centroids...")
    try:
        from scripts.analysis.build_weighted_priority_map import fetch_london_lsoa_boundaries  # noqa: PLC0415
        lsoa_gdf, _, _ = fetch_london_lsoa_boundaries()
        lsoa_gdf = lsoa_gdf.to_crs("EPSG:4326")
        centroids = lsoa_gdf.geometry.centroid
        lsoa_code_col = next(
            (c for c in lsoa_gdf.columns if "lsoa" in c.lower() and "code" in c.lower()), None
        )
        if lsoa_code_col is None:
            raise ValueError("No LSOA code column found in ArcGIS data.")
        df = pd.DataFrame({
            "LSOA_code": lsoa_gdf[lsoa_code_col].astype(str),
            "lat": centroids.y,
            "lon": centroids.x,
        })
        return df.dropna()
    except Exception as exc:
        print(f"ERROR: Could not load LSOA centroids from ArcGIS: {exc}", file=sys.stderr)
        print("Provide a local LSOA centroids CSV with --lsoa-csv LSOA_code,latitude,longitude", file=sys.stderr)
        sys.exit(1)


def _query_osrm_table(
    coords: list[tuple[str, float, float]],
    source_indices: list[int],
    dest_indices: list[int],
    osrm_url: str,
) -> list[list[float | None]]:
    """Query the OSRM table endpoint. Returns duration matrix in seconds."""
    coord_str = ";".join(f"{lon:.6f},{lat:.6f}" for _, lat, lon in coords)
    src_str = ";".join(str(i) for i in source_indices)
    dst_str = ";".join(str(i) for i in dest_indices)
    url = f"{osrm_url.rstrip('/')}/table/v1/foot/{coord_str}?sources={src_str}&destinations={dst_str}&annotations=duration"

    resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok":
        raise ValueError(f"OSRM returned code={data.get('code')}: {data.get('message', 'unknown error')}")
    return data["durations"]


def build_walking_matrix(
    centroids: pd.DataFrame,
    osrm_url: str,
    chunk_size: int,
) -> pd.DataFrame:
    lsoa_codes = centroids["LSOA_code"].tolist()
    lats = centroids["lat"].tolist()
    lons = centroids["lon"].tolist()
    n = len(lsoa_codes)

    chunks = [list(range(i, min(i + chunk_size, n))) for i in range(0, n, chunk_size)]
    total_requests = len(chunks) ** 2
    print(f"  {n} LSOAs, chunk size {chunk_size} → {len(chunks)} chunks, {total_requests} requests")
    print(f"  Using OSRM endpoint: {osrm_url}")

    rows: list[dict[str, object]] = []
    request_num = 0
    for src_chunk in chunks:
        for dst_chunk in chunks:
            request_num += 1
            if request_num % 100 == 0:
                pct = request_num / total_requests * 100
                print(f"  [{request_num}/{total_requests}] {pct:.1f}% complete...")

            src_coords = [(lsoa_codes[i], lats[i], lons[i]) for i in src_chunk]
            dst_coords = [(lsoa_codes[i], lats[i], lons[i]) for i in dst_chunk]

            all_coords = src_coords + dst_coords
            src_indices = list(range(len(src_coords)))
            dst_indices = list(range(len(src_coords), len(src_coords) + len(dst_coords)))

            try:
                durations = _query_osrm_table(all_coords, src_indices, dst_indices, osrm_url)
                for row_idx, src_lsoa_idx in enumerate(src_chunk):
                    for col_idx, dst_lsoa_idx in enumerate(dst_chunk):
                        raw = durations[row_idx][col_idx]
                        travel_minutes = float(raw / 60.0) if raw is not None else float("nan")
                        rows.append({
                            "origin_lsoa": lsoa_codes[src_lsoa_idx],
                            "destination_lsoa": lsoa_codes[dst_lsoa_idx],
                            "travel_time_minutes": travel_minutes,
                        })
            except Exception as exc:
                print(f"  WARNING: Request {request_num} failed: {exc}. Filling with NaN.", file=sys.stderr)
                for src_lsoa_idx in src_chunk:
                    for dst_lsoa_idx in dst_chunk:
                        rows.append({
                            "origin_lsoa": lsoa_codes[src_lsoa_idx],
                            "destination_lsoa": lsoa_codes[dst_lsoa_idx],
                            "travel_time_minutes": float("nan"),
                        })

            if REQUEST_DELAY_S > 0:
                time.sleep(REQUEST_DELAY_S)

    return pd.DataFrame(rows)


def build_travel_time_matrix(
    mode: str,
    lsoa_csv: Path | None,
    output_dir: Path,
    osrm_url: str,
    chunk_size: int,
) -> Path:
    if mode == "transit":
        print(
            "Transit mode: use the R5 Docker setup in scripts/analysis/r5/ "
            "to compute the transit matrix.",
            file=sys.stderr,
        )
        print("See scripts/analysis/r5/README.md for instructions.", file=sys.stderr)
        sys.exit(0)

    print("Loading LSOA centroids...")
    centroids = _load_lsoa_centroids(lsoa_csv)
    print(f"  {len(centroids)} centroids loaded")

    print("Computing walking travel-time matrix via OSRM...")
    matrix = build_walking_matrix(centroids, osrm_url, chunk_size)

    valid = matrix["travel_time_minutes"].notna().sum()
    total = len(matrix)
    print(f"\nCompleted: {total:,} LSOA pairs, {valid:,} with valid times ({total - valid:,} NaN/no route)")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "travel_time_walking.parquet"
    matrix.to_parquet(output_path, index=False)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Output: {output_path} ({size_mb:.1f} MB)")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build LSOA-to-LSOA travel time matrix."
    )
    parser.add_argument(
        "--mode",
        choices=["walking", "transit"],
        default="walking",
        help="Travel mode. 'transit' redirects to the R5 Docker setup.",
    )
    parser.add_argument(
        "--lsoa-csv",
        default=None,
        type=Path,
        help="LSOA centroids CSV (LSOA_code, latitude, longitude). "
             "If omitted, centroids are fetched from ArcGIS.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        type=Path,
        help="Output directory (default: data/cache/)",
    )
    parser.add_argument(
        "--osrm-url",
        default=OSRM_PUBLIC_URL,
        help=f"OSRM base URL (default: {OSRM_PUBLIC_URL}). "
             "Point at a local OSRM instance for production use.",
    )
    parser.add_argument(
        "--chunk-size",
        default=DEFAULT_CHUNK_SIZE,
        type=int,
        help=f"Number of LSOAs per request batch (default: {DEFAULT_CHUNK_SIZE}).",
    )
    args = parser.parse_args()
    build_travel_time_matrix(
        mode=args.mode,
        lsoa_csv=args.lsoa_csv,
        output_dir=args.output_dir,
        osrm_url=args.osrm_url,
        chunk_size=args.chunk_size,
    )


if __name__ == "__main__":
    main()

"""
R5 Conveyal transit travel-time matrix builder for London LSOAs.

Run inside the Docker container built from scripts/analysis/r5/Dockerfile.
See scripts/analysis/r5/README.md for full usage instructions.

Environment variables (set via docker run -e or --env-file):
    DATA_DIR    Directory containing GTFS feeds and OSM PBF (default /data)
    OUTPUT_DIR  Directory for the output parquet file (default /output)

The script:
1. Starts R5 in HTTP server mode pointing at the data directory
2. Waits for the server to be ready
3. Loads LSOA centroids from /data/lsoa_centroids.csv (LSOA_code, lat, lon)
4. Builds the transit travel-time matrix using the R5 /travelTimeMatrix endpoint
   with Tuesday 10:00 AM departure (fixed for reproducibility)
5. Writes output to $OUTPUT_DIR/travel_time_transit.parquet
   with columns: origin_lsoa, destination_lsoa, travel_time_minutes
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/output"))
R5_JAR = Path(os.environ.get("R5_JAR", "/r5/r5.jar"))

R5_HOST = "http://localhost:7070"
R5_READY_ENDPOINT = f"{R5_HOST}/api/version"
DEPARTURE_DATE = "2025-11-04"  # Tuesday
DEPARTURE_TIME = "10:00"
MAX_TRAVEL_TIME_MINUTES = 120
WALK_SPEED_KMH = 4.8
MAX_RIDES = 4
CHUNK_SIZE = 200
REQUEST_TIMEOUT = 300


def _wait_for_r5(max_wait_s: int = 120) -> None:
    print("  Waiting for R5 server to start...")
    start = time.time()
    while time.time() - start < max_wait_s:
        try:
            resp = requests.get(R5_READY_ENDPOINT, timeout=5)
            if resp.status_code == 200:
                print(f"  R5 ready after {time.time() - start:.0f}s")
                return
        except requests.ConnectionError:
            pass
        time.sleep(3)
    raise RuntimeError(f"R5 did not start within {max_wait_s}s")


def _load_centroids() -> pd.DataFrame:
    centroids_path = DATA_DIR / "lsoa_centroids.csv"
    if not centroids_path.exists():
        raise FileNotFoundError(
            f"LSOA centroids file not found at {centroids_path}. "
            "Generate it with scripts/analysis/build_qof_lsoa.py --lsoa-csv or "
            "export LSOA centroids with columns: LSOA_code, latitude, longitude."
        )
    df = pd.read_csv(centroids_path, dtype=str)
    df.columns = df.columns.str.strip()
    code_col = next((c for c in df.columns if c.lower() in {"lsoa_code", "lsoa21cd"}), None)
    lat_col = next((c for c in df.columns if c.lower() in {"latitude", "lat"}), None)
    lon_col = next((c for c in df.columns if c.lower() in {"longitude", "lon", "long"}), None)
    if not code_col or not lat_col or not lon_col:
        raise ValueError(f"lsoa_centroids.csv must have LSOA_code, latitude, longitude. Found: {list(df.columns)}")
    df = df.rename(columns={code_col: "LSOA_code", lat_col: "lat", lon_col: "lon"})
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    return df[["LSOA_code", "lat", "lon"]].dropna()


def _query_r5_chunk(
    origins: list[dict[str, object]],
    destinations: list[dict[str, object]],
) -> list[dict[str, object]]:
    payload = {
        "originPoints": origins,
        "destinationPoints": destinations,
        "date": DEPARTURE_DATE,
        "fromTime": DEPARTURE_TIME + ":00",
        "toTime": DEPARTURE_TIME + ":59",
        "maxTripDurationMinutes": MAX_TRAVEL_TIME_MINUTES,
        "walkSpeed": WALK_SPEED_KMH,
        "maxRides": MAX_RIDES,
        "transitModes": ["BUS", "TRAM", "SUBWAY", "RAIL", "FERRY"],
    }
    resp = requests.post(
        f"{R5_HOST}/api/travelTimeMatrix",
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def build_transit_matrix(centroids: pd.DataFrame) -> pd.DataFrame:
    lsoa_codes = centroids["LSOA_code"].tolist()
    n = len(lsoa_codes)
    chunks = [list(range(i, min(i + CHUNK_SIZE, n))) for i in range(0, n, CHUNK_SIZE)]
    total_requests = len(chunks) ** 2
    print(f"  {n} LSOAs, chunk size {CHUNK_SIZE} → {len(chunks)} chunks, {total_requests} requests")

    rows: list[dict[str, object]] = []
    request_num = 0
    for src_chunk in chunks:
        for dst_chunk in chunks:
            request_num += 1
            if request_num % 50 == 0:
                pct = request_num / total_requests * 100
                print(f"  [{request_num}/{total_requests}] {pct:.1f}% complete...")

            origins = [
                {"id": lsoa_codes[i], "lat": float(centroids.iloc[i]["lat"]), "lon": float(centroids.iloc[i]["lon"])}
                for i in src_chunk
            ]
            destinations = [
                {"id": lsoa_codes[i], "lat": float(centroids.iloc[i]["lat"]), "lon": float(centroids.iloc[i]["lon"])}
                for i in dst_chunk
            ]

            try:
                results = _query_r5_chunk(origins, destinations)
                for result in results:
                    rows.append({
                        "origin_lsoa": result["originId"],
                        "destination_lsoa": result["destinationId"],
                        "travel_time_minutes": float(result["travelTimeMinutes"])
                        if result.get("travelTimeMinutes") is not None
                        else float("nan"),
                    })
            except Exception as exc:
                print(f"  WARNING: Chunk {request_num} failed: {exc}. Filling with NaN.", file=sys.stderr)
                for i in src_chunk:
                    for j in dst_chunk:
                        rows.append({
                            "origin_lsoa": lsoa_codes[i],
                            "destination_lsoa": lsoa_codes[j],
                            "travel_time_minutes": float("nan"),
                        })

    return pd.DataFrame(rows)


def main() -> None:
    print("=== R5 Transit Travel-Time Matrix Builder ===")
    print(f"Data directory: {DATA_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")

    print("\nStarting R5 in HTTP server mode...")
    r5_proc = subprocess.Popen(
        ["java", "-Xmx8g", "-jar", str(R5_JAR), "--server", "--graphs", str(DATA_DIR)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        _wait_for_r5()

        print("\nLoading LSOA centroids...")
        centroids = _load_centroids()
        print(f"  {len(centroids)} centroids loaded")

        print("\nComputing transit travel-time matrix via R5...")
        print(f"  Departure: {DEPARTURE_DATE} {DEPARTURE_TIME} (Tuesday morning)")
        matrix = build_transit_matrix(centroids)

        valid = matrix["travel_time_minutes"].notna().sum()
        total = len(matrix)
        print(f"\nCompleted: {total:,} LSOA pairs, {valid:,} with valid times")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / "travel_time_transit.parquet"
        matrix.to_parquet(output_path, index=False)
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"Output: {output_path} ({size_mb:.1f} MB)")

    finally:
        r5_proc.terminate()
        r5_proc.wait()
        print("R5 server stopped.")


if __name__ == "__main__":
    main()

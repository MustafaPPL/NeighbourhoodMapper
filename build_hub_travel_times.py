from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from build_weighted_priority_map import (
    DEFAULT_OUTPUT_CSV as DEFAULT_WEIGHTED_SCORED_CSV,
    FAMILY_HUB_GEO_CACHE_CSV,
    GP_GEO_CACHE_CSV,
    OUTPUT_DIR,
    PHARMACY_GEO_CACHE_CSV,
    fetch_london_lsoa_boundaries,
)


DEFAULT_SCORED_CSV = DEFAULT_WEIGHTED_SCORED_CSV
DEFAULT_OUTPUT_CSV = OUTPUT_DIR / "lsoa_hub_travel_times.csv"
DEFAULT_CACHE_DIR = OUTPUT_DIR / "travel_time_cache"

OSRM_BASE_URL = "https://router.project-osrm.org"
TFL_JOURNEY_RESULTS_BASE_URL = "https://api.tfl.gov.uk/Journey/JourneyResults"
REQUEST_TIMEOUT = 60
USER_AGENT = "London-access-gap-travel-times/1.0 (+python requests)"
METRIC_CRS = "EPSG:27700"
WGS84 = "EPSG:4326"
DEFAULT_CANDIDATE_COUNT = 5
DEFAULT_ORIGIN_BATCH_SIZE = 60

ROAD_PROFILES = {"driving", "walking", "cycling"}
TRANSIT_PROFILE = "transit"
SUPPORTED_PROFILES = sorted(ROAD_PROFILES | {TRANSIT_PROFILE})

HUB_TYPE_TO_PATH = {
    "gp": GP_GEO_CACHE_CSV,
    "pharmacy": PHARMACY_GEO_CACHE_CSV,
    "family_hub": FAMILY_HUB_GEO_CACHE_CSV,
}

HUB_TYPE_TO_LABEL = {
    "gp": "GP practice",
    "pharmacy": "Community pharmacy",
    "family_hub": "Family hub",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Pull travel times from London LSOA centroids to the nearest hub locations. "
            "Road profiles use OSRM; public transport uses TfL Journey Results."
        )
    )
    parser.add_argument(
        "--scored-csv",
        type=Path,
        default=DEFAULT_SCORED_CSV,
        help="CSV containing at least LSOA_code and any priority fields you want to carry through.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=DEFAULT_OUTPUT_CSV,
        help="Path for the output travel-time CSV.",
    )
    parser.add_argument(
        "--hub-type",
        action="append",
        choices=sorted(HUB_TYPE_TO_PATH),
        help="Hub type to analyse. Repeat to include multiple types. Defaults to all built-in hub types.",
    )
    parser.add_argument(
        "--profile",
        action="append",
        choices=SUPPORTED_PROFILES,
        help="Travel profile to calculate. Repeat to include multiple profiles. Defaults to driving.",
    )
    parser.add_argument(
        "--candidate-count",
        type=int,
        default=DEFAULT_CANDIDATE_COUNT,
        help="How many straight-line nearest hubs to test per LSOA before routing.",
    )
    parser.add_argument(
        "--origin-batch-size",
        type=int,
        default=DEFAULT_ORIGIN_BATCH_SIZE,
        help="How many LSOA origins to include in each road-routing matrix request.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Directory for cached routing API responses.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.2,
        help="Pause between API calls to avoid hammering the routing services.",
    )
    parser.add_argument(
        "--date",
        help="Optional TfL journey date in YYYYMMDD format for transit requests.",
    )
    parser.add_argument(
        "--time",
        help="Optional TfL journey time in HHMM format for transit requests.",
    )
    parser.add_argument(
        "--time-is",
        choices=["Departing", "Arriving"],
        default="Departing",
        help="How TfL should interpret the journey time for transit requests.",
    )
    parser.add_argument(
        "--tfl-modes",
        default="bus,tube,overground,dlr,elizabeth-line,tram,national-rail",
        help="Comma-separated TfL public transport modes to allow in transit routing.",
    )
    parser.add_argument(
        "--tfl-app-key",
        default=os.getenv("TFL_APP_KEY", ""),
        help="TfL app key. Defaults to the TFL_APP_KEY environment variable if set.",
    )
    parser.add_argument(
        "--tfl-app-id",
        default=os.getenv("TFL_APP_ID", ""),
        help="Optional TfL app id. Defaults to the TFL_APP_ID environment variable if set.",
    )
    return parser.parse_args()


def request_json(url: str, params: dict[str, str], cache_dir: Path, pause_seconds: float, max_retries: int = 4) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.md5(
        json.dumps({"url": url, "params": params}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    cache_path = cache_dir / f"{cache_key}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    headers = {"User-Agent": USER_AGENT}
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
            if pause_seconds > 0:
                time.sleep(pause_seconds)
            return payload
        except Exception as exc:
            last_error = exc
            if attempt == max_retries:
                raise
            time.sleep(min(2**attempt, 8))

    raise RuntimeError(f"Routing request failed: {last_error}")


def ensure_columns(df: pd.DataFrame, required: Iterable[str], source: Path) -> None:
    missing = sorted(set(required).difference(df.columns))
    if missing:
        raise ValueError(f"Missing required columns in {source}: {missing}")


def load_scored_lsoas(path: Path) -> pd.DataFrame:
    scored = pd.read_csv(path, dtype={"LSOA_code": str})
    ensure_columns(scored, ["LSOA_code"], path)
    return scored


def build_lsoa_centroids(scored: pd.DataFrame) -> gpd.GeoDataFrame:
    lsoa, _, _ = fetch_london_lsoa_boundaries()
    lsoa = lsoa.loc[:, ["LSOA_code", "geometry"]].drop_duplicates("LSOA_code")
    lsoa = lsoa[lsoa["LSOA_code"].isin(scored["LSOA_code"])].copy()
    lsoa_metric = lsoa.to_crs(METRIC_CRS)
    centroids_metric = lsoa_metric.copy()
    centroids_metric["geometry"] = centroids_metric.geometry.centroid
    centroids = centroids_metric.to_crs(WGS84)
    return centroids.merge(scored, on="LSOA_code", how="inner", validate="1:1")


def points_to_gdf(df: pd.DataFrame, latitude_col: str = "Latitude", longitude_col: str = "Longitude") -> gpd.GeoDataFrame:
    points = df.copy()
    points[latitude_col] = pd.to_numeric(points[latitude_col], errors="coerce")
    points[longitude_col] = pd.to_numeric(points[longitude_col], errors="coerce")
    points = points.dropna(subset=[latitude_col, longitude_col]).copy()
    return gpd.GeoDataFrame(
        points,
        geometry=gpd.points_from_xy(points[longitude_col], points[latitude_col]),
        crs=WGS84,
    )


def load_hubs(hub_type: str) -> gpd.GeoDataFrame:
    path = HUB_TYPE_TO_PATH[hub_type]
    df = pd.read_csv(path, dtype=str)
    df.columns = [str(col).strip() for col in df.columns]

    if hub_type == "gp":
        ensure_columns(df, ["Practice Name", "Practice Code", "Latitude", "Longitude"], path)
        df = df.rename(columns={"Practice Name": "hub_name", "Practice Code": "hub_code"})
    elif hub_type == "pharmacy":
        ensure_columns(df, ["PHARMACY_ODS_CODE_F_CODE", "SiteName", "Latitude", "Longitude"], path)
        df = df.rename(columns={"SiteName": "hub_name", "PHARMACY_ODS_CODE_F_CODE": "hub_code"})
    elif hub_type == "family_hub":
        ensure_columns(df, ["Postcode", "Latitude", "Longitude"], path)
        df = df.rename(columns={"Postcode": "hub_code"})
        df["hub_name"] = df["hub_code"]
    else:
        raise ValueError(f"Unsupported hub type: {hub_type}")

    hubs = points_to_gdf(df)
    hubs["hub_type"] = hub_type
    hubs["hub_label"] = HUB_TYPE_TO_LABEL[hub_type]
    hubs = hubs.drop_duplicates(subset=["hub_code", "Latitude", "Longitude"]).reset_index(drop=True)
    return hubs.loc[:, ["hub_type", "hub_label", "hub_name", "hub_code", "Latitude", "Longitude", "geometry"]]


def compute_candidate_indices(origin_xy: np.ndarray, dest_xy: np.ndarray, candidate_count: int) -> np.ndarray:
    if len(dest_xy) == 0:
        return np.empty((len(origin_xy), 0), dtype=int)

    candidate_count = min(candidate_count, len(dest_xy))
    candidate_indices = np.empty((len(origin_xy), candidate_count), dtype=int)
    for start in range(0, len(origin_xy), 500):
        stop = min(start + 500, len(origin_xy))
        delta = origin_xy[start:stop, None, :] - dest_xy[None, :, :]
        distances_sq = np.sum(delta * delta, axis=2)
        nearest = np.argpartition(distances_sq, kth=candidate_count - 1, axis=1)[:, :candidate_count]
        candidate_indices[start:stop] = nearest
    return candidate_indices


def profile_suffix(profile: str) -> str:
    return "transit" if profile == TRANSIT_PROFILE else profile


def format_coordinates(coords: list[tuple[float, float]]) -> str:
    return ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coords)


def query_osrm_table(
    origins: list[tuple[float, float]],
    destinations: list[tuple[float, float]],
    profile: str,
    cache_dir: Path,
    pause_seconds: float,
) -> tuple[list[list[float | None]], list[list[float | None]]]:
    coordinates = origins + destinations
    if not coordinates:
        return [], []

    origin_indices = ";".join(str(i) for i in range(len(origins)))
    destination_indices = ";".join(str(i) for i in range(len(origins), len(coordinates)))
    url = f"{OSRM_BASE_URL}/table/v1/{profile}/{format_coordinates(coordinates)}"
    payload = request_json(
        url,
        {
            "sources": origin_indices,
            "destinations": destination_indices,
            "annotations": "duration,distance",
        },
        cache_dir=cache_dir,
        pause_seconds=pause_seconds,
    )

    if payload.get("code") != "Ok":
        raise RuntimeError(f"OSRM table request failed: {payload}")

    durations = payload.get("durations")
    distances = payload.get("distances")
    if durations is None or distances is None:
        raise RuntimeError(f"OSRM response missing durations/distances: {payload}")
    return durations, distances


def build_tfl_params(args: argparse.Namespace) -> dict[str, str]:
    params = {
        "journeyPreference": "leasttime",
        "mode": args.tfl_modes,
    }
    if args.date:
        params["date"] = args.date
    if args.time:
        params["time"] = args.time
        params["timeIs"] = args.time_is
    if args.tfl_app_key:
        params["app_key"] = args.tfl_app_key
    if args.tfl_app_id:
        params["app_id"] = args.tfl_app_id
    return params


def format_tfl_point(lat: float, lon: float) -> str:
    return f"{lat:.6f},{lon:.6f}"


def query_tfl_journey_time(
    origin: tuple[float, float],
    destination: tuple[float, float],
    args: argparse.Namespace,
    cache_dir: Path,
) -> tuple[float | None, float | None]:
    origin_point = format_tfl_point(origin[0], origin[1])
    destination_point = format_tfl_point(destination[0], destination[1])
    url = f"{TFL_JOURNEY_RESULTS_BASE_URL}/{origin_point}/to/{destination_point}"
    payload = request_json(
        url,
        build_tfl_params(args),
        cache_dir=cache_dir,
        pause_seconds=args.pause_seconds,
    )

    journeys = payload.get("journeys") or []
    if not journeys:
        return None, None

    best_duration = None
    best_fare = None
    for journey in journeys:
        duration = journey.get("duration")
        if duration is None:
            continue
        duration_value = float(duration)
        if best_duration is None or duration_value < best_duration:
            best_duration = duration_value
            fare = journey.get("fare", {}) if isinstance(journey.get("fare"), dict) else {}
            total_cost = fare.get("totalCost")
            best_fare = round(float(total_cost) / 100.0, 2) if total_cost is not None else None

    return best_duration, best_fare


def calculate_nearest_hub_metrics_road(
    centroids: gpd.GeoDataFrame,
    hubs: gpd.GeoDataFrame,
    hub_type: str,
    profile: str,
    candidate_count: int,
    origin_batch_size: int,
    cache_dir: Path,
    pause_seconds: float,
) -> pd.DataFrame:
    origin_points = centroids.to_crs(METRIC_CRS).reset_index(drop=True)
    hub_points = hubs.to_crs(METRIC_CRS).reset_index(drop=True)

    origin_xy = np.column_stack([origin_points.geometry.x.to_numpy(), origin_points.geometry.y.to_numpy()])
    hub_xy = np.column_stack([hub_points.geometry.x.to_numpy(), hub_points.geometry.y.to_numpy()])
    candidates = compute_candidate_indices(origin_xy, hub_xy, candidate_count)

    results: list[dict[str, object]] = []
    for batch_start in range(0, len(origin_points), origin_batch_size):
        batch_stop = min(batch_start + origin_batch_size, len(origin_points))
        batch = origin_points.iloc[batch_start:batch_stop].copy()
        batch_candidates = candidates[batch_start:batch_stop]

        unique_hub_indices = sorted({int(idx) for row in batch_candidates for idx in row.tolist()})
        candidate_lookup = {hub_idx: pos for pos, hub_idx in enumerate(unique_hub_indices)}

        origin_coords = [
            (float(geom.x), float(geom.y))
            for geom in centroids.iloc[batch_start:batch_stop].to_crs(WGS84).geometry
        ]
        destination_coords = [
            (float(hubs.iloc[hub_idx].geometry.x), float(hubs.iloc[hub_idx].geometry.y))
            for hub_idx in unique_hub_indices
        ]

        durations, distances = query_osrm_table(
            origins=origin_coords,
            destinations=destination_coords,
            profile=profile,
            cache_dir=cache_dir / hub_type / profile,
            pause_seconds=pause_seconds,
        )

        profile_key = profile_suffix(profile)
        for local_origin_idx, (_, row) in enumerate(batch.iterrows()):
            best_duration = None
            best_distance = None
            best_hub_index = None
            for hub_idx in batch_candidates[local_origin_idx]:
                destination_pos = candidate_lookup[int(hub_idx)]
                duration_seconds = durations[local_origin_idx][destination_pos]
                distance_metres = distances[local_origin_idx][destination_pos]
                if duration_seconds is None or distance_metres is None:
                    continue
                if best_duration is None or duration_seconds < best_duration:
                    best_duration = duration_seconds
                    best_distance = distance_metres
                    best_hub_index = int(hub_idx)

            prefix = f"nearest_{hub_type}_{profile_key}"
            record = {"LSOA_code": row["LSOA_code"]}
            if best_hub_index is None:
                record[f"{prefix}_name"] = pd.NA
                record[f"{prefix}_code"] = pd.NA
                record[f"{prefix}_minutes"] = pd.NA
                record[f"{prefix}_distance_km"] = pd.NA
            else:
                best_hub = hubs.iloc[best_hub_index]
                record[f"{prefix}_name"] = best_hub["hub_name"]
                record[f"{prefix}_code"] = best_hub["hub_code"]
                record[f"{prefix}_minutes"] = round(float(best_duration) / 60.0, 1)
                record[f"{prefix}_distance_km"] = round(float(best_distance) / 1000.0, 2)
            results.append(record)

    return pd.DataFrame(results)


def calculate_nearest_hub_metrics_transit(
    centroids: gpd.GeoDataFrame,
    hubs: gpd.GeoDataFrame,
    hub_type: str,
    candidate_count: int,
    cache_dir: Path,
    args: argparse.Namespace,
) -> pd.DataFrame:
    origin_points = centroids.to_crs(METRIC_CRS).reset_index(drop=True)
    hub_points = hubs.to_crs(METRIC_CRS).reset_index(drop=True)

    origin_xy = np.column_stack([origin_points.geometry.x.to_numpy(), origin_points.geometry.y.to_numpy()])
    hub_xy = np.column_stack([hub_points.geometry.x.to_numpy(), hub_points.geometry.y.to_numpy()])
    candidates = compute_candidate_indices(origin_xy, hub_xy, candidate_count)

    results: list[dict[str, object]] = []
    for origin_idx, (_, row) in enumerate(centroids.reset_index(drop=True).iterrows()):
        origin_lat = float(row.geometry.y)
        origin_lon = float(row.geometry.x)
        best_duration = None
        best_fare = None
        best_hub_index = None

        for hub_idx in candidates[origin_idx]:
            hub_row = hubs.iloc[int(hub_idx)]
            duration_minutes, fare_gbp = query_tfl_journey_time(
                origin=(origin_lat, origin_lon),
                destination=(float(hub_row.geometry.y), float(hub_row.geometry.x)),
                args=args,
                cache_dir=cache_dir / hub_type / TRANSIT_PROFILE,
            )
            if duration_minutes is None:
                continue
            if best_duration is None or duration_minutes < best_duration:
                best_duration = duration_minutes
                best_fare = fare_gbp
                best_hub_index = int(hub_idx)

        prefix = f"nearest_{hub_type}_{profile_suffix(TRANSIT_PROFILE)}"
        record = {"LSOA_code": row["LSOA_code"]}
        if best_hub_index is None:
            record[f"{prefix}_name"] = pd.NA
            record[f"{prefix}_code"] = pd.NA
            record[f"{prefix}_minutes"] = pd.NA
            record[f"{prefix}_fare_gbp"] = pd.NA
        else:
            best_hub = hubs.iloc[best_hub_index]
            record[f"{prefix}_name"] = best_hub["hub_name"]
            record[f"{prefix}_code"] = best_hub["hub_code"]
            record[f"{prefix}_minutes"] = round(float(best_duration), 1)
            record[f"{prefix}_fare_gbp"] = best_fare
        results.append(record)

        if (origin_idx + 1) % 250 == 0:
            print(f"Processed transit journeys for {origin_idx + 1}/{len(centroids)} LSOAs to {hub_type}")

    return pd.DataFrame(results)


def calculate_nearest_hub_metrics(
    centroids: gpd.GeoDataFrame,
    hubs: gpd.GeoDataFrame,
    hub_type: str,
    profile: str,
    args: argparse.Namespace,
) -> pd.DataFrame:
    if profile in ROAD_PROFILES:
        return calculate_nearest_hub_metrics_road(
            centroids=centroids,
            hubs=hubs,
            hub_type=hub_type,
            profile=profile,
            candidate_count=args.candidate_count,
            origin_batch_size=args.origin_batch_size,
            cache_dir=args.cache_dir,
            pause_seconds=args.pause_seconds,
        )
    if profile == TRANSIT_PROFILE:
        return calculate_nearest_hub_metrics_transit(
            centroids=centroids,
            hubs=hubs,
            hub_type=hub_type,
            candidate_count=args.candidate_count,
            cache_dir=args.cache_dir,
            args=args,
        )
    raise ValueError(f"Unsupported profile: {profile}")


def main() -> None:
    args = parse_args()
    hub_types = args.hub_type or list(HUB_TYPE_TO_PATH)
    profiles = args.profile or ["driving"]

    if args.candidate_count < 1:
        raise ValueError("--candidate-count must be at least 1.")
    if args.origin_batch_size < 1:
        raise ValueError("--origin-batch-size must be at least 1.")

    scored = load_scored_lsoas(args.scored_csv)
    centroids = build_lsoa_centroids(scored)
    output = scored.copy()

    for hub_type in hub_types:
        hubs = load_hubs(hub_type)
        if hubs.empty:
            raise ValueError(f"No valid hub coordinates found for hub type '{hub_type}'.")
        for profile in profiles:
            metrics = calculate_nearest_hub_metrics(
                centroids=centroids,
                hubs=hubs,
                hub_type=hub_type,
                profile=profile,
                args=args,
            )
            output = output.merge(metrics, on="LSOA_code", how="left", validate="1:1")

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output_csv, index=False)

    print(f"Created: {args.output_csv}")
    print(f"Rows: {len(output)}")
    print(f"Profiles: {', '.join(profiles)}")
    print(f"Hub types: {', '.join(hub_types)}")


if __name__ == "__main__":
    main()

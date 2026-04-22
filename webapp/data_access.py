from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import pandas as pd
import requests

from build_weighted_priority_map import (
    fetch_london_lsoa_boundaries,
    load_65plus_data,
    load_community_pharmacies,
    load_deprivation_data,
    load_family_hubs,
    load_gp_practices,
)
from webapp.config import AppConfig, BRITISH_NATIONAL_GRID, WGS84


ICB_CODE_BY_NAME = {
    "NHS North Central London ICB": "NCL",
    "NHS North East London ICB": "NEL",
    "NHS North West London ICB": "NWL",
    "NHS South East London ICB": "SEL",
    "NHS South West London ICB": "SWL",
}


@dataclass(frozen=True)
class CandidateGeocodeResult:
    candidates: gpd.GeoDataFrame
    invalid_postcodes: list[str]


def detect_column(columns: Iterable[str], candidates: list[str]) -> str | None:
    normalized = {str(column).strip().lower(): str(column) for column in columns}
    for candidate in candidates:
        match = normalized.get(candidate.lower())
        if match is not None:
            return match
    return None


def load_need_inputs(config: AppConfig) -> pd.DataFrame:
    deprivation = load_deprivation_data(config.deprivation_csv)
    population = load_population_data(config.population_csv)
    older_people = load_65plus_data(config.older_people_csv)

    merged = deprivation.merge(population, on="LSOA_code", how="inner", validate="1:1")
    merged = merged.merge(older_people, on="LSOA_code", how="left", validate="1:1")
    merged["population"] = pd.to_numeric(merged["population"], errors="coerce")
    merged["population_65_plus"] = pd.to_numeric(merged["population_65_plus"], errors="coerce")
    merged["older_people_proportion"] = merged["population_65_plus"] / merged["population"]
    merged.loc[~merged["older_people_proportion"].between(0, 1), "older_people_proportion"] = pd.NA
    merged["deprivation_inverse"] = 11 - pd.to_numeric(merged["IMD_decile"], errors="coerce")
    merged.loc[~merged["IMD_decile"].between(1, 10), "deprivation_inverse"] = pd.NA
    return merged


def load_population_data(path: Path) -> pd.DataFrame:
    population = pd.read_csv(path, dtype=str)
    required = {"LSOA 2021 Code", "Total"}
    missing = required.difference(population.columns)
    if missing:
        raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")
    population = population.rename(columns={"LSOA 2021 Code": "LSOA_code", "Total": "population"})
    return population.loc[:, ["LSOA_code", "population"]].drop_duplicates("LSOA_code")


def load_neighbourhoods(config: AppConfig) -> gpd.GeoDataFrame:
    neighbourhoods = gpd.read_file(config.neighbourhoods_path).to_crs(WGS84)
    required = {"nghbrhd", "borough", "ICB"}
    missing = required.difference(neighbourhoods.columns)
    if missing:
        raise ValueError(f"Missing required columns in {config.neighbourhoods_path}: {sorted(missing)}")
    return neighbourhoods


def load_lsoa_boundaries(config: AppConfig) -> gpd.GeoDataFrame:
    if config.lsoa_source == "local_file":
        assert config.local_lsoa_path is not None
        lsoa = gpd.read_file(config.local_lsoa_path).to_crs(WGS84)
        lsoa_code_column = detect_column(lsoa.columns, ["LSOA_code", "LSOA21CD", "LSOA11CD", "CODE"])
        if lsoa_code_column is None:
            raise ValueError(
                f"Could not find an LSOA code column in {config.local_lsoa_path}. "
                f"Available columns: {list(lsoa.columns)}"
            )
        return lsoa.rename(columns={lsoa_code_column: "LSOA_code"})

    lsoa, _, _ = fetch_london_lsoa_boundaries()
    return lsoa.to_crs(WGS84)


def annotate_lsoa_geography(lsoa: gpd.GeoDataFrame, neighbourhoods: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    centroids = lsoa.to_crs(BRITISH_NATIONAL_GRID).copy()
    centroids["geometry"] = centroids.geometry.centroid
    centroids = centroids.to_crs(WGS84)

    joined = gpd.sjoin(
        centroids.loc[:, ["LSOA_code", "geometry"]],
        neighbourhoods.loc[:, ["nghbrhd", "borough", "ICB", "geometry"]],
        how="left",
        predicate="within",
    )
    joined = joined.drop(columns=["index_right", "geometry"], errors="ignore")
    joined = (
        joined.groupby("LSOA_code", as_index=False)
        .agg(
            {
                "nghbrhd": "first",
                "borough": "first",
                "ICB": "first",
            }
        )
        .reset_index(drop=True)
    )
    return lsoa.merge(joined, on="LSOA_code", how="left", validate="1:1")


def filter_scope(lsoa: gpd.GeoDataFrame, geography_mode: str, icb_name: str | None) -> gpd.GeoDataFrame:
    if geography_mode == "All London":
        return lsoa.copy()
    if not icb_name:
        raise ValueError("An ICB must be selected when geography mode is 'Specific ICB'.")
    icb_code = ICB_CODE_BY_NAME.get(icb_name)
    if icb_code is None:
        raise ValueError(f"Unsupported ICB: {icb_name}")
    return lsoa[lsoa["ICB"].astype(str).str.strip().eq(icb_code)].copy()


def load_asset_counts() -> dict[str, int]:
    return {
        "gp_practices": len(load_gp_practices()),
        "community_pharmacies": len(load_community_pharmacies()),
        "family_hubs": len(load_family_hubs()),
    }


def normalize_postcode(value: str) -> str:
    return "".join(str(value).upper().split())


def load_postcode_lsoa_lookup(path: Path) -> pd.DataFrame:
    lookup = pd.read_csv(path, dtype=str)
    postcode_column = detect_column(lookup.columns, ["pcds", "postcode", "pcd7", "pcd8", "pcd", "Postcode"])
    lsoa_column = detect_column(lookup.columns, ["lsoa21cd", "LSOA_code", "lsoa_code", "LSOA21CD"])
    lsoa_name_column = detect_column(lookup.columns, ["lsoa21nm", "LSOA_name", "lsoa_name", "LSOA21NM"])
    if postcode_column is None or lsoa_column is None:
        raise ValueError(
            f"Postcode-to-LSOA file {path} must contain postcode and LSOA code columns. "
            f"Available columns: {list(lookup.columns)}"
        )
    rename_map = {postcode_column: "postcode", lsoa_column: "LSOA_code"}
    if lsoa_name_column is not None:
        rename_map[lsoa_name_column] = "LSOA_name"
    lookup = lookup.rename(columns=rename_map)
    lookup["postcode_normalized"] = lookup["postcode"].map(normalize_postcode)
    lookup = lookup.dropna(subset=["postcode_normalized", "LSOA_code"]).drop_duplicates("postcode_normalized")
    keep_columns = ["postcode", "postcode_normalized", "LSOA_code"]
    if "LSOA_name" in lookup.columns:
        keep_columns.append("LSOA_name")
    return lookup.loc[:, keep_columns]


def _load_local_postcode_coordinate_lookup(path: Path) -> pd.DataFrame:
    lookup = pd.read_csv(path, dtype=str)
    postcode_column = detect_column(lookup.columns, ["postcode", "pcds", "pcd", "Postcode"])
    lat_column = detect_column(lookup.columns, ["latitude", "lat", "Latitude"])
    lon_column = detect_column(lookup.columns, ["longitude", "lon", "long", "Longitude"])
    if postcode_column is None or lat_column is None or lon_column is None:
        raise ValueError(
            f"Postcode lookup file {path} must contain postcode, latitude, and longitude columns. "
            f"Available columns: {list(lookup.columns)}"
        )
    lookup = lookup.rename(
        columns={postcode_column: "postcode", lat_column: "latitude", lon_column: "longitude"}
    )
    lookup["postcode_normalized"] = lookup["postcode"].map(normalize_postcode)
    lookup["latitude"] = pd.to_numeric(lookup["latitude"], errors="coerce")
    lookup["longitude"] = pd.to_numeric(lookup["longitude"], errors="coerce")
    lookup = lookup.dropna(subset=["latitude", "longitude"]).drop_duplicates("postcode_normalized")
    return lookup.loc[:, ["postcode", "postcode_normalized", "latitude", "longitude"]]


def _geocode_via_postcodes_io(postcodes: list[str], api_base_url: str) -> CandidateGeocodeResult:
    rows: list[dict[str, object]] = []
    invalid: list[str] = []
    for postcode in postcodes:
        response = requests.get(f"{api_base_url.rstrip('/')}/{postcode}", timeout=20)
        if response.status_code != 200:
            invalid.append(postcode)
            continue
        payload = response.json()
        result = payload.get("result")
        if not isinstance(result, dict):
            invalid.append(postcode)
            continue
        latitude = result.get("latitude")
        longitude = result.get("longitude")
        if latitude is None or longitude is None:
            invalid.append(postcode)
            continue
        rows.append(
            {
                "postcode": postcode,
                "postcode_normalized": normalize_postcode(postcode),
                "latitude": latitude,
                "longitude": longitude,
                "geocode_source": "postcodes.io",
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        candidates = gpd.GeoDataFrame(frame, geometry=[], crs=WGS84)
    else:
        candidates = gpd.GeoDataFrame(
            frame,
            geometry=gpd.points_from_xy(frame["longitude"], frame["latitude"]),
            crs=WGS84,
        )
    return CandidateGeocodeResult(candidates=candidates, invalid_postcodes=invalid)


def geocode_candidate_postcodes(postcodes: list[str], config: AppConfig) -> CandidateGeocodeResult:
    normalized_input = [normalize_postcode(postcode) for postcode in postcodes if normalize_postcode(postcode)]
    if not normalized_input:
        return CandidateGeocodeResult(
            candidates=gpd.GeoDataFrame(columns=["postcode"], geometry=[], crs=WGS84),
            invalid_postcodes=[],
        )

    if config.postcode_source == "local_lookup":
        assert config.postcode_coordinate_lookup_csv is not None
        lookup = _load_local_postcode_coordinate_lookup(config.postcode_coordinate_lookup_csv)
        matched = lookup[lookup["postcode_normalized"].isin(normalized_input)].copy()
        matched["geocode_source"] = "local_lookup"
        postcode_map = {normalize_postcode(postcode): postcode.strip().upper() for postcode in postcodes}
        matched["postcode"] = matched["postcode_normalized"].map(postcode_map).fillna(matched["postcode"])
        candidates = gpd.GeoDataFrame(
            matched,
            geometry=gpd.points_from_xy(matched["longitude"], matched["latitude"]),
            crs=WGS84,
        )
        invalid = sorted(set(normalized_input).difference(set(matched["postcode_normalized"])))
        invalid = [postcode_map.get(postcode, postcode) for postcode in invalid]
        return CandidateGeocodeResult(candidates=candidates, invalid_postcodes=invalid)

    if config.postcode_source == "postcodes_io":
        return _geocode_via_postcodes_io(postcodes, config.postcode_api_base_url)

    raise ValueError("Postcode geocoding is not configured.")


def assign_candidates_to_lsoa(
    candidates: gpd.GeoDataFrame,
    scored_lsoas: gpd.GeoDataFrame,
    config: AppConfig,
) -> tuple[gpd.GeoDataFrame, list[str]]:
    if candidates.empty:
        return candidates.copy(), []

    lookup = load_postcode_lsoa_lookup(config.postcode_lsoa_lookup_csv)
    joined = candidates.merge(
        lookup.loc[:, [column for column in lookup.columns if column != "postcode"]],
        on="postcode_normalized",
        how="left",
        validate="1:1",
    )
    joined["postcode_lookup_source"] = "postcode_to_lsoa_file"

    scoped_reference = scored_lsoas.loc[:, ["LSOA_code", "ICB"]].drop_duplicates("LSOA_code")
    joined = joined.merge(scoped_reference, on="LSOA_code", how="left")
    joined["host_lsoa_in_scope"] = joined["ICB"].notna()
    unresolved = joined.loc[joined["LSOA_code"].isna(), "postcode"].astype(str).tolist()
    return gpd.GeoDataFrame(joined, geometry="geometry", crs=candidates.crs), unresolved

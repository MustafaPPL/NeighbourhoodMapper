from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import pandas as pd
import requests

from scripts.analysis.build_weighted_priority_map import (
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


_ETHNICITY_COLUMNS = [
    "LSOA_code",
    "pct_asian_residents",
    "pct_black_residents",
    "pct_mixed_residents",
    "pct_other_ethnic_group_residents",
    "pct_white_other_residents",
]

_QOF_COLUMNS = [
    "LSOA_code",
    "qof_chd_prevalence",
    "qof_copd_prevalence",
    "qof_diabetes_prevalence",
    "qof_depression_prevalence",
]


def load_travel_time_matrix(path: Path | None) -> dict[tuple[str, str], float] | None:
    """
    Load a pre-computed LSOA travel-time parquet into a dict keyed by (origin, destination).

    Returns None if path is None or the file does not exist (caller should fall back to
    straight-line mode). Intended to be called once per analysis run and cached by the caller.
    """
    if path is None or not path.exists():
        return None
    df = pd.read_parquet(path, columns=["origin_lsoa", "destination_lsoa", "travel_time_minutes"])
    valid = df.dropna(subset=["travel_time_minutes"])
    return {
        (row.origin_lsoa, row.destination_lsoa): float(row.travel_time_minutes)
        for row in valid.itertuples(index=False)
    }


def load_estate_sites(path: Path) -> gpd.GeoDataFrame:
    """Return NHS estate sites as a GeoDataFrame (WGS84) with site_name and geometry."""
    df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.strip()
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"])
    return gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs="EPSG:4326",
    )


def compute_estate_proximity(
    candidate_lat: float,
    candidate_lon: float,
    estate_sites: gpd.GeoDataFrame | None,
    radius_m: int,
) -> dict[str, object]:
    """Return estate proximity flags for a single candidate location."""
    null_result: dict[str, object] = {
        "nearby_nhs_estate_flag": False,
        "nearby_estate_count": 0,
        "nearest_estate_name": None,
        "nearest_estate_distance_m": None,
    }
    if estate_sites is None or estate_sites.empty:
        return null_result

    from shapely.geometry import Point

    candidate_bng = gpd.GeoSeries(
        [Point(candidate_lon, candidate_lat)], crs="EPSG:4326"
    ).to_crs("EPSG:27700").iloc[0]
    sites_bng = estate_sites.to_crs("EPSG:27700").copy()
    sites_bng["distance_m"] = sites_bng.geometry.distance(candidate_bng)
    nearby = sites_bng[sites_bng["distance_m"] <= radius_m].copy()
    if nearby.empty:
        return null_result
    nearest = nearby.loc[nearby["distance_m"].idxmin()]
    return {
        "nearby_nhs_estate_flag": True,
        "nearby_estate_count": int(len(nearby)),
        "nearest_estate_name": str(nearest.get("site_name", "")),
        "nearest_estate_distance_m": float(nearest["distance_m"]),
    }


def load_ethnicity_data(path: Path) -> pd.DataFrame:
    """Return ethnicity LSOA proportions dataframe with LSOA_code and five proportion columns."""
    df = pd.read_csv(path, dtype={"LSOA_code": str})
    df.columns = df.columns.str.strip()
    missing = [col for col in _ETHNICITY_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Ethnicity CSV is missing required columns: {missing}. Found: {list(df.columns)}")
    for col in _ETHNICITY_COLUMNS[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.loc[:, _ETHNICITY_COLUMNS].dropna(subset=["LSOA_code"]).drop_duplicates("LSOA_code")


def load_qof_data(path: Path) -> pd.DataFrame:
    """Return QOF LSOA prevalence dataframe with LSOA_code and four disease columns."""
    df = pd.read_csv(path, dtype={"LSOA_code": str})
    df.columns = df.columns.str.strip()
    missing = [col for col in _QOF_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"QOF CSV is missing required columns: {missing}. Found: {list(df.columns)}")
    for col in _QOF_COLUMNS[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.loc[:, _QOF_COLUMNS].dropna(subset=["LSOA_code"]).drop_duplicates("LSOA_code")


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

    if config.qof_lsoa_csv is not None:
        qof = load_qof_data(config.qof_lsoa_csv)
        merged = merged.merge(qof, on="LSOA_code", how="left", validate="1:1")

    if config.ethnicity_lsoa_csv is not None:
        ethnicity = load_ethnicity_data(config.ethnicity_lsoa_csv)
        merged = merged.merge(ethnicity, on="LSOA_code", how="left", validate="1:1")

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
    borough_column = detect_column(lookup.columns, ["borough", "local_authority", "lad_name", "LAD23NM", "LADNM"])
    if postcode_column is None or lsoa_column is None:
        raise ValueError(
            f"Postcode-to-LSOA file {path} must contain postcode and LSOA code columns. "
            f"Available columns: {list(lookup.columns)}"
        )
    rename_map = {postcode_column: "postcode", lsoa_column: "LSOA_code"}
    if lsoa_name_column is not None:
        rename_map[lsoa_name_column] = "LSOA_name"
    if borough_column is not None:
        rename_map[borough_column] = "borough"
    lookup = lookup.rename(columns=rename_map)
    lookup["postcode_normalized"] = lookup["postcode"].map(normalize_postcode)
    lookup = lookup.dropna(subset=["postcode_normalized", "LSOA_code"]).drop_duplicates("postcode_normalized")
    keep_columns = ["postcode", "postcode_normalized", "LSOA_code"]
    keep_columns.extend([column for column in ["LSOA_name", "borough"] if column in lookup.columns])
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

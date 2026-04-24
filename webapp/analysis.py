from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import pandas as pd

from webapp.config import AppConfig, BRITISH_NATIONAL_GRID
from webapp.data_access import (
    annotate_lsoa_geography,
    assign_candidates_to_lsoa,
    filter_scope,
    geocode_candidate_postcodes,
    load_lsoa_boundaries,
    load_need_inputs,
    load_neighbourhoods,
    load_postcode_lsoa_lookup,
)


INDEX_DEFINITIONS = {
    "deprivation_inverse": {
        "label": "Deprivation",
        "source_column": "deprivation_inverse",
        "description": "Inverse IMD decile so higher values represent higher deprivation.",
    },
    "population": {
        "label": "Population",
        "source_column": "population",
        "description": "Total resident population.",
    },
    "population_65_plus": {
        "label": "65+ population",
        "source_column": "population_65_plus",
        "description": "Residents aged 65 years and over.",
    },
    "older_people_proportion": {
        "label": "65+ proportion",
        "source_column": "older_people_proportion",
        "description": "Residents aged 65+ as a share of total population.",
    },
}

DEFAULT_HUB_SCORE_WEIGHTS = {
    "host_lsoa": 60.0,
    "catchment": 40.0,
}
DEFAULT_CATCHMENT_RADIUS_M = 2000
DEFAULT_SUGGESTION_COUNT = 5
DEFAULT_SUGGESTION_MIN_SPACING_M = 1000


@dataclass(frozen=True)
class AnalysisResult:
    need_scores: gpd.GeoDataFrame
    candidate_scores: gpd.GeoDataFrame
    invalid_postcodes: list[str]
    unresolved_postcodes: list[str]
    metadata: dict[str, object]


def min_max_scale(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    minimum = numeric.min(skipna=True)
    maximum = numeric.max(skipna=True)
    if pd.isna(minimum) or pd.isna(maximum):
        return pd.Series(pd.NA, index=series.index, dtype="Float64")
    if maximum == minimum:
        return pd.Series(1.0, index=series.index, dtype="Float64")
    return ((numeric - minimum) / (maximum - minimum)).astype("Float64")


def build_need_scores(
    config: AppConfig,
    geography_mode: str,
    icb_name: str | None,
    index_weights: dict[str, float],
    selected_neighbourhoods: list[str] | None = None,
) -> gpd.GeoDataFrame:
    need_inputs = load_need_inputs(config)
    neighbourhoods = load_neighbourhoods(config)
    lsoa_boundaries = load_lsoa_boundaries(config)
    lsoa_boundaries = annotate_lsoa_geography(lsoa_boundaries, neighbourhoods)
    scoped_boundaries = filter_scope(lsoa_boundaries, geography_mode, icb_name)
    if selected_neighbourhoods:
        scoped_boundaries = scoped_boundaries[
            scoped_boundaries["nghbrhd"].astype(str).isin(selected_neighbourhoods)
        ].copy()
    scoped = scoped_boundaries.merge(need_inputs, on="LSOA_code", how="inner", validate="1:1")

    for index_name, weight in index_weights.items():
        source_column = INDEX_DEFINITIONS[index_name]["source_column"]
        scaled_column = f"{index_name}_scaled"
        weighted_column = f"{index_name}_weighted"
        scoped[scaled_column] = min_max_scale(scoped[source_column])
        scoped[weighted_column] = scoped[scaled_column] * (weight / 100.0)

    weighted_columns = [f"{index_name}_weighted" for index_name in index_weights]
    scoped["need_score"] = scoped[weighted_columns].sum(axis=1, min_count=len(weighted_columns))
    scoped["need_score_pct"] = (scoped["need_score"] * 100).round(2)
    return scoped


def _score_single_candidate(
    candidate_row: pd.Series,
    centroids: gpd.GeoDataFrame,
    hub_score_weights: dict[str, float],
    catchment_radius_m: float,
) -> dict[str, object]:
    distances = centroids.geometry.distance(candidate_row.geometry)
    host_lsoa = candidate_row["LSOA_code"]

    host_need = centroids.loc[centroids["LSOA_code"].eq(host_lsoa), "need_score"]
    host_need_value = float(host_need.iloc[0]) if not host_need.empty and pd.notna(host_need.iloc[0]) else pd.NA

    in_catchment = centroids[(distances <= catchment_radius_m) & (~centroids["LSOA_code"].eq(host_lsoa))].copy()
    if not in_catchment.empty:
        in_catchment["distance_m"] = distances.loc[in_catchment.index]
        in_catchment["distance_weight"] = 1 - (in_catchment["distance_m"] / catchment_radius_m)
        in_catchment = in_catchment[in_catchment["distance_weight"] > 0].copy()

    catchment_mean = 0.0
    if not in_catchment.empty:
        catchment_scores = pd.to_numeric(in_catchment["need_score"], errors="coerce")
        catchment_weights = pd.to_numeric(in_catchment["distance_weight"], errors="coerce")
        valid_mask = catchment_scores.notna() & catchment_weights.notna() & (catchment_weights > 0)
        if valid_mask.any():
            catchment_mean = float(
                (catchment_scores.loc[valid_mask] * catchment_weights.loc[valid_mask]).sum()
                / catchment_weights.loc[valid_mask].sum()
            )

    host_weight = hub_score_weights["host_lsoa"] / 100.0
    catchment_weight = hub_score_weights["catchment"] / 100.0

    if pd.isna(host_need_value):
        hub_score = pd.NA
    else:
        hub_score = (host_weight * float(host_need_value)) + (catchment_weight * float(catchment_mean))

    return {
        "host_need_score": host_need_value,
        "weighted_catchment_need_score": float(catchment_mean),
        "lsoas_in_catchment": int(len(in_catchment)),
        "catchment_radius_m": float(catchment_radius_m),
        "hub_score": hub_score,
    }


def _representative_postcodes_by_lsoa(config: AppConfig) -> pd.DataFrame:
    lookup = load_postcode_lsoa_lookup(config.postcode_lsoa_lookup_csv)
    lookup = lookup.sort_values(["LSOA_code", "postcode"]).copy()
    aggregations: dict[str, tuple[str, str]] = {
        "postcode": ("postcode", "first"),
        "postcode_normalized": ("postcode_normalized", "first"),
        "postcode_count_in_lsoa": ("postcode", "size"),
    }
    if "LSOA_name" in lookup.columns:
        aggregations["LSOA_name"] = ("LSOA_name", "first")
    representative = lookup.groupby("LSOA_code", as_index=False).agg(**aggregations)
    return representative


def _select_spaced_suggestions(
    scored_bng: gpd.GeoDataFrame,
    suggestion_count: int,
    min_spacing_m: float,
    one_per_neighbourhood: bool,
) -> gpd.GeoDataFrame:
    selected_indices: list[int] = []
    selected_geometries = []
    selected_neighbourhoods: set[str] = set()

    for index, row in scored_bng.iterrows():
        neighbourhood = row.get("nghbrhd")
        neighbourhood_key = str(neighbourhood).strip() if pd.notna(neighbourhood) else ""
        if one_per_neighbourhood and neighbourhood_key and neighbourhood_key in selected_neighbourhoods:
            continue
        if min_spacing_m > 0 and any(row.geometry.distance(geometry) < min_spacing_m for geometry in selected_geometries):
            continue

        selected_indices.append(index)
        selected_geometries.append(row.geometry)
        if neighbourhood_key:
            selected_neighbourhoods.add(neighbourhood_key)
        if len(selected_indices) >= suggestion_count:
            break

    return scored_bng.loc[selected_indices].copy()


def suggest_candidate_hubs(
    need_scores: gpd.GeoDataFrame,
    config: AppConfig,
    hub_score_weights: dict[str, float],
    catchment_radius_m: float,
    suggestion_count: int = DEFAULT_SUGGESTION_COUNT,
    min_spacing_m: float = DEFAULT_SUGGESTION_MIN_SPACING_M,
    one_per_neighbourhood: bool = True,
) -> gpd.GeoDataFrame:
    need_columns = [
        column
        for column in ["LSOA_code", "ICB", "borough", "nghbrhd", "need_score", "need_score_pct"]
        if column in need_scores.columns
    ]
    scoped_need = need_scores.loc[:, [*need_columns, "geometry"]].copy()
    scoped_need = scoped_need[pd.to_numeric(scoped_need["need_score"], errors="coerce").notna()].copy()
    if scoped_need.empty:
        return gpd.GeoDataFrame(geometry=[], crs=need_scores.crs)

    representative_postcodes = _representative_postcodes_by_lsoa(config)
    centroids = scoped_need.to_crs(BRITISH_NATIONAL_GRID)
    centroids["geometry"] = centroids.geometry.centroid
    candidates = centroids.merge(representative_postcodes, on="LSOA_code", how="left")
    candidates = candidates.dropna(subset=["postcode"]).copy()
    if candidates.empty:
        return gpd.GeoDataFrame(geometry=[], crs=BRITISH_NATIONAL_GRID)

    scoring_centroids = centroids.loc[:, ["LSOA_code", "need_score", "need_score_pct", "geometry"]].copy()
    rows: list[dict[str, object]] = []
    for _, candidate in candidates.iterrows():
        row = candidate.drop(labels=["geometry"]).to_dict()
        row.update(_score_single_candidate(candidate, scoring_centroids, hub_score_weights, catchment_radius_m))
        row["candidate_source"] = "Suggested search location"
        row["coordinate_source"] = "Host LSOA centroid"
        row["geocode_source"] = "LSOA centroid"
        row["postcode_lookup_source"] = "postcode_to_lsoa_file"
        row["host_lsoa_in_scope"] = True
        row["is_suggested"] = True
        row["postcode_note"] = "Representative postcode in the host LSOA; map marker uses the LSOA centroid."
        rows.append(row)

    scored = pd.DataFrame(rows)
    scored["hub_score_pct"] = (pd.to_numeric(scored["hub_score"], errors="coerce") * 100).round(2)
    scored["host_need_score_pct"] = (pd.to_numeric(scored["host_need_score"], errors="coerce") * 100).round(2)
    scored["weighted_catchment_need_score_pct"] = (
        pd.to_numeric(scored["weighted_catchment_need_score"], errors="coerce") * 100
    ).round(2)
    scored_bng = gpd.GeoDataFrame(scored, geometry=candidates.geometry.reset_index(drop=True), crs=BRITISH_NATIONAL_GRID)
    scored_bng = scored_bng.sort_values(
        ["hub_score", "host_need_score", "need_score"],
        ascending=[False, False, False],
    )
    selected = _select_spaced_suggestions(
        scored_bng,
        max(1, int(suggestion_count)),
        float(min_spacing_m),
        one_per_neighbourhood,
    )
    selected = selected.reset_index(drop=True)
    selected["rank"] = selected.index + 1
    return selected.to_crs(need_scores.crs)


def rank_candidate_hubs(
    need_scores: gpd.GeoDataFrame,
    candidate_postcodes: list[str],
    config: AppConfig,
    hub_score_weights: dict[str, float],
    catchment_radius_m: float,
) -> tuple[gpd.GeoDataFrame, list[str], list[str]]:
    geocoded = geocode_candidate_postcodes(candidate_postcodes, config)
    assigned, unresolved = assign_candidates_to_lsoa(geocoded.candidates, need_scores, config)
    if assigned.empty:
        return assigned, geocoded.invalid_postcodes, unresolved

    scoped_need = need_scores.loc[:, ["LSOA_code", "ICB", "need_score", "need_score_pct", "geometry"]].copy()
    centroids = scoped_need.to_crs(BRITISH_NATIONAL_GRID)
    centroids["geometry"] = centroids.geometry.centroid

    assigned_bng = assigned.to_crs(BRITISH_NATIONAL_GRID)
    rows: list[dict[str, object]] = []
    for _, candidate in assigned_bng.iterrows():
        row = candidate.drop(labels=["geometry"]).to_dict()
        row.update(_score_single_candidate(candidate, centroids, hub_score_weights, catchment_radius_m))
        rows.append(row)

    scored = pd.DataFrame(rows)
    scored["hub_score_pct"] = (pd.to_numeric(scored["hub_score"], errors="coerce") * 100).round(2)
    scored["host_need_score_pct"] = (pd.to_numeric(scored["host_need_score"], errors="coerce") * 100).round(2)
    scored["weighted_catchment_need_score_pct"] = (
        pd.to_numeric(scored["weighted_catchment_need_score"], errors="coerce") * 100
    ).round(2)
    scored["candidate_source"] = "User supplied postcode"
    scored["coordinate_source"] = scored.get("geocode_source", "Configured postcode geocoder")
    scored["is_suggested"] = False
    scored = scored.sort_values(["hub_score", "host_need_score"], ascending=[False, False]).reset_index(drop=True)
    scored["rank"] = scored.index + 1
    return (
        gpd.GeoDataFrame(scored, geometry=assigned.geometry.reset_index(drop=True), crs=assigned.crs),
        geocoded.invalid_postcodes,
        unresolved,
    )


def run_analysis(
    config: AppConfig,
    geography_mode: str,
    icb_name: str | None,
    index_weights: dict[str, float],
    hub_score_weights: dict[str, float],
    catchment_radius_m: float,
    candidate_postcodes: list[str] | None = None,
    selected_neighbourhoods: list[str] | None = None,
    candidate_mode: str = "manual",
    suggestion_count: int = DEFAULT_SUGGESTION_COUNT,
    suggestion_min_spacing_m: float = DEFAULT_SUGGESTION_MIN_SPACING_M,
    suggestion_one_per_neighbourhood: bool = True,
) -> AnalysisResult:
    need_scores = build_need_scores(config, geography_mode, icb_name, index_weights, selected_neighbourhoods)
    if need_scores.empty:
        raise ValueError(
            "No LSOAs were available after applying the selected geography and neighbourhood filters. "
            "Check the ICB/neighbourhood selection and source geography joins."
        )
    if pd.to_numeric(need_scores["need_score"], errors="coerce").notna().sum() == 0:
        raise ValueError(
            "Need Scores could not be calculated for the selected scope. Check that the selected indices contain "
            "valid values within the chosen geography."
        )
    if candidate_mode == "suggested":
        candidate_scores = suggest_candidate_hubs(
            need_scores,
            config,
            hub_score_weights,
            catchment_radius_m,
            suggestion_count=suggestion_count,
            min_spacing_m=suggestion_min_spacing_m,
            one_per_neighbourhood=suggestion_one_per_neighbourhood,
        )
        invalid_postcodes: list[str] = []
        unresolved_postcodes: list[str] = []
    else:
        candidate_postcodes = candidate_postcodes or []
        if not candidate_postcodes:
            raise ValueError("Enter at least one candidate postcode, or switch to Suggest locations.")
        candidate_scores, invalid_postcodes, unresolved_postcodes = rank_candidate_hubs(
            need_scores,
            candidate_postcodes,
            config,
            hub_score_weights,
            catchment_radius_m,
        )
    if candidate_scores.empty:
        raise ValueError(
            "No candidate locations produced a scored result. Check postcode lookups and the selected geography."
        )
    metadata = {
        "candidate_mode": candidate_mode,
        "geography_mode": geography_mode,
        "icb_name": icb_name,
        "index_weights": index_weights,
        "hub_score_weights": hub_score_weights,
        "catchment_radius_m": float(catchment_radius_m),
        "suggestion_count_requested": int(suggestion_count),
        "suggestion_min_spacing_m": float(suggestion_min_spacing_m),
        "suggestion_one_per_neighbourhood": bool(suggestion_one_per_neighbourhood),
        "candidate_location_note": (
            "Suggested postcodes are representative postcodes inside high-scoring host LSOAs; "
            "map markers use LSOA centroids."
            if candidate_mode == "suggested"
            else "Manual candidate postcodes use configured postcode coordinates."
        ),
        "selected_neighbourhoods": selected_neighbourhoods or [],
        "lsoa_count": int(len(need_scores)),
        "candidate_count": int(len(candidate_scores)),
        "valid_need_score_count": int(pd.to_numeric(need_scores["need_score"], errors="coerce").notna().sum()),
        "valid_hub_score_count": int(pd.to_numeric(candidate_scores["hub_score"], errors="coerce").notna().sum()),
        "in_scope_host_count": int(candidate_scores.get("host_lsoa_in_scope", pd.Series(dtype=bool)).fillna(False).sum()),
        "generated_at": pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "data_version": pd.Timestamp.utcnow().date().isoformat(),
    }
    return AnalysisResult(
        need_scores=need_scores,
        candidate_scores=candidate_scores,
        invalid_postcodes=invalid_postcodes,
        unresolved_postcodes=unresolved_postcodes,
        metadata=metadata,
    )

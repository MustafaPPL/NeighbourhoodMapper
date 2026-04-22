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


def _score_single_candidate(candidate_row: pd.Series, centroids: gpd.GeoDataFrame) -> dict[str, object]:
    distances = centroids.geometry.distance(candidate_row.geometry)
    host_lsoa = candidate_row["LSOA_code"]

    host_need = centroids.loc[centroids["LSOA_code"].eq(host_lsoa), "need_score"]
    host_need_value = float(host_need.iloc[0]) if not host_need.empty and pd.notna(host_need.iloc[0]) else pd.NA

    local_band = centroids[(distances <= 500) & (~centroids["LSOA_code"].eq(host_lsoa))]
    wider_band = centroids[(distances > 500) & (distances <= 2000) & (~centroids["LSOA_code"].eq(host_lsoa))]

    local_mean = local_band["need_score"].mean() if not local_band.empty else 0.0
    wider_mean = wider_band["need_score"].mean() if not wider_band.empty else 0.0

    if pd.isna(host_need_value):
        hub_score = pd.NA
    else:
        hub_score = (0.60 * float(host_need_value)) + (0.25 * float(local_mean)) + (0.15 * float(wider_mean))

    return {
        "host_need_score": host_need_value,
        "mean_need_score_0_to_500m": float(local_mean),
        "mean_need_score_500m_to_2km": float(wider_mean),
        "lsoas_0_to_500m": int(len(local_band)),
        "lsoas_500m_to_2km": int(len(wider_band)),
        "hub_score": hub_score,
    }


def rank_candidate_hubs(
    need_scores: gpd.GeoDataFrame,
    candidate_postcodes: list[str],
    config: AppConfig,
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
        row.update(_score_single_candidate(candidate, centroids))
        rows.append(row)

    scored = pd.DataFrame(rows)
    scored["hub_score_pct"] = (pd.to_numeric(scored["hub_score"], errors="coerce") * 100).round(2)
    scored["host_need_score_pct"] = (pd.to_numeric(scored["host_need_score"], errors="coerce") * 100).round(2)
    scored["mean_need_score_0_to_500m_pct"] = (
        pd.to_numeric(scored["mean_need_score_0_to_500m"], errors="coerce") * 100
    ).round(2)
    scored["mean_need_score_500m_to_2km_pct"] = (
        pd.to_numeric(scored["mean_need_score_500m_to_2km"], errors="coerce") * 100
    ).round(2)
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
    candidate_postcodes: list[str],
    selected_neighbourhoods: list[str] | None = None,
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
    candidate_scores, invalid_postcodes, unresolved_postcodes = rank_candidate_hubs(
        need_scores,
        candidate_postcodes,
        config,
    )
    if candidate_scores.empty:
        raise ValueError(
            "No candidate postcodes produced a scored result. Check postcode geocoding and postcode-to-LSOA matching."
        )
    metadata = {
        "geography_mode": geography_mode,
        "icb_name": icb_name,
        "index_weights": index_weights,
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

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

from build_weighted_priority_map import (
    DEFAULT_65PLUS_CSV,
    DEFAULT_POPULATION_CSV,
    MAP_DPI,
    MAP_FIGSIZE,
    NEIGHBOURHOOD_LINE_HALO_WIDTH,
    NEIGHBOURHOOD_LINE_MAIN_WIDTH,
    OUTPUT_DIR,
    build_parks_and_gardens_legend_handle,
    build_icb_outline,
    fetch_parks_and_gardens,
    fetch_london_base_geographies,
    fetch_london_lsoa_boundaries,
    plot_parks_and_gardens_overlay,
    load_community_pharmacies,
    load_family_hubs,
    load_gp_practices,
    load_neighbourhoods,
)


DEFAULT_OUTPUT_CSV = OUTPUT_DIR / "neighbourhood_asset_density.csv"
DEFAULT_MAP_PNG = OUTPUT_DIR / "neighbourhood_service_desert_map.png"
DEFAULT_CHILD_AGE_MAX = 17
WGS84 = "EPSG:4326"
METRIC_CRS = "EPSG:3857"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a neighbourhood-level asset density dataset and service desert map "
            "for GPs, pharmacies, and family hubs across London."
        )
    )
    parser.add_argument(
        "--population-csv",
        type=Path,
        default=DEFAULT_POPULATION_CSV,
        help="LSOA population CSV with Total and age-band columns.",
    )
    parser.add_argument(
        "--older-people-csv",
        type=Path,
        default=DEFAULT_65PLUS_CSV,
        help="LSOA 65+ population CSV.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=DEFAULT_OUTPUT_CSV,
        help="Path for the neighbourhood summary CSV.",
    )
    parser.add_argument(
        "--map-png",
        type=Path,
        default=DEFAULT_MAP_PNG,
        help="Path for the service desert map PNG.",
    )
    parser.add_argument(
        "--child-age-max",
        type=int,
        default=DEFAULT_CHILD_AGE_MAX,
        help="Maximum age to count as child population for family hub denominator.",
    )
    return parser.parse_args()


def ensure_columns(df: pd.DataFrame, required: list[str], path: Path) -> None:
    missing = sorted(set(required).difference(df.columns))
    if missing:
        raise ValueError(f"Missing required columns in {path}: {missing}")


def build_child_columns(columns: pd.Index, child_age_max: int) -> list[str]:
    child_columns: list[str] = []
    for col in columns:
        label = str(col)
        if len(label) < 2:
            continue
        prefix = label[0]
        age = label[1:]
        if prefix not in {"F", "M"} or not age.isdigit():
            continue
        if int(age) <= child_age_max:
            child_columns.append(label)
    return child_columns


def load_population_denominators(population_csv: Path, older_people_csv: Path, child_age_max: int) -> pd.DataFrame:
    population = pd.read_csv(population_csv, dtype={"LSOA 2021 Code": str})
    ensure_columns(population, ["LSOA 2021 Code", "Total"], population_csv)

    child_columns = build_child_columns(population.columns, child_age_max)
    if not child_columns:
        raise ValueError(f"No child age columns found in {population_csv} for age <= {child_age_max}.")

    child_population = population[child_columns].apply(pd.to_numeric, errors="coerce").sum(axis=1)
    population = pd.DataFrame(
        {
            "LSOA_code": population["LSOA 2021 Code"],
            "total_population": pd.to_numeric(population["Total"], errors="coerce"),
            "child_population": child_population,
        }
    )

    older_people = pd.read_csv(older_people_csv, dtype=str)
    ensure_columns(
        older_people,
        ["Lower layer Super Output Areas Code", "Age (6 categories)", "Observation"],
        older_people_csv,
    )
    older_people = older_people[older_people["Age (6 categories)"].fillna("").eq("Aged 65 years and over")].copy()
    older_people["older_population_65_plus"] = pd.to_numeric(older_people["Observation"], errors="coerce")
    older_people = older_people.rename(columns={"Lower layer Super Output Areas Code": "LSOA_code"})
    older_people = older_people.loc[:, ["LSOA_code", "older_population_65_plus"]]

    return population.merge(older_people, on="LSOA_code", how="left", validate="1:1")


def build_neighbourhood_population(neighbourhoods: gpd.GeoDataFrame, denominators: pd.DataFrame) -> pd.DataFrame:
    lsoa_boundaries, _, _ = fetch_london_lsoa_boundaries()
    lsoa_boundaries = lsoa_boundaries.loc[:, ["LSOA_code", "geometry"]].drop_duplicates("LSOA_code")
    lsoa_with_population = lsoa_boundaries.merge(denominators, on="LSOA_code", how="inner", validate="1:1")

    lsoa_metric = lsoa_with_population.to_crs(METRIC_CRS)
    lsoa_metric["geometry"] = lsoa_metric.geometry.centroid
    lsoa_centroids = lsoa_metric.to_crs(WGS84)
    neighbourhoods_wgs84 = neighbourhoods.to_crs(WGS84)

    joined = gpd.sjoin(
        lsoa_centroids,
        neighbourhoods_wgs84.loc[:, ["nghbrhd", "borough", "ICB", "geometry"]],
        how="inner",
        predicate="within",
    )
    grouped = (
        joined.groupby(["nghbrhd", "borough", "ICB"], dropna=False)[
            ["total_population", "child_population", "older_population_65_plus"]
        ]
        .sum(min_count=1)
        .reset_index()
    )
    return grouped


def count_assets_by_neighbourhood(points: gpd.GeoDataFrame, neighbourhoods: gpd.GeoDataFrame, count_column: str) -> pd.DataFrame:
    joined = gpd.sjoin(
        points.to_crs(WGS84),
        neighbourhoods.to_crs(WGS84).loc[:, ["nghbrhd", "borough", "ICB", "geometry"]],
        how="inner",
        predicate="within",
    )
    counts = joined.groupby(["nghbrhd", "borough", "ICB"], dropna=False).size().reset_index(name=count_column)
    return counts


def rate_per_10k(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    values = pd.to_numeric(numerator, errors="coerce") / pd.to_numeric(denominator, errors="coerce")
    values = values.where(pd.to_numeric(denominator, errors="coerce") > 0)
    return (values * 10000).astype("Float64")


def inverse_rank_score(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return pd.Series(pd.NA, index=series.index, dtype="Float64")
    ranks = valid.rank(method="average", pct=True)
    score = 1 - ranks
    output = pd.Series(pd.NA, index=series.index, dtype="Float64")
    output.loc[valid.index] = score.astype("Float64")
    return output


def build_summary(neighbourhoods: gpd.GeoDataFrame, args: argparse.Namespace) -> gpd.GeoDataFrame:
    denominators = load_population_denominators(args.population_csv, args.older_people_csv, args.child_age_max)
    neighbourhood_population = build_neighbourhood_population(neighbourhoods, denominators)

    summary = neighbourhoods.loc[:, ["nghbrhd", "borough", "ICB", "geometry"]].copy()
    summary = summary.merge(neighbourhood_population, on=["nghbrhd", "borough", "ICB"], how="left", validate="1:1")

    gp_counts = count_assets_by_neighbourhood(load_gp_practices(), neighbourhoods, "gp_sites")
    pharmacy_counts = count_assets_by_neighbourhood(load_community_pharmacies(), neighbourhoods, "community_pharmacies")
    family_hub_counts = count_assets_by_neighbourhood(load_family_hubs(), neighbourhoods, "family_hubs")

    for counts in [gp_counts, pharmacy_counts, family_hub_counts]:
        summary = summary.merge(counts, on=["nghbrhd", "borough", "ICB"], how="left", validate="1:1")

    for column in ["gp_sites", "community_pharmacies", "family_hubs"]:
        summary[column] = summary[column].fillna(0).astype(int)

    summary["gp_sites_per_10k_population"] = rate_per_10k(summary["gp_sites"], summary["total_population"])
    summary["pharmacies_per_10k_population"] = rate_per_10k(
        summary["community_pharmacies"], summary["total_population"]
    )
    summary["family_hubs_per_10k_children"] = rate_per_10k(summary["family_hubs"], summary["child_population"])

    summary["gp_desert_score"] = inverse_rank_score(summary["gp_sites_per_10k_population"])
    summary["pharmacy_desert_score"] = inverse_rank_score(summary["pharmacies_per_10k_population"])
    summary["family_hub_desert_score"] = inverse_rank_score(summary["family_hubs_per_10k_children"])
    summary["service_desert_score"] = (
        summary[["gp_desert_score", "pharmacy_desert_score", "family_hub_desert_score"]]
        .apply(pd.to_numeric, errors="coerce")
        .mean(axis=1)
    )
    summary["service_desert_score_pct"] = (summary["service_desert_score"] * 100).round(1)
    summary["service_desert_flag"] = summary["service_desert_score"].ge(summary["service_desert_score"].quantile(0.8))

    summary = summary.sort_values(["service_desert_score", "gp_sites_per_10k_population"], ascending=[False, True])
    summary["service_desert_rank"] = range(1, len(summary) + 1)
    return summary


def create_map(summary: gpd.GeoDataFrame, map_png: Path) -> None:
    neighbourhoods_3857 = summary.to_crs(METRIC_CRS)
    london_boroughs, _, envelope = fetch_london_base_geographies()
    boroughs_3857 = london_boroughs.to_crs(METRIC_CRS)
    icb_outline_3857 = build_icb_outline(london_boroughs).to_crs(METRIC_CRS)
    try:
        parks_and_gardens_3857 = fetch_parks_and_gardens(london_boroughs, envelope).to_crs(METRIC_CRS)
    except Exception as exc:
        print(f"[warn] Could not load Historic England Parks and Gardens layer: {exc}")
        parks_and_gardens_3857 = gpd.GeoDataFrame(geometry=[], crs=WGS84).to_crs(METRIC_CRS)

    fig, ax = plt.subplots(figsize=MAP_FIGSIZE)
    cax = inset_axes(ax, width="4%", height="30%", loc="lower right", borderpad=2)

    neighbourhoods_3857.plot(
        column="service_desert_score_pct",
        cmap="YlOrRd",
        linewidth=0.0,
        alpha=0.92,
        legend=True,
        legend_kwds={"cax": cax},
        missing_kwds={"color": "#eeeeee", "label": "Missing data"},
        ax=ax,
    )
    cax.tick_params(labelsize=8, length=0, pad=2)
    cax.yaxis.set_ticks_position("left")
    cax.set_ylabel("Service desert score", fontsize=8)

    plot_parks_and_gardens_overlay(ax, parks_and_gardens_3857)

    boroughs_3857.boundary.plot(ax=ax, linewidth=0.35, color="#606060", alpha=0.7, zorder=3)
    neighbourhoods_3857.boundary.plot(
        ax=ax,
        linewidth=NEIGHBOURHOOD_LINE_HALO_WIDTH,
        color="white",
        alpha=0.7,
        zorder=4,
    )
    neighbourhoods_3857.boundary.plot(
        ax=ax,
        linewidth=NEIGHBOURHOOD_LINE_MAIN_WIDTH,
        color="#1a1a1a",
        alpha=0.9,
        zorder=5,
    )
    flagged = neighbourhoods_3857[neighbourhoods_3857["service_desert_flag"].fillna(False)]
    if not flagged.empty:
        flagged.boundary.plot(ax=ax, linewidth=2.2, color="#7f0000", alpha=0.95, zorder=6)

    icb_outline_3857.boundary.plot(ax=ax, linewidth=2.0, color="white", alpha=0.55, zorder=6.5)
    icb_outline_3857.boundary.plot(
        ax=ax,
        linewidth=0.9,
        color="#b7bec7",
        linestyle=(0, (6, 6)),
        alpha=0.95,
        zorder=7,
    )

    minx, miny, maxx, maxy = neighbourhoods_3857.total_bounds
    pad_x = (maxx - minx) * 0.03
    pad_y = (maxy - miny) * 0.03
    ax.set_xlim(minx - pad_x, maxx + pad_x)
    ax.set_ylim(miny - pad_y, maxy + pad_y)

    ax.set_axis_off()
    ax.set_title(
        "London neighbourhood service desert map\n"
        "Combined low provision score from GP, pharmacy, and family hub density",
        fontsize=14,
        pad=16,
    )
    if len(parks_and_gardens_3857) > 0:
        fig.legend(
            handles=[build_parks_and_gardens_legend_handle()],
            loc="lower center",
            bbox_to_anchor=(0.5, 0.03),
            ncol=1,
            fontsize=8,
            frameon=True,
            handletextpad=0.5,
        )
        bottom = 0.08
    else:
        bottom = 0.02
    fig.subplots_adjust(left=0.02, right=0.98, top=0.94, bottom=bottom)
    map_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(map_png, dpi=MAP_DPI, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    neighbourhoods = load_neighbourhoods()
    summary = build_summary(neighbourhoods, args)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    csv_ready = pd.DataFrame(summary.drop(columns="geometry"))
    csv_ready.to_csv(args.output_csv, index=False)
    create_map(summary, args.map_png)

    print(f"Created: {args.output_csv}")
    print(f"Created: {args.map_png}")
    print(f"Neighbourhoods: {len(summary)}")
    print()
    print("Top 10 service desert neighbourhoods:")
    print(
        csv_ready.head(10).loc[
            :,
            [
                "service_desert_rank",
                "nghbrhd",
                "borough",
                "ICB",
                "service_desert_score_pct",
                "gp_sites_per_10k_population",
                "pharmacies_per_10k_population",
                "family_hubs_per_10k_children",
            ],
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()

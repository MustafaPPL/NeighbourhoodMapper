from __future__ import annotations

import io
import argparse
import time
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import requests
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

from project_paths import DATA_DIR, OUTPUT_DIR, get_older_people_dir


ROOT = Path(__file__).resolve().parent
OLDER_PEOPLE_DIR = get_older_people_dir()

DEFAULT_DEPRIVATION_CSV = DATA_DIR / "core20_lsoa_latest.csv"
DEFAULT_POPULATION_CSV = DATA_DIR / "LSOA Population.csv"
DEFAULT_65PLUS_CSV = OLDER_PEOPLE_DIR / "65+ Population London LSOA.csv"
DEFAULT_SCOPE = "icb"
DEFAULT_TARGET_ICB = "NHS North East London ICB"
DEFAULT_OUTPUT_CSV = OUTPUT_DIR / "north_east_london_weighted_priority_scores.csv"
DEFAULT_MAP_PNG = OUTPUT_DIR / "north_east_london_weighted_priority_map.png"
DEFAULT_DEPRIVATION_MAP_PNG = OUTPUT_DIR / "north_east_london_deprivation_priority_map.png"
DEFAULT_AGE_MAP_PNG = OUTPUT_DIR / "north_east_london_age_65_plus_priority_map.png"
DEFAULT_AGE_DENSITY_MAP_PNG = OUTPUT_DIR / "north_east_london_age_65_plus_density_map.png"
DEFAULT_POPULATION_MAP_PNG = OUTPUT_DIR / "north_east_london_population_priority_map.png"

DEPRIVATION_WEIGHT = 50
OLDER_PEOPLE_WEIGHT = 30
POPULATION_WEIGHT = 20

LAD_FS_BASE = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Local_Authority_Districts_December_2023_Boundaries_UK_BGC/FeatureServer/0"
)
LSOA_FS_BASE = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V5/FeatureServer/0"
)
WARD_FS_BASE = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Wards_December_2023_Boundaries_UK_BGC/FeatureServer/0"
)
PARKS_GARDENS_FS_BASE = (
    "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/ArcGIS/rest/services/"
    "National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer/7"
)
REQUEST_TIMEOUT = 60
USER_AGENT = "London-weighted-priority-mapper/1.0 (+python requests)"
MAP_FIGSIZE = (12, 14)
MAP_DPI = 220
AREA_CRS = "EPSG:27700"
NEIGHBOURHOOD_SHP = OLDER_PEOPLE_DIR / "neighbourhoods_shapefile.shp"
NEIGHBOURHOOD_LINE_MAIN_WIDTH = 1.0
NEIGHBOURHOOD_LINE_HALO_WIDTH = 1.6
GP_GEO_CACHE_CSV = OLDER_PEOPLE_DIR / "combined_gps_geocoded.csv"
PHARMACY_CSV = OLDER_PEOPLE_DIR / "Pharmacy List.csv"
PHARMACY_GEO_CACHE_CSV = OLDER_PEOPLE_DIR / "pharmacy_geocoded.csv"
FAMILY_HUB_CSV = OLDER_PEOPLE_DIR / "Family Hub Sites.csv"
FAMILY_HUB_GEO_CACHE_CSV = OLDER_PEOPLE_DIR / "family_hub_geocoded.csv"
NHS_TRUSTS_XLSX = DATA_DIR / "london_nhs_trusts.xlsx"
CIVIC_CENTRES_CSV = DATA_DIR / "london_civic_centres.csv"
LIBRARIES_CSV = DATA_DIR / "london_libraries.csv"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
LIBRARIES_OVERPASS_QUERY = """
[out:json][timeout:25];
area["name"="London"]->.searchArea;
(
  node["amenity"="library"](area.searchArea);
  way["amenity"="library"](area.searchArea);
  relation["amenity"="library"](area.searchArea);
);
out center;
"""
ICB_OUTLINE_WIDTH = 0.9
ICB_OUTLINE_COLOR = "#b7bec7"
PARKS_GARDENS_LABEL = "Registered park/garden"
PARKS_GARDENS_FILL_COLOR = "#D3FFBE"
PARKS_GARDENS_EDGE_COLOR = "#267300"
PARKS_GARDENS_FILL_ALPHA = 0.36
PARKS_GARDENS_EDGE_ALPHA = 0.9
PARKS_GARDENS_LINE_WIDTH = 0.55
LONDON_HWB_PATTERN = (
    "BARKING|BARNET|BEXLEY|BRENT|BROMLEY|CAMDEN|CITY OF LONDON|CROYDON|EALING|ENFIELD|"
    "GREENWICH|HACKNEY|HAMMERSMITH|HARINGEY|HARROW|HAVERING|HILLINGDON|HOUNSLOW|ISLINGTON|"
    "KENSINGTON|KINGSTON|LAMBETH|LEWISHAM|MERTON|NEWHAM|REDBRIDGE|RICHMOND|SOUTHWARK|"
    "SUTTON|TOWER HAMLETS|WALTHAM FOREST|WANDSWORTH|WESTMINSTER"
)
ICB_BOROUGHS_BY_LAD = {
    "NHS North Central London ICB": {"Barnet", "Camden", "Enfield", "Haringey", "Islington"},
    "NHS North East London ICB": {
        "Barking and Dagenham",
        "City of London",
        "Hackney",
        "Havering",
        "Newham",
        "Redbridge",
        "Tower Hamlets",
        "Waltham Forest",
    },
    "NHS North West London ICB": {
        "Brent",
        "Ealing",
        "Hammersmith and Fulham",
        "Harrow",
        "Hillingdon",
        "Hounslow",
        "Kensington and Chelsea",
        "Westminster",
    },
    "NHS South East London ICB": {"Bexley", "Bromley", "Greenwich", "Lambeth", "Lewisham", "Southwark"},
    "NHS South West London ICB": {
        "Croydon",
        "Kingston upon Thames",
        "Merton",
        "Richmond upon Thames",
        "Sutton",
        "Wandsworth",
    },
}

ICB_SHORT_NAMES = {
    "NHS North Central London ICB": "North Central London",
    "NHS North East London ICB": "North East London",
    "NHS North West London ICB": "North West London",
    "NHS South East London ICB": "South East London",
    "NHS South West London ICB": "South West London",
}

SCOPE_CHOICES = ["all_london", "icb"]
MAP_CHOICES = ["deprivation", "age", "age_density", "population", "weighted"]
DEFAULT_MAP_SELECTION = ["deprivation", "age", "population", "weighted"]

LONDON_BOROUGHS_AND_CITY = {
    "Barking and Dagenham",
    "Barnet",
    "Bexley",
    "Brent",
    "Bromley",
    "Camden",
    "City of London",
    "Croydon",
    "Ealing",
    "Enfield",
    "Greenwich",
    "Hackney",
    "Hammersmith and Fulham",
    "Haringey",
    "Harrow",
    "Havering",
    "Hillingdon",
    "Hounslow",
    "Islington",
    "Kensington and Chelsea",
    "Kingston upon Thames",
    "Lambeth",
    "Lewisham",
    "Merton",
    "Newham",
    "Redbridge",
    "Richmond upon Thames",
    "Southwark",
    "Sutton",
    "Tower Hamlets",
    "Waltham Forest",
    "Wandsworth",
    "Westminster",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create an LSOA-level weighted priority dataset from deprivation, "
            "65+ population, and overall population."
        )
    )
    parser.add_argument(
        "--deprivation-csv",
        type=Path,
        default=DEFAULT_DEPRIVATION_CSV,
        help="CSV containing at least LSOA_code, IMD_decile, and population.",
    )
    parser.add_argument(
        "--older-people-csv",
        type=Path,
        default=DEFAULT_65PLUS_CSV,
        help="CSV containing LSOA-level 65+ counts.",
    )
    parser.add_argument(
        "--population-csv",
        type=Path,
        default=DEFAULT_POPULATION_CSV,
        help="CSV containing LSOA-level total population.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=DEFAULT_OUTPUT_CSV,
        help="Path for the scored output CSV.",
    )
    parser.add_argument(
        "--map-png",
        type=Path,
        default=DEFAULT_MAP_PNG,
        help="Path for the output choropleth PNG.",
    )
    parser.add_argument(
        "--deprivation-map-png",
        type=Path,
        default=DEFAULT_DEPRIVATION_MAP_PNG,
        help="Path for the deprivation score choropleth PNG.",
    )
    parser.add_argument(
        "--age-map-png",
        type=Path,
        default=DEFAULT_AGE_MAP_PNG,
        help="Path for the age 65+ score choropleth PNG.",
    )
    parser.add_argument(
        "--age-density-map-png",
        type=Path,
        default=DEFAULT_AGE_DENSITY_MAP_PNG,
        help="Path for the age 65+ density choropleth PNG.",
    )
    parser.add_argument(
        "--population-map-png",
        type=Path,
        default=DEFAULT_POPULATION_MAP_PNG,
        help="Path for the population score choropleth PNG.",
    )
    parser.add_argument(
        "--scope",
        choices=SCOPE_CHOICES,
        default=DEFAULT_SCOPE,
        help="Run for all London or a specific ICB. Defaults to icb.",
    )
    parser.add_argument(
        "--icb",
        choices=list(ICB_BOROUGHS_BY_LAD),
        default=DEFAULT_TARGET_ICB,
        help="London ICB footprint to score and map when --scope icb is used.",
    )
    parser.add_argument(
        "--no-map",
        action="store_true",
        help="Skip choropleth map generation.",
    )
    parser.add_argument(
        "--map",
        action="append",
        choices=MAP_CHOICES,
        default=None,
        help=(
            "Map(s) to render. Repeat to include multiple. Defaults to the core component maps "
            "plus the weighted map for the selected scope: deprivation, age, population, and weighted."
        ),
    )
    return parser.parse_args()


def request_json(url: str, params: dict, max_retries: int = 5) -> dict:
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except Exception:
            if attempt == max_retries:
                raise
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError("unreachable")


def arcgis_query_to_gdf(
    layer_base_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    out_sr: int = 4326,
    geometry: tuple[float, float, float, float] | None = None,
    page_size: int = 500,
    max_retries: int = 5,
) -> gpd.GeoDataFrame:
    query_url = f"{layer_base_url}/query"
    count_params = {"where": where, "returnCountOnly": "true", "f": "json"}
    if geometry is not None:
        xmin, ymin, xmax, ymax = geometry
        count_params.update(
            {
                "geometry": f"{xmin},{ymin},{xmax},{ymax}",
                "geometryType": "esriGeometryEnvelope",
                "inSR": out_sr,
                "spatialRel": "esriSpatialRelIntersects",
            }
        )

    total = int(request_json(query_url, count_params).get("count", 0))
    parts: list[gpd.GeoDataFrame] = []
    fetched = 0
    while fetched < total:
        params = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": out_sr,
            "resultOffset": fetched,
            "resultRecordCount": page_size,
            "f": "geojson",
        }
        if geometry is not None:
            xmin, ymin, xmax, ymax = geometry
            params.update(
                {
                    "geometry": f"{xmin},{ymin},{xmax},{ymax}",
                    "geometryType": "esriGeometryEnvelope",
                    "inSR": out_sr,
                    "spatialRel": "esriSpatialRelIntersects",
                }
            )

        response = None
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.get(
                    query_url,
                    params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                part = gpd.read_file(io.BytesIO(response.content))
                break
            except Exception:
                if attempt == max_retries:
                    raise
                time.sleep(min(2 ** attempt, 20))

        if len(part) == 0:
            break
        parts.append(part)
        fetched += len(part)

    if not parts:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs)


def find_col(columns: pd.Index, candidates: list[str]) -> str | None:
    lookup = {str(col).strip().lower(): str(col) for col in columns}
    for candidate in candidates:
        match = lookup.get(candidate.strip().lower())
        if match:
            return match
    return None


def normalize_postcode(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip().upper().replace(" ", "")


def points_to_gdf(df: pd.DataFrame) -> gpd.GeoDataFrame:
    points = df.copy()
    points["Latitude"] = pd.to_numeric(points["Latitude"], errors="coerce")
    points["Longitude"] = pd.to_numeric(points["Longitude"], errors="coerce")
    points = points.dropna(subset=["Latitude", "Longitude"]).copy()
    return gpd.GeoDataFrame(
        points,
        geometry=gpd.points_from_xy(points["Longitude"], points["Latitude"]),
        crs="EPSG:4326",
    )


def min_max_scale(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return pd.Series(pd.NA, index=series.index, dtype="Float64")

    minimum = valid.min()
    maximum = valid.max()
    if minimum == maximum:
        return pd.Series(1.0, index=series.index, dtype="Float64")

    scaled = (numeric - minimum) / (maximum - minimum)
    return scaled.astype("Float64")


def format_whole_number(value: float) -> str:
    return f"{int(round(value)):,}"


def log_step(message: str) -> None:
    print(f"[audit] {message}")


def summarise_numeric(series: pd.Series) -> str:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return "no valid values"
    return (
        f"count={len(numeric):,}, min={numeric.min():,.2f}, "
        f"median={numeric.median():,.2f}, max={numeric.max():,.2f}"
    )


def print_scoring_audit(df: pd.DataFrame) -> None:
    log_step("Scoring audit summary")
    print(f"  Deprivation score: {summarise_numeric(df['deprivation_score'])}")
    print(f"  65+ proportion: {summarise_numeric(df['older_people_proportion'])}")
    print(f"  Population score input uses raw population totals: {summarise_numeric(df['population'])}")
    print(f"  Population score: {summarise_numeric(df['population_score'])}")
    print(f"  Weighted priority score: {summarise_numeric(df['weighted_priority_score'])}")


def build_population_bands(series: pd.Series) -> tuple[pd.Series, list[str]]:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        empty = pd.Series(pd.NA, index=series.index, dtype="object")
        return empty, []

    quantiles = [0.0, 0.2, 0.4, 0.6, 0.8, 0.95, 1.0]
    raw_edges = [float(valid.quantile(q)) for q in quantiles]
    edges: list[float] = []
    for edge in raw_edges:
        if not edges or edge > edges[-1]:
            edges.append(edge)

    if len(edges) < 2:
        label = format_whole_number(valid.iloc[0])
        single_band = pd.Series(label, index=series.index, dtype="object")
        single_band.loc[numeric.isna()] = pd.NA
        return single_band, [label]

    labels = [
        f"{format_whole_number(lower)} to {format_whole_number(upper)}"
        for lower, upper in zip(edges[:-1], edges[1:])
    ]
    bands = pd.cut(numeric, bins=edges, labels=labels, include_lowest=True, duplicates="drop")
    return bands.astype("object"), labels


def add_population_density_columns(map_df_3857: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    output = map_df_3857.copy()
    area_sq_km = output.to_crs(AREA_CRS).geometry.area / 1_000_000
    output["lsoa_area_sq_km"] = area_sq_km.astype("Float64")
    output["population_density_per_sq_km"] = (
        pd.to_numeric(output["population_raw"], errors="coerce") / output["lsoa_area_sq_km"]
    ).astype("Float64")
    output.loc[output["lsoa_area_sq_km"] <= 0, "population_density_per_sq_km"] = pd.NA
    return output


def add_older_people_density_columns(map_df_3857: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    output = add_population_density_columns(map_df_3857)
    output["older_people_density_per_sq_km"] = (
        pd.to_numeric(output["population_65_plus"], errors="coerce") / output["lsoa_area_sq_km"]
    ).astype("Float64")
    output.loc[output["lsoa_area_sq_km"] <= 0, "older_people_density_per_sq_km"] = pd.NA
    return output


def load_deprivation_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"LSOA_code": str})
    required = {"LSOA_code", "IMD_decile"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")

    df = df.loc[:, ["LSOA_code", "IMD_decile"]].copy()
    df["IMD_decile"] = pd.to_numeric(df["IMD_decile"], errors="coerce")
    return df


def load_65plus_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    required = {
        "Lower layer Super Output Areas Code",
        "Age (6 categories)",
        "Observation",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")

    df = df[df["Age (6 categories)"].fillna("").eq("Aged 65 years and over")].copy()
    df["population_65_plus"] = pd.to_numeric(df["Observation"], errors="coerce")
    df = df.rename(columns={"Lower layer Super Output Areas Code": "LSOA_code"})
    return df.loc[:, ["LSOA_code", "population_65_plus"]]


def load_population_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    required = {"LSOA 2021 Code", "Total"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")

    df = df.rename(columns={"LSOA 2021 Code": "LSOA_code", "Total": "population"})
    df["population"] = pd.to_numeric(df["population"], errors="coerce")
    return df.loc[:, ["LSOA_code", "population"]].drop_duplicates("LSOA_code")


def add_component_scores(df: pd.DataFrame) -> pd.DataFrame:
    # Lower IMD deciles are more deprived, so invert the scale.
    df["deprivation_score"] = (10 - df["IMD_decile"]) / 9
    df.loc[~df["IMD_decile"].between(1, 10), "deprivation_score"] = pd.NA

    df["older_people_proportion"] = df["population_65_plus"] / df["population"]
    df.loc[~df["older_people_proportion"].between(0, 1), "older_people_proportion"] = pd.NA

    df["older_people_score"] = min_max_scale(df["older_people_proportion"])
    df["population_score"] = min_max_scale(df["population"])
    df["population_raw"] = pd.to_numeric(df["population"], errors="coerce")
    df["deprivation_score_pct"] = (df["deprivation_score"] * 100).round(2)
    df["older_people_score_pct"] = (df["older_people_score"] * 100).round(2)
    df["population_score_pct"] = (df["population_score"] * 100).round(2)

    total_weight = DEPRIVATION_WEIGHT + OLDER_PEOPLE_WEIGHT + POPULATION_WEIGHT
    df["weighted_priority_score"] = (
        df["deprivation_score"] * DEPRIVATION_WEIGHT
        + df["older_people_score"] * OLDER_PEOPLE_WEIGHT
        + df["population_score"] * POPULATION_WEIGHT
    ) / total_weight
    df["weighted_priority_score_pct"] = (df["weighted_priority_score"] * 100).round(2)
    return df


def finalise_output(df: pd.DataFrame) -> pd.DataFrame:
    scored = df.dropna(
        subset=[
            "deprivation_score",
            "older_people_score",
            "population_score",
            "weighted_priority_score",
        ]
    ).copy()

    scored = scored.sort_values(
        ["weighted_priority_score", "deprivation_score", "older_people_proportion", "population"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    scored["priority_rank"] = scored.index + 1
    scored["priority_decile"] = pd.qcut(
        scored["weighted_priority_score"],
        10,
        labels=list(range(10, 0, -1)),
        duplicates="drop",
    ).astype(str)

    return scored.loc[
        :,
        [
            "priority_rank",
            "priority_decile",
            "LSOA_code",
            "IMD_decile",
            "population",
            "population_raw",
            "population_65_plus",
            "older_people_proportion",
            "deprivation_score",
            "deprivation_score_pct",
            "older_people_score",
            "older_people_score_pct",
            "population_score",
            "population_score_pct",
            "weighted_priority_score",
            "weighted_priority_score_pct",
        ],
    ]


def get_target_boroughs(icb_name: str) -> set[str]:
    boroughs = ICB_BOROUGHS_BY_LAD.get(icb_name)
    if not boroughs:
        raise ValueError(f"Unsupported ICB: {icb_name}")
    return boroughs


def get_icb_display_name(icb_name: str) -> str:
    return ICB_SHORT_NAMES.get(icb_name, icb_name.replace("NHS ", "").replace(" ICB", ""))


def slugify_scope_label(text: str) -> str:
    return (
        text.lower()
        .replace("nhs ", "")
        .replace(" icb", "")
        .replace("&", "and")
        .replace(":", "")
        .replace(",", "")
        .replace(" ", "_")
    )


def get_scope_label(scope: str, icb_name: str | None = None) -> str:
    if scope == "all_london":
        return "All London"
    if icb_name is None:
        raise ValueError("icb_name is required when scope is 'icb'.")
    return get_icb_display_name(icb_name)


def get_default_output_paths(scope: str, icb_name: str | None = None) -> dict[str, Path]:
    if scope == "all_london":
        prefix = "all_london"
    else:
        if icb_name is None:
            raise ValueError("icb_name is required when scope is 'icb'.")
        prefix = slugify_scope_label(get_icb_display_name(icb_name))

    return {
        "output_csv": OUTPUT_DIR / f"{prefix}_weighted_priority_scores.csv",
        "map_png": OUTPUT_DIR / f"{prefix}_weighted_priority_map.png",
        "deprivation_map_png": OUTPUT_DIR / f"{prefix}_deprivation_priority_map.png",
        "age_map_png": OUTPUT_DIR / f"{prefix}_age_65_plus_priority_map.png",
        "age_density_map_png": OUTPUT_DIR / f"{prefix}_age_65_plus_density_map.png",
        "population_map_png": OUTPUT_DIR / f"{prefix}_population_priority_map.png",
    }


def fetch_london_base_geographies() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, tuple[float, float, float, float]]:
    lad = arcgis_query_to_gdf(LAD_FS_BASE, out_sr=4326)
    lad_name_col = find_col(lad.columns, ["LAD23NM", "LAD24NM", "LAD22NM", "LADNM", "NAME"])
    if not lad_name_col:
        raise ValueError(f"Could not find LAD name column. Available: {list(lad.columns)}")

    london_boroughs = lad[lad[lad_name_col].isin(LONDON_BOROUGHS_AND_CITY)].copy()
    if london_boroughs.empty:
        raise ValueError("No London boroughs matched in LAD layer.")

    xmin, ymin, xmax, ymax = london_boroughs.total_bounds
    pad = 0.05
    envelope = (xmin - pad, ymin - pad, xmax + pad, ymax + pad)
    return london_boroughs, lad, envelope


def fetch_target_base_geographies(
    icb_name: str,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, tuple[float, float, float, float]]:
    london_boroughs, lad, _ = fetch_london_base_geographies()
    lad_name_col = find_col(london_boroughs.columns, ["LAD23NM", "LAD24NM", "LAD22NM", "LADNM", "NAME"])
    if not lad_name_col:
        raise ValueError(f"Could not find LAD name column. Available: {list(london_boroughs.columns)}")

    target_boroughs = london_boroughs[london_boroughs[lad_name_col].isin(get_target_boroughs(icb_name))].copy()
    if target_boroughs.empty:
        raise ValueError(f"No boroughs matched for {icb_name}.")

    xmin, ymin, xmax, ymax = target_boroughs.total_bounds
    pad = 0.03
    envelope = (xmin - pad, ymin - pad, xmax + pad, ymax + pad)
    return target_boroughs, lad, envelope


def fetch_target_lsoa_boundaries(
    icb_name: str,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, tuple[float, float, float, float]]:
    target_boroughs, _, envelope = fetch_target_base_geographies(icb_name)

    lsoa = arcgis_query_to_gdf(LSOA_FS_BASE, out_sr=4326, geometry=envelope)
    target_union = target_boroughs.union_all()
    lsoa = lsoa[lsoa.intersects(target_union)].copy()

    lsoa_code_col = find_col(lsoa.columns, ["LSOA21CD", "LSOA11CD", "LSOA_CODE", "CODE"])
    if not lsoa_code_col:
        raise ValueError(f"Could not find LSOA code column. Available: {list(lsoa.columns)}")

    return lsoa.rename(columns={lsoa_code_col: "LSOA_code"}), target_boroughs, envelope


def fetch_target_wards(target_boroughs: gpd.GeoDataFrame, envelope: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    wards = arcgis_query_to_gdf(WARD_FS_BASE, out_sr=4326, geometry=envelope)
    target_union = target_boroughs.union_all()
    return wards[wards.intersects(target_union)].copy()


def fetch_london_lsoa_boundaries() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, tuple[float, float, float, float]]:
    london_boroughs, _, envelope = fetch_london_base_geographies()

    lsoa = arcgis_query_to_gdf(LSOA_FS_BASE, out_sr=4326, geometry=envelope)
    london_union = london_boroughs.union_all()
    lsoa = lsoa[lsoa.intersects(london_union)].copy()

    lsoa_code_col = find_col(lsoa.columns, ["LSOA21CD", "LSOA11CD", "LSOA_CODE", "CODE"])
    if not lsoa_code_col:
        raise ValueError(f"Could not find LSOA code column. Available: {list(lsoa.columns)}")

    return lsoa.rename(columns={lsoa_code_col: "LSOA_code"}), london_boroughs, envelope


def fetch_london_wards(london_boroughs: gpd.GeoDataFrame, envelope: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    wards = arcgis_query_to_gdf(WARD_FS_BASE, out_sr=4326, geometry=envelope)
    london_union = london_boroughs.union_all()
    return wards[wards.intersects(london_union)].copy()


def load_neighbourhoods(icb_name: str | None = None) -> gpd.GeoDataFrame:
    if not NEIGHBOURHOOD_SHP.exists():
        raise FileNotFoundError(f"Missing file: {NEIGHBOURHOOD_SHP}")
    neighbourhoods = gpd.read_file(NEIGHBOURHOOD_SHP).to_crs(4326)
    if icb_name is not None and "ICB" in neighbourhoods.columns:
        icb_label = get_icb_display_name(icb_name)
        neighbourhoods = neighbourhoods[neighbourhoods["ICB"].astype(str).str.strip().eq(icb_label)].copy()
    return neighbourhoods


def build_icb_outline(london_boroughs: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    borough_to_icb = {
        borough: icb
        for icb, boroughs in ICB_BOROUGHS_BY_LAD.items()
        for borough in boroughs
    }
    outlines = london_boroughs.copy()
    lad_name_col = find_col(outlines.columns, ["LAD23NM", "LAD24NM", "LAD22NM", "LADNM", "NAME"])
    if not lad_name_col:
        raise ValueError(f"Could not find LAD name column. Available: {list(outlines.columns)}")
    outlines["__icb"] = outlines[lad_name_col].map(borough_to_icb)
    outlines = outlines.dropna(subset=["__icb"]).dissolve(by="__icb", as_index=False)
    return outlines


def load_gp_practices() -> gpd.GeoDataFrame:
    if not GP_GEO_CACHE_CSV.exists():
        raise FileNotFoundError(f"Missing file: {GP_GEO_CACHE_CSV}")
    gps = pd.read_csv(GP_GEO_CACHE_CSV, dtype=str)
    return points_to_gdf(gps)


def load_community_pharmacies() -> gpd.GeoDataFrame:
    if not PHARMACY_CSV.exists():
        raise FileNotFoundError(f"Missing file: {PHARMACY_CSV}")
    if not PHARMACY_GEO_CACHE_CSV.exists():
        raise FileNotFoundError(f"Missing file: {PHARMACY_GEO_CACHE_CSV}")

    pharmacy = pd.read_csv(PHARMACY_CSV, dtype=str)
    pharmacy.columns = [c.strip() for c in pharmacy.columns]
    pharmacy = pharmacy[pharmacy["CONTRACT_TYPE"].fillna("").str.contains("community", case=False, na=False)].copy()
    pharmacy = pharmacy[
        pharmacy["HEALTH_AND_WELLBEING_BOARD"].fillna("").str.contains(LONDON_HWB_PATTERN, case=False, na=False)
    ].copy()

    geocoded = pd.read_csv(PHARMACY_GEO_CACHE_CSV, dtype=str)
    geocoded.columns = [c.strip() for c in geocoded.columns]
    merged = pharmacy.merge(
        geocoded[["PHARMACY_ODS_CODE_F_CODE", "SiteName", "Latitude", "Longitude"]].drop_duplicates(
            "PHARMACY_ODS_CODE_F_CODE"
        ),
        on="PHARMACY_ODS_CODE_F_CODE",
        how="inner",
    )
    return points_to_gdf(merged)


def load_family_hubs() -> gpd.GeoDataFrame:
    if not FAMILY_HUB_CSV.exists():
        raise FileNotFoundError(f"Missing file: {FAMILY_HUB_CSV}")
    if not FAMILY_HUB_GEO_CACHE_CSV.exists():
        raise FileNotFoundError(f"Missing file: {FAMILY_HUB_GEO_CACHE_CSV}")

    hubs = pd.read_csv(FAMILY_HUB_CSV, dtype=str)
    hubs.columns = [c.strip() for c in hubs.columns]
    hubs = hubs[hubs["Region"].fillna("").str.contains("london", case=False, na=False)].copy()
    hubs["Postcode_normalized"] = hubs["Postcode"].map(normalize_postcode)

    geocoded = pd.read_csv(FAMILY_HUB_GEO_CACHE_CSV, dtype=str)
    geocoded.columns = [c.strip() for c in geocoded.columns]
    geocoded["Postcode_normalized"] = geocoded["Postcode"].map(normalize_postcode)
    merged = hubs.merge(
        geocoded[["Postcode_normalized", "Latitude", "Longitude"]].drop_duplicates("Postcode_normalized"),
        on="Postcode_normalized",
        how="inner",
    )
    return points_to_gdf(merged)


def load_nhs_trusts() -> gpd.GeoDataFrame:
    if not NHS_TRUSTS_XLSX.exists():
        raise FileNotFoundError(f"Missing file: {NHS_TRUSTS_XLSX}")

    trusts = pd.read_excel(NHS_TRUSTS_XLSX, dtype=str)
    trusts.columns = [c.strip() for c in trusts.columns]
    required = {"Trust Name", "Latitude", "Longitude", "Type"}
    missing = required.difference(trusts.columns)
    if missing:
        raise ValueError(f"Missing required columns in {NHS_TRUSTS_XLSX}: {sorted(missing)}")

    trusts["Type"] = trusts["Type"].fillna("").str.strip()
    trusts = trusts[trusts["Type"].str.contains("Acute|Specialist|Mental Health", case=False, na=False)].copy()

    def normalize_trust_type(value: str) -> str:
        lowered = value.lower()
        if "specialist" in lowered:
            return "Specialist Trust"
        if "acute" in lowered:
            return "Acute Trust"
        if "mental" in lowered:
            return "Mental Health Trust"
        return ""

    trusts["trust_type"] = trusts["Type"].map(normalize_trust_type)
    trusts = trusts[trusts["trust_type"] != ""].copy()
    return points_to_gdf(trusts)


def load_civic_centres() -> gpd.GeoDataFrame:
    if not CIVIC_CENTRES_CSV.exists():
        raise FileNotFoundError(f"Missing file: {CIVIC_CENTRES_CSV}")

    civic = pd.read_csv(CIVIC_CENTRES_CSV, dtype=str)
    civic.columns = [c.strip() for c in civic.columns]
    civic = civic.rename(columns={"latitude": "Latitude", "longitude": "Longitude", "type": "Type"})
    return points_to_gdf(civic)


def load_libraries() -> gpd.GeoDataFrame:
    if not LIBRARIES_CSV.exists():
        libraries = fetch_and_cache_libraries()
        return points_to_gdf(libraries)

    libraries = pd.read_csv(LIBRARIES_CSV, dtype=str)
    libraries.columns = [c.strip() for c in libraries.columns]
    libraries = libraries.rename(columns={"latitude": "Latitude", "longitude": "Longitude", "type": "Type"})
    return points_to_gdf(libraries)


def fetch_parks_and_gardens(
    target_boroughs: gpd.GeoDataFrame,
    envelope: tuple[float, float, float, float],
) -> gpd.GeoDataFrame:
    parks = arcgis_query_to_gdf(
        PARKS_GARDENS_FS_BASE,
        out_fields="ListEntry,Name,Grade,RegDate,AmendDate,hyperlink,area_ha",
        out_sr=4326,
        geometry=envelope,
    )
    if parks.empty:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    if parks.crs is None:
        parks = parks.set_crs("EPSG:4326")
    else:
        parks = parks.to_crs("EPSG:4326")

    target_union = target_boroughs.to_crs("EPSG:4326").union_all()
    return parks[parks.intersects(target_union)].copy()


def plot_parks_and_gardens_overlay(ax: plt.Axes, parks_3857: gpd.GeoDataFrame) -> None:
    if len(parks_3857) == 0:
        return
    parks_3857.plot(
        ax=ax,
        color=PARKS_GARDENS_FILL_COLOR,
        edgecolor="none",
        alpha=PARKS_GARDENS_FILL_ALPHA,
        zorder=2.6,
    )
    parks_3857.boundary.plot(
        ax=ax,
        linewidth=PARKS_GARDENS_LINE_WIDTH,
        color=PARKS_GARDENS_EDGE_COLOR,
        alpha=PARKS_GARDENS_EDGE_ALPHA,
        zorder=2.7,
    )


def build_parks_and_gardens_legend_handle() -> Patch:
    return Patch(
        facecolor=PARKS_GARDENS_FILL_COLOR,
        edgecolor=PARKS_GARDENS_EDGE_COLOR,
        linewidth=0.8,
        alpha=0.65,
        label=PARKS_GARDENS_LABEL,
    )


def filter_points_to_target(points: gpd.GeoDataFrame, target_boroughs: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if len(points) == 0:
        return points.copy()
    target_union = target_boroughs.union_all()
    return points[points.intersects(target_union)].copy()


def get_target_lsoa_codes(scope: str, icb_name: str | None = None) -> set[str]:
    if scope == "all_london":
        lsoa_boundaries, _, _ = fetch_london_lsoa_boundaries()
    else:
        if icb_name is None:
            raise ValueError("icb_name is required when scope is 'icb'.")
        lsoa_boundaries, _, _ = fetch_target_lsoa_boundaries(icb_name)
    return set(lsoa_boundaries["LSOA_code"].dropna().astype(str))


def fetch_and_cache_libraries() -> pd.DataFrame:
    response = requests.post(
        OVERPASS_URL,
        data={"data": LIBRARIES_OVERPASS_QUERY},
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()

    libraries: list[dict[str, object]] = []
    for element in data.get("elements", []):
        name = element.get("tags", {}).get("name", "Unnamed Library")
        if "lat" in element and "lon" in element:
            latitude = element["lat"]
            longitude = element["lon"]
        else:
            center = element.get("center", {})
            latitude = center.get("lat")
            longitude = center.get("lon")

        if latitude is None or longitude is None:
            continue

        libraries.append(
            {
                "name": name,
                "borough": "",
                "type": "Library",
                "latitude": latitude,
                "longitude": longitude,
            }
        )

    libraries_df = pd.DataFrame(libraries).drop_duplicates(subset=["name", "latitude", "longitude"])
    LIBRARIES_CSV.parent.mkdir(parents=True, exist_ok=True)
    libraries_df.to_csv(LIBRARIES_CSV, index=False)
    print(f"[info] Cached {len(libraries_df)} libraries to {LIBRARIES_CSV}")
    return libraries_df


def add_map_overlays(
    ax: plt.Axes,
    map_df_3857: gpd.GeoDataFrame,
    parks_and_gardens_3857: gpd.GeoDataFrame,
    wards_3857: gpd.GeoDataFrame,
    neighbourhoods_3857: gpd.GeoDataFrame,
    icb_outline_3857: gpd.GeoDataFrame,
    gps_3857: gpd.GeoDataFrame,
    pharmacies_3857: gpd.GeoDataFrame,
    family_hubs_3857: gpd.GeoDataFrame,
    trusts_3857: gpd.GeoDataFrame,
    civic_centres_3857: gpd.GeoDataFrame,
    libraries_3857: gpd.GeoDataFrame,
    title: str,
    output_path: Path,
    fig: plt.Figure,
) -> None:
    plot_parks_and_gardens_overlay(ax, parks_and_gardens_3857)

    wards_3857.boundary.plot(ax=ax, linewidth=0.25, color="#585858", alpha=0.55, zorder=3)
    neighbourhoods_3857.boundary.plot(
        ax=ax,
        linewidth=NEIGHBOURHOOD_LINE_HALO_WIDTH,
        color="white",
        alpha=0.65,
        zorder=3.8,
    )
    neighbourhoods_3857.boundary.plot(
        ax=ax,
        linewidth=NEIGHBOURHOOD_LINE_MAIN_WIDTH,
        color="#1A1A1A",
        alpha=0.9,
        zorder=4,
    )
    icb_outline_3857.boundary.plot(
        ax=ax,
        linewidth=2.0,
        color="white",
        alpha=0.6,
        zorder=5.8,
    )
    icb_outline_3857.boundary.plot(
        ax=ax,
        linewidth=ICB_OUTLINE_WIDTH,
        color=ICB_OUTLINE_COLOR,
        linestyle=(0, (6, 6)),
        alpha=0.9,
        zorder=6,
    )

    if len(libraries_3857) > 0:
        libraries_3857.plot(
            ax=ax,
            markersize=15,
            facecolor="none",
            edgecolor="#2B6F8A",
            linewidth=0.45,
            alpha=0.75,
            zorder=6.2,
            label="Library",
        )
    if len(civic_centres_3857) > 0:
        civic_centres_3857.plot(
            ax=ax,
            markersize=18,
            color="#5C677D",
            edgecolor="white",
            linewidth=0.3,
            alpha=0.72,
            zorder=6.9,
            label="Civic centre",
        )
    if len(gps_3857) > 0:
        gps_3857.plot(
            ax=ax,
            markersize=11,
            color="#D81B60",
            edgecolor="white",
            linewidth=0.25,
            alpha=0.95,
            zorder=7,
            label="GP practice",
        )
    if len(pharmacies_3857) > 0:
        pharmacies_3857.plot(
            ax=ax,
            markersize=9,
            color="#1F77B4",
            edgecolor="white",
            linewidth=0.25,
            alpha=0.9,
            zorder=7,
            label="Community pharmacy",
        )
    if len(family_hubs_3857) > 0:
        family_hubs_3857.plot(
            ax=ax,
            markersize=12,
            color="#2CA02C",
            edgecolor="white",
            linewidth=0.25,
            alpha=0.95,
            zorder=7,
            label="Family hub",
        )
    trust_styles = {
        "Acute Trust": {"color": "#243B53", "marker": "^", "size": 40},
        "Specialist Trust": {"color": "#B7791F", "marker": "D", "size": 34},
        "Mental Health Trust": {"color": "#6B46C1", "marker": "s", "size": 32},
    }
    for trust_type, style in trust_styles.items():
        subset = trusts_3857[trusts_3857["trust_type"] == trust_type]
        if len(subset) == 0:
            continue
        subset.plot(
            ax=ax,
            markersize=style["size"],
            color=style["color"],
            marker=style["marker"],
            edgecolor="white",
            linewidth=0.35,
            alpha=0.95,
            zorder=7.1,
            label=trust_type,
        )
    if (
        len(gps_3857) > 0
        or len(pharmacies_3857) > 0
        or len(family_hubs_3857) > 0
        or len(trusts_3857) > 0
        or len(civic_centres_3857) > 0
        or len(libraries_3857) > 0
        or len(parks_and_gardens_3857) > 0
    ):
        handles: list[Line2D | Patch] = []
        if len(parks_and_gardens_3857) > 0:
            handles.append(build_parks_and_gardens_legend_handle())
        if len(libraries_3857) > 0:
            handles.append(
                Line2D([0], [0], marker="o", color="none", markerfacecolor="none", markeredgecolor="#2B6F8A", markeredgewidth=0.8, markersize=6, label="Library")
            )
        if len(civic_centres_3857) > 0:
            handles.append(
                Line2D([0], [0], marker="o", color="none", markerfacecolor="#5C677D", markeredgecolor="white", markeredgewidth=0.5, markersize=7, label="Civic centre")
            )
        if len(gps_3857) > 0:
            handles.append(
                Line2D([0], [0], marker="o", color="none", markerfacecolor="#D81B60", markeredgecolor="white", markeredgewidth=0.4, markersize=6, label="GP practice")
            )
        if len(pharmacies_3857) > 0:
            handles.append(
                Line2D([0], [0], marker="o", color="none", markerfacecolor="#1F77B4", markeredgecolor="white", markeredgewidth=0.4, markersize=6, label="Community pharmacy")
            )
        if len(family_hubs_3857) > 0:
            handles.append(
                Line2D([0], [0], marker="o", color="none", markerfacecolor="#2CA02C", markeredgecolor="white", markeredgewidth=0.4, markersize=6, label="Family hub")
            )
        if len(trusts_3857[trusts_3857["trust_type"] == "Acute Trust"]) > 0:
            handles.append(
                Line2D([0], [0], marker="^", color="none", markerfacecolor="#243B53", markeredgecolor="white", markeredgewidth=0.5, markersize=7, label="Acute Trust")
            )
        if len(trusts_3857[trusts_3857["trust_type"] == "Specialist Trust"]) > 0:
            handles.append(
                Line2D([0], [0], marker="D", color="none", markerfacecolor="#B7791F", markeredgecolor="white", markeredgewidth=0.5, markersize=6.5, label="Specialist Trust")
            )
        if len(trusts_3857[trusts_3857["trust_type"] == "Mental Health Trust"]) > 0:
            handles.append(
                Line2D([0], [0], marker="s", color="none", markerfacecolor="#6B46C1", markeredgecolor="white", markeredgewidth=0.5, markersize=6.5, label="Mental Health Trust")
            )
        if handles:
            fig.legend(
                handles=handles,
                labels=[handle.get_label() for handle in handles],
                loc="lower center",
                bbox_to_anchor=(0.5, 0.03),
                ncol=3,
                fontsize=8,
                frameon=True,
                columnspacing=1.2,
                handletextpad=0.5,
            )

    minx, miny, maxx, maxy = map_df_3857.total_bounds
    pad_x = (maxx - minx) * 0.03
    pad_y = (maxy - miny) * 0.03
    ax.set_xlim(minx - pad_x, maxx + pad_x)
    ax.set_ylim(miny - pad_y, maxy + pad_y)

    ax.set_axis_off()
    ax.set_title(title, fontsize=14, pad=16)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.92, bottom=0.14)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=MAP_DPI, bbox_inches="tight")
    plt.close(fig)


def plot_priority_map(
    map_df_3857: gpd.GeoDataFrame,
    parks_and_gardens_3857: gpd.GeoDataFrame,
    wards_3857: gpd.GeoDataFrame,
    neighbourhoods_3857: gpd.GeoDataFrame,
    icb_outline_3857: gpd.GeoDataFrame,
    gps_3857: gpd.GeoDataFrame,
    pharmacies_3857: gpd.GeoDataFrame,
    family_hubs_3857: gpd.GeoDataFrame,
    trusts_3857: gpd.GeoDataFrame,
    civic_centres_3857: gpd.GeoDataFrame,
    libraries_3857: gpd.GeoDataFrame,
    score_column: str,
    legend_label: str,
    title: str,
    output_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=MAP_FIGSIZE)
    cax = inset_axes(ax, width="4%", height="30%", loc="lower right", borderpad=2)

    map_df_3857.plot(
        column=score_column,
        cmap="OrRd",
        linewidth=0.0,
        alpha=0.9,
        legend=True,
        legend_kwds={"cax": cax},
        missing_kwds={"color": "#eeeeee", "label": "Missing score"},
        ax=ax,
    )
    cax.tick_params(labelsize=8, length=0, pad=2)
    cax.yaxis.set_ticks_position("left")
    cax.set_ylabel(legend_label, fontsize=8)
    add_map_overlays(
        ax,
        map_df_3857,
        parks_and_gardens_3857,
        wards_3857,
        neighbourhoods_3857,
        icb_outline_3857,
        gps_3857,
        pharmacies_3857,
        family_hubs_3857,
        trusts_3857,
        civic_centres_3857,
        libraries_3857,
        title,
        output_path,
        fig,
    )


def plot_banded_metric_map(
    map_df_3857: gpd.GeoDataFrame,
    parks_and_gardens_3857: gpd.GeoDataFrame,
    wards_3857: gpd.GeoDataFrame,
    neighbourhoods_3857: gpd.GeoDataFrame,
    icb_outline_3857: gpd.GeoDataFrame,
    gps_3857: gpd.GeoDataFrame,
    pharmacies_3857: gpd.GeoDataFrame,
    family_hubs_3857: gpd.GeoDataFrame,
    trusts_3857: gpd.GeoDataFrame,
    civic_centres_3857: gpd.GeoDataFrame,
    libraries_3857: gpd.GeoDataFrame,
    metric_column: str,
    legend_title: str,
    title: str,
    output_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=MAP_FIGSIZE)
    plot_df = map_df_3857.copy()
    banded, labels = build_population_bands(plot_df[metric_column])
    plot_df["metric_band"] = banded
    cmap = plt.get_cmap("OrRd")
    colors = [cmap(value) for value in [0.30, 0.45, 0.60, 0.72, 0.84, 0.96][: len(labels)]]

    for label, color in zip(labels, colors):
        subset = plot_df[plot_df["metric_band"] == label]
        if len(subset) == 0:
            continue
        subset.plot(ax=ax, color=color, linewidth=0.0, alpha=0.9, zorder=2)

    missing = plot_df[plot_df["metric_band"].isna()]
    if len(missing) > 0:
        missing.plot(ax=ax, color="#eeeeee", linewidth=0.0, alpha=0.9, zorder=1)

    band_handles = [Patch(facecolor=color, edgecolor="none", label=label) for label, color in zip(labels, colors)]
    if len(missing) > 0:
        band_handles.append(Patch(facecolor="#eeeeee", edgecolor="none", label="Missing score"))
    band_legend = ax.legend(
        handles=band_handles,
        title=legend_title,
        loc="lower right",
        fontsize=8,
        title_fontsize=8,
        frameon=True,
    )
    ax.add_artist(band_legend)

    add_map_overlays(
        ax,
        map_df_3857,
        parks_and_gardens_3857,
        wards_3857,
        neighbourhoods_3857,
        icb_outline_3857,
        gps_3857,
        pharmacies_3857,
        family_hubs_3857,
        trusts_3857,
        civic_centres_3857,
        libraries_3857,
        title,
        output_path,
        fig,
    )


def create_maps(
    scored: pd.DataFrame,
    scope: str,
    icb_name: str | None,
    selected_maps: set[str],
    deprivation_output_path: Path,
    age_output_path: Path,
    age_density_output_path: Path,
    population_output_path: Path,
    weighted_output_path: Path,
) -> list[Path]:
    if scope == "all_london":
        lsoa, target_boroughs, envelope = fetch_london_lsoa_boundaries()
        wards = fetch_london_wards(target_boroughs, envelope)
        neighbourhoods = load_neighbourhoods()
        icb_outline = build_icb_outline(target_boroughs)
        gps = load_gp_practices()
        pharmacies = load_community_pharmacies()
        family_hubs = load_family_hubs()
        trusts = load_nhs_trusts()
        try:
            civic_centres = load_civic_centres()
        except FileNotFoundError:
            civic_centres = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        try:
            libraries = load_libraries()
        except FileNotFoundError:
            libraries = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    else:
        if icb_name is None:
            raise ValueError("icb_name is required when scope is 'icb'.")
        lsoa, target_boroughs, envelope = fetch_target_lsoa_boundaries(icb_name)
        wards = fetch_target_wards(target_boroughs, envelope)
        neighbourhoods = load_neighbourhoods(icb_name)
        icb_outline = build_icb_outline(target_boroughs)
        gps = filter_points_to_target(load_gp_practices(), target_boroughs)
        pharmacies = filter_points_to_target(load_community_pharmacies(), target_boroughs)
        family_hubs = filter_points_to_target(load_family_hubs(), target_boroughs)
        trusts = filter_points_to_target(load_nhs_trusts(), target_boroughs)
        try:
            civic_centres = filter_points_to_target(load_civic_centres(), target_boroughs)
        except FileNotFoundError:
            civic_centres = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        try:
            libraries = filter_points_to_target(load_libraries(), target_boroughs)
        except FileNotFoundError:
            libraries = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    try:
        parks_and_gardens = fetch_parks_and_gardens(target_boroughs, envelope)
    except Exception as exc:
        print(f"[warn] Could not load Historic England Parks and Gardens layer: {exc}")
        parks_and_gardens = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    map_df = lsoa.merge(scored, on="LSOA_code", how="left", validate="1:1")
    scope_label = get_scope_label(scope, icb_name)
    map_df_3857 = add_older_people_density_columns(map_df.to_crs(3857))
    parks_and_gardens_3857 = parks_and_gardens.to_crs(3857)
    wards_3857 = wards.to_crs(3857)
    neighbourhoods_3857 = neighbourhoods.to_crs(3857)
    icb_outline_3857 = icb_outline.to_crs(3857)
    gps_3857 = gps.to_crs(3857)
    pharmacies_3857 = pharmacies.to_crs(3857)
    family_hubs_3857 = family_hubs.to_crs(3857)
    trusts_3857 = trusts.to_crs(3857)
    civic_centres_3857 = civic_centres.to_crs(3857)
    libraries_3857 = libraries.to_crs(3857)
    created_paths: list[Path] = []
    if "deprivation" in selected_maps:
        log_step(f"Rendering deprivation map -> {deprivation_output_path.name}")
        plot_priority_map(
            map_df_3857,
            parks_and_gardens_3857,
            wards_3857,
            neighbourhoods_3857,
            icb_outline_3857,
            gps_3857,
            pharmacies_3857,
            family_hubs_3857,
            trusts_3857,
            civic_centres_3857,
            libraries_3857,
            "deprivation_score_pct",
            "Deprivation score",
            f"{scope_label} deprivation score by LSOA\nComponent view used in the final weighted priority map",
            deprivation_output_path,
        )
        created_paths.append(deprivation_output_path)
    if "age" in selected_maps:
        log_step(f"Rendering 65+ proportion map -> {age_output_path.name}")
        plot_priority_map(
            map_df_3857,
            parks_and_gardens_3857,
            wards_3857,
            neighbourhoods_3857,
            icb_outline_3857,
            gps_3857,
            pharmacies_3857,
            family_hubs_3857,
            trusts_3857,
            civic_centres_3857,
            libraries_3857,
            "older_people_score_pct",
            "Age 65+ score",
            f"{scope_label} 65+ proportion score by LSOA\nComponent view used in the final weighted priority map",
            age_output_path,
        )
        created_paths.append(age_output_path)
    if "age_density" in selected_maps:
        log_step(f"Rendering 65+ density map -> {age_density_output_path.name}")
        plot_banded_metric_map(
            map_df_3857,
            parks_and_gardens_3857,
            wards_3857,
            neighbourhoods_3857,
            icb_outline_3857,
            gps_3857,
            pharmacies_3857,
            family_hubs_3857,
            trusts_3857,
            civic_centres_3857,
            libraries_3857,
            "older_people_density_per_sq_km",
            "65+ people per sq km",
            f"{scope_label} age 65+ density by LSOA\nOlder residents per square kilometre using LSOA polygon area",
            age_density_output_path,
        )
        created_paths.append(age_density_output_path)
    if "population" in selected_maps:
        log_step(f"Rendering population density map -> {population_output_path.name}")
        plot_banded_metric_map(
            map_df_3857,
            parks_and_gardens_3857,
            wards_3857,
            neighbourhoods_3857,
            icb_outline_3857,
            gps_3857,
            pharmacies_3857,
            family_hubs_3857,
            trusts_3857,
            civic_centres_3857,
            libraries_3857,
            "population_density_per_sq_km",
            "People per sq km",
            f"{scope_label} population density by LSOA\nPeople per square kilometre using LSOA polygon area",
            population_output_path,
        )
        created_paths.append(population_output_path)
    if "weighted" in selected_maps:
        log_step(f"Rendering weighted priority map -> {weighted_output_path.name}")
        plot_priority_map(
            map_df_3857,
            parks_and_gardens_3857,
            wards_3857,
            neighbourhoods_3857,
            icb_outline_3857,
            gps_3857,
            pharmacies_3857,
            family_hubs_3857,
            trusts_3857,
            civic_centres_3857,
            libraries_3857,
            "weighted_priority_score_pct",
            "Weighted priority score",
            f"{scope_label} weighted priority score by LSOA\n"
            "Split by neighbourhoods: Deprivation 50, Age 65+ proportion 30, Overall population 20",
            weighted_output_path,
        )
        created_paths.append(weighted_output_path)
    return created_paths


def main() -> None:
    args = parse_args()

    scope = args.scope
    icb_name = args.icb if scope == "icb" else None
    selected_maps = set(args.map or DEFAULT_MAP_SELECTION)
    default_outputs = get_default_output_paths(scope, icb_name)
    deprivation_csv = args.deprivation_csv
    population_csv = args.population_csv
    older_people_csv = args.older_people_csv
    output_csv = args.output_csv if args.output_csv != DEFAULT_OUTPUT_CSV else default_outputs["output_csv"]
    deprivation_map_png = (
        args.deprivation_map_png
        if args.deprivation_map_png != DEFAULT_DEPRIVATION_MAP_PNG
        else default_outputs["deprivation_map_png"]
    )
    age_map_png = args.age_map_png if args.age_map_png != DEFAULT_AGE_MAP_PNG else default_outputs["age_map_png"]
    age_density_map_png = (
        args.age_density_map_png
        if args.age_density_map_png != DEFAULT_AGE_DENSITY_MAP_PNG
        else default_outputs["age_density_map_png"]
    )
    population_map_png = (
        args.population_map_png
        if args.population_map_png != DEFAULT_POPULATION_MAP_PNG
        else default_outputs["population_map_png"]
    )
    map_png = args.map_png if args.map_png != DEFAULT_MAP_PNG else default_outputs["map_png"]
    scope_label = get_scope_label(scope, icb_name)

    log_step(f"Starting weighted priority build for {scope_label}")
    print(f"  Scope mode: {scope}")
    if scope == "icb":
        print(f"  ICB filter: {icb_name}")
    print(f"  Output CSV: {output_csv}")
    if args.no_map:
        print("  Maps: skipped (--no-map)")
    else:
        print(f"  Selected maps: {', '.join(sorted(selected_maps))}")

    if not deprivation_csv.exists():
        raise FileNotFoundError(f"Missing file: {deprivation_csv}")
    if not population_csv.exists():
        raise FileNotFoundError(f"Missing file: {population_csv}")
    if not older_people_csv.exists():
        raise FileNotFoundError(f"Missing file: {older_people_csv}")

    log_step("Loading source datasets")
    deprivation = load_deprivation_data(deprivation_csv)
    population = load_population_data(population_csv)
    older_people = load_65plus_data(older_people_csv)
    print(f"  Deprivation rows: {len(deprivation):,}")
    print(f"  Population rows: {len(population):,}")
    print(f"  65+ rows: {len(older_people):,}")

    log_step(f"Filtering LSOAs for {scope_label}")
    target_lsoa_codes = get_target_lsoa_codes(scope, icb_name)
    print(f"  Target LSOAs: {len(target_lsoa_codes):,}")

    log_step("Merging source tables")
    merged = deprivation.merge(population, on="LSOA_code", how="left", validate="1:1")
    merged = merged.merge(older_people, on="LSOA_code", how="left", validate="1:1")
    merged = merged[merged["LSOA_code"].isin(target_lsoa_codes)].copy()
    print(f"  Rows after merge and scope filter: {len(merged):,}")
    print(f"  Missing population values: {merged['population'].isna().sum():,}")
    print(f"  Missing 65+ values: {merged['population_65_plus'].isna().sum():,}")

    log_step("Calculating component scores")
    merged = add_component_scores(merged)
    print_scoring_audit(merged)

    log_step("Finalising ranked output")
    scored = finalise_output(merged)
    scored.insert(0, "scope", scope)
    scored.insert(1, "scope_name", scope_label)
    print(f"  Rows retained after dropping incomplete scores: {len(scored):,}")

    log_step(f"Writing scored CSV -> {output_csv.name}")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(output_csv, index=False)

    if not args.no_map:
        log_step("Generating requested maps")
        created_maps = create_maps(
            scored,
            scope,
            icb_name,
            selected_maps,
            deprivation_map_png,
            age_map_png,
            age_density_map_png,
            population_map_png,
            map_png,
        )

    print(f"Created: {output_csv}")
    if not args.no_map:
        for created_map in created_maps:
            print(f"Created: {created_map}")
    print(f"Scope: {scope_label}")
    print(f"Rows scored: {len(scored)}")
    print("Weights used:")
    print(f"  Deprivation: {DEPRIVATION_WEIGHT}")
    print(f"  65+ proportion: {OLDER_PEOPLE_WEIGHT}")
    print(f"  Overall population: {POPULATION_WEIGHT}")
    print()
    print("Top 10 LSOAs by weighted priority:")
    print(
        scored.loc[
            :9,
            ["priority_rank", "LSOA_code", "weighted_priority_score_pct", "IMD_decile", "older_people_proportion", "population"],
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()

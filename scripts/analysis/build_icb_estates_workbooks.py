from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

import geopandas as gpd
import pandas as pd

from scripts.analysis.build_icb_asset_workbooks import build_family_hub_dataset, build_pharmacy_dataset
from scripts.analysis.build_weighted_priority_map import (
    ICB_BOROUGHS_BY_LAD,
    ICB_SHORT_NAMES,
    load_civic_centres,
    load_gp_practices,
    load_libraries,
    load_neighbourhoods,
    load_nhs_trusts,
    slugify_scope_label,
)
from project_paths import OUTPUT_DIR


OUTPUT_SUBDIR = OUTPUT_DIR / "icb_estates_mapping_workbooks"
NEIGHBOURHOOD_ASSET_DENSITY_CSV = OUTPUT_DIR / "neighbourhood_asset_density.csv"

ICB_CODES = {
    "NHS North Central London ICB": "NCL",
    "NHS North East London ICB": "NEL",
    "NHS North West London ICB": "NWL",
    "NHS South East London ICB": "SEL",
    "NHS South West London ICB": "SWL",
}

ICB_NAMES_BY_CODE = {code: icb for icb, code in ICB_CODES.items()}
BOROUGH_TO_ICB_CODE = {
    borough: ICB_CODES[icb]
    for icb, boroughs in ICB_BOROUGHS_BY_LAD.items()
    for borough in boroughs
}

BOROUGH_ALIASES = {
    "barking & dagenham": "Barking and Dagenham",
    "barking and dagenham": "Barking and Dagenham",
    "hammersmith & fulham": "Hammersmith and Fulham",
    "hammersmith and fulham": "Hammersmith and Fulham",
    "kingston": "Kingston upon Thames",
    "kingston upon thames": "Kingston upon Thames",
    "richmond": "Richmond upon Thames",
    "richmond upon thames": "Richmond upon Thames",
}


def normalize_borough(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    return BOROUGH_ALIASES.get(text.lower(), text)


def reorder_columns(df: pd.DataFrame, first_columns: list[str]) -> pd.DataFrame:
    first = [column for column in first_columns if column in df.columns]
    rest = [column for column in df.columns if column not in first]
    return df.loc[:, first + rest]


def clean_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    for column in output.columns:
        if pd.api.types.is_object_dtype(output[column]):
            output[column] = output[column].where(output[column].notna(), "")
    return output


def assign_spatial_context(
    points: gpd.GeoDataFrame,
    neighbourhoods: gpd.GeoDataFrame,
    source_borough_column: str | None = None,
) -> pd.DataFrame:
    if points.empty:
        return pd.DataFrame(points.drop(columns="geometry", errors="ignore"))

    points_wgs84 = points.to_crs("EPSG:4326").copy().reset_index(drop=True)
    points_wgs84["__asset_id"] = range(len(points_wgs84))

    neighbourhood_context = neighbourhoods.to_crs("EPSG:4326").loc[
        :, ["nghbrhd", "borough", "ICB", "geometry"]
    ]
    joined = gpd.sjoin(
        points_wgs84.loc[:, ["__asset_id", "geometry"]],
        neighbourhood_context,
        how="left",
        predicate="within",
    )

    joined["__has_context"] = joined["ICB"].notna()
    context = (
        joined.sort_values(["__asset_id", "__has_context"], ascending=[True, False])
        .drop_duplicates("__asset_id")
        .set_index("__asset_id")
        .loc[:, ["nghbrhd", "borough", "ICB"]]
        .rename(
            columns={
                "nghbrhd": "Neighbourhood",
                "borough": "Spatial Borough",
                "ICB": "ICB code",
            }
        )
    )

    attributes = pd.DataFrame(points_wgs84.drop(columns="geometry")).set_index("__asset_id")
    output = attributes.join(context, how="left").reset_index(drop=True)

    if source_borough_column and source_borough_column in output.columns:
        normalized_borough = output[source_borough_column].map(normalize_borough)
        fallback_icb = normalized_borough.map(BOROUGH_TO_ICB_CODE)
        output["Spatial Borough"] = output["Spatial Borough"].fillna(normalized_borough)
        output["ICB code"] = output["ICB code"].fillna(fallback_icb)

    output["ICB"] = output["ICB code"].map(ICB_NAMES_BY_CODE)
    output["ICB display name"] = output["ICB"].map(ICB_SHORT_NAMES)
    return reorder_columns(
        output,
        ["ICB", "ICB display name", "ICB code", "Spatial Borough", "Neighbourhood"],
    )


def add_icb_metadata(df: pd.DataFrame, icb_name: str) -> pd.DataFrame:
    output = df.copy()
    output["ICB code"] = ICB_CODES[icb_name]
    output["ICB display name"] = ICB_SHORT_NAMES[icb_name]
    return reorder_columns(output, ["ICB", "ICB display name", "ICB code", "Borough"])


def build_point_asset_tables(neighbourhoods: gpd.GeoDataFrame) -> dict[str, pd.DataFrame]:
    loaders: dict[str, tuple[Callable[[], gpd.GeoDataFrame], str | None, list[str]]] = {
        "GP practices": (
            load_gp_practices,
            "Borough",
            ["ICB display name", "Spatial Borough", "Neighbourhood", "Practice Name", "Practice Code"],
        ),
        "NHS trusts": (
            load_nhs_trusts,
            None,
            ["ICB display name", "Spatial Borough", "Neighbourhood", "Trust Name", "Type", "trust_type"],
        ),
        "Civic centres": (
            load_civic_centres,
            "borough",
            ["ICB display name", "Spatial Borough", "Neighbourhood", "name", "Type"],
        ),
        "Libraries": (
            load_libraries,
            "borough",
            ["ICB display name", "Spatial Borough", "Neighbourhood", "name", "Type"],
        ),
    }

    tables: dict[str, pd.DataFrame] = {}
    for sheet_name, (loader, source_borough_column, sort_columns) in loaders.items():
        table = assign_spatial_context(loader(), neighbourhoods, source_borough_column)
        existing_sort_columns = [column for column in sort_columns if column in table.columns]
        if existing_sort_columns:
            table = table.sort_values(existing_sort_columns, na_position="last")
        tables[sheet_name] = table
    return tables


def load_neighbourhood_summary() -> pd.DataFrame:
    if not NEIGHBOURHOOD_ASSET_DENSITY_CSV.exists():
        return pd.DataFrame()
    summary = pd.read_csv(NEIGHBOURHOOD_ASSET_DENSITY_CSV, dtype=str)
    if "ICB" not in summary.columns:
        return pd.DataFrame()
    return summary


def build_summary_sheet(icb_name: str, sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = [
        {"Item": "ICB", "Value": icb_name},
        {"Item": "ICB display name", "Value": ICB_SHORT_NAMES[icb_name]},
        {"Item": "ICB code", "Value": ICB_CODES[icb_name]},
        {"Item": "Generated at", "Value": datetime.now().strftime("%Y-%m-%d %H:%M")},
        {"Item": "Output folder", "Value": str(OUTPUT_SUBDIR)},
        {"Item": "Notes", "Value": "One tab per Estates mapping dataset in the current local workspace."},
    ]
    rows.extend({"Item": f"{sheet_name} rows", "Value": str(len(df))} for sheet_name, df in sheets.items())
    return pd.DataFrame(rows)


def autosize_worksheet(writer: pd.ExcelWriter, sheet_name: str, df: pd.DataFrame) -> None:
    worksheet = writer.sheets[sheet_name]
    worksheet.freeze_panes = "A2"
    if len(df.columns) > 0:
        worksheet.auto_filter.ref = worksheet.dimensions

    for column_cells in worksheet.columns:
        header = str(column_cells[0].value or "")
        max_length = len(header)
        for cell in column_cells[1:1000]:
            if cell.value is not None:
                max_length = max(max_length, len(str(cell.value)))
        width = min(max(max_length + 2, 10), 45)
        worksheet.column_dimensions[column_cells[0].column_letter].width = width


def write_workbook(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            safe_name = sheet_name[:31]
            ready = clean_for_excel(df)
            ready.to_excel(writer, sheet_name=safe_name, index=False)
            autosize_worksheet(writer, safe_name, ready)


def build_workbooks() -> list[Path]:
    neighbourhoods = load_neighbourhoods()
    point_asset_tables = build_point_asset_tables(neighbourhoods)
    pharmacy_tables = build_pharmacy_dataset()
    family_hub_tables = build_family_hub_dataset()
    neighbourhood_summary = load_neighbourhood_summary()

    created_paths: list[Path] = []
    for icb_name in ICB_BOROUGHS_BY_LAD:
        icb_code = ICB_CODES[icb_name]
        sheets: dict[str, pd.DataFrame] = {
            "GP practices": point_asset_tables["GP practices"].query("`ICB code` == @icb_code").copy(),
            "Community pharmacies": add_icb_metadata(pharmacy_tables[icb_name], icb_name),
            "Family hubs": add_icb_metadata(family_hub_tables[icb_name], icb_name),
            "NHS trusts": point_asset_tables["NHS trusts"].query("`ICB code` == @icb_code").copy(),
            "Civic centres": point_asset_tables["Civic centres"].query("`ICB code` == @icb_code").copy(),
            "Libraries": point_asset_tables["Libraries"].query("`ICB code` == @icb_code").copy(),
        }

        if not neighbourhood_summary.empty:
            summary = neighbourhood_summary[neighbourhood_summary["ICB"].eq(icb_code)].copy()
            if "service_desert_rank" in summary.columns:
                summary["service_desert_rank_sort"] = pd.to_numeric(
                    summary["service_desert_rank"],
                    errors="coerce",
                )
                summary = summary.sort_values("service_desert_rank_sort").drop(
                    columns="service_desert_rank_sort"
                )
            sheets["Neighbourhood summary"] = summary

        ordered_sheets = {"Summary": build_summary_sheet(icb_name, sheets)}
        ordered_sheets.update(sheets)

        filename = f"{slugify_scope_label(ICB_SHORT_NAMES[icb_name])}_estates_mapping_data.xlsx"
        path = OUTPUT_SUBDIR / filename
        write_workbook(path, ordered_sheets)
        created_paths.append(path)

    return created_paths


def main() -> None:
    created_paths = build_workbooks()
    print("Created per-ICB Estates mapping workbooks:")
    for path in created_paths:
        print(path)


if __name__ == "__main__":
    main()

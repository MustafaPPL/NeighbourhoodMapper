
"""
South East London: 65+ population density with assets overlay

What it does
- Downloads borough boundaries (LAD Dec 2023) and filters to SEL ICB
- Downloads LSOA Dec 2021 boundaries, clipped to SEL
- Loads latest ONS LSOA population estimates and extracts 65+ population
- Calculates 65+ population density (people per km^2) and plots choropleth
- Overlays borough/ICB outlines and assets
"""

from __future__ import annotations

import io
import sys
import time
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
import requests

# Optional basemap
try:
    import contextily as ctx
    HAS_CTX = True
except Exception:
    HAS_CTX = False

# -----------------------------
# CONFIG
# -----------------------------

LAD_FS_BASE = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Local_Authority_Districts_December_2023_Boundaries_UK_BGC/FeatureServer/0"
)
LSOA_FS_BASE = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V5/FeatureServer/0"
)
ONS_LSOA_POP_XLSX_URL = (
    "https://www.ons.gov.uk/file?uri=/peoplepopulationandcommunity/"
    "populationandmigration/populationestimates/datasets/"
    "lowersuperoutputareamidyearpopulationestimatesnationalstatistics/"
    "mid2022revisednov2025tomid2024/sapelsoabroadage20222024.xlsx"
)

OUTPUT_PNG = "sel_65plus_density.png"
FIGSIZE = (12, 12)
DPI = 200

SCOPE_ICB = "NHS South East London ICB"
AGE_BAND = "65+"

ASSETS_CSV = "assets.csv"
PLOT_ASSETS = True
ASSET_POINT_SIZE = 18
ASSET_POINT_COLOR = "#111111"
ASSET_CATEGORY_COLOR_MAP = {
    "Primary Care": "#1A5CBA",
    "Acute Hospital": "#89CFF0",
    "Community Health": "#2A9D6F",
    "Mental Health": "#8B5CF6",
    "Specialist Hospital": "#E8A020",
    "Void": "#AAAAAA",
}
ASSET_CATEGORY_ORDER = [
    "Primary Care",
    "Acute Hospital",
    "Community Health",
    "Mental Health",
    "Specialist Hospital",
    "Void",
]

DENSITY_CMAP = LinearSegmentedColormap.from_list(
    "65plusDensityWarm",
    ["#fff7ec", "#fee8c8", "#fdd49e", "#fdbb84", "#fd8d3c", "#fb6a4a", "#ef3b2c"],
)
DENSITY_ALPHA = 0.85

ICB_OUTLINE_COLOR = "#2B2B2B"
ICB_OUTLINE_WIDTH = 1.6
ICB_OUTLINE_STYLE = "--"

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

ICB_BOROUGHS_BY_LAD = {
    "NHS North Central London ICB": {
        "Barnet",
        "Camden",
        "Enfield",
        "Haringey",
        "Islington",
    },
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
    "NHS South East London ICB": {
        "Bexley",
        "Bromley",
        "Greenwich",
        "Lambeth",
        "Lewisham",
        "Southwark",
    },
    "NHS South West London ICB": {
        "Croydon",
        "Kingston upon Thames",
        "Merton",
        "Richmond upon Thames",
        "Sutton",
        "Wandsworth",
    },
}

REQUEST_TIMEOUT = 60
USER_AGENT = "SEL-65plus-mapper/1.0 (+python requests)"


def _request_json(url: str, params: Dict, max_retries: int = 5) -> Dict:
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == max_retries:
                raise
            sleep_s = min(2 ** attempt, 20)
            print(f"[warn] Request failed (attempt {attempt}/{max_retries}): {e} -> sleeping {sleep_s}s")
            time.sleep(sleep_s)
    raise RuntimeError("unreachable")


def arcgis_query_to_gdf(
    layer_base_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    out_sr: int = 4326,
    geometry: Optional[Tuple[float, float, float, float]] = None,
    geometry_type: str = "esriGeometryEnvelope",
    spatial_rel: str = "esriSpatialRelIntersects",
    page_size: int = 2000,
) -> gpd.GeoDataFrame:
    query_url = f"{layer_base_url}/query"

    count_params = {
        "where": where,
        "returnCountOnly": "true",
        "f": "json",
    }
    if geometry is not None:
        xmin, ymin, xmax, ymax = geometry
        count_params.update({
            "geometry": f"{xmin},{ymin},{xmax},{ymax}",
            "geometryType": geometry_type,
            "inSR": out_sr,
            "spatialRel": spatial_rel,
        })

    count_json = _request_json(query_url, count_params)
    total = int(count_json.get("count", 0))
    print(f"[info] {layer_base_url.split('/')[-1]}: total features to fetch = {total}")

    all_parts: List[gpd.GeoDataFrame] = []
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
            params.update({
                "geometry": f"{xmin},{ymin},{xmax},{ymax}",
                "geometryType": geometry_type,
                "inSR": out_sr,
                "spatialRel": spatial_rel,
            })

        headers = {"User-Agent": USER_AGENT}
        r = requests.get(query_url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()

        part = gpd.read_file(io.BytesIO(r.content))
        if len(part) == 0:
            print(f"[warn] Received 0 features at offset {fetched}. Stopping early.")
            break

        all_parts.append(part)
        fetched += len(part)
        print(f"[info] fetched {fetched}/{total}")

    if not all_parts:
        return gpd.GeoDataFrame(geometry=[], crs=f"EPSG:{out_sr}")

    gdf = pd.concat(all_parts, ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=f"EPSG:{out_sr}")
    return gdf


def find_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols:
            return cols[cand.lower()]
    return None


def find_lsoa_code_col(df: pd.DataFrame) -> str:
    preferred = ["LSOA21CD", "LSOA11CD", "lsoa_code", "LSOA code (2011)", "LSOA code (2021)", "LSOA 2021 Code"]
    col = find_col(df, preferred)
    if col:
        return col
    for c in df.columns:
        cl = c.lower()
        if "lsoa" in cl and (cl.endswith("cd") or "code" in cl):
            return c
    raise ValueError("Could not identify an LSOA code column.")


def load_latest_lsoa_population_65plus(xlsx_url: str) -> pd.DataFrame:
    print("[info] Downloading ONS LSOA population estimates...")
    r = requests.get(xlsx_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    xls = pd.ExcelFile(io.BytesIO(r.content))

    mid_sheets = []
    for sheet in xls.sheet_names:
        if sheet.lower().startswith("mid-") and "lsoa 2021" in sheet.lower():
            try:
                year = int(sheet.split()[0].replace("Mid-", ""))
            except Exception:
                year = None
            if year:
                mid_sheets.append((year, sheet))
    if not mid_sheets:
        raise ValueError("Could not find a 'Mid-YYYY LSOA 2021' sheet in the ONS workbook.")

    mid_sheets.sort()
    _, latest_sheet = mid_sheets[-1]
    df = pd.read_excel(xls, sheet_name=latest_sheet, header=3)

    lsoa_col = find_lsoa_code_col(df)
    if not lsoa_col:
        raise ValueError(f"Could not find LSOA code column in sheet '{latest_sheet}'.")

    f_col = "F65 and over"
    m_col = "M65 and over"
    if f_col not in df.columns or m_col not in df.columns:
        raise ValueError(f"Expected columns '{f_col}' and '{m_col}' not found.")

    out = df[[lsoa_col, f_col, m_col]].copy()
    out["population"] = pd.to_numeric(out[f_col], errors="coerce") + pd.to_numeric(out[m_col], errors="coerce")
    out = out.dropna(subset=["population"])
    print(f"[info] Using sheet '{latest_sheet}' and 65+ population.")
    return out[[lsoa_col, "population"]]


def load_assets_points(
    csv_path: str,
    bounds: Optional[Tuple[float, float, float, float]] = None,
) -> gpd.GeoDataFrame:
    assets = pd.read_csv(csv_path, dtype=str)
    assets.columns = [c.strip() for c in assets.columns]

    lat_col = find_col(assets, ["Latitude", "Lat", "latitude", "LAT"])
    lon_col = find_col(assets, ["Longitude", "Long", "Lon", "longitude", "LONG"])
    category_col = find_col(assets, ["Category", "Asset Category", "Type"])
    if not lat_col or not lon_col:
        raise ValueError("Could not find Latitude/Longitude columns in assets.csv")

    lat = pd.to_numeric(assets[lat_col], errors="coerce")
    lon = pd.to_numeric(
        assets[lon_col].astype(str).str.replace("–", "-", regex=False),
        errors="coerce",
    )

    valid = lat.notna() & lon.notna()
    assets = assets.loc[valid].copy()
    assets["__lat"] = lat[valid]
    assets["__lon"] = lon[valid]

    if bounds is not None:
        xmin, ymin, xmax, ymax = bounds
        in_bounds = (
            (assets["__lon"] >= xmin)
            & (assets["__lon"] <= xmax)
            & (assets["__lat"] >= ymin)
            & (assets["__lat"] <= ymax)
        )
        assets = assets.loc[in_bounds].copy()

    assets_gdf = gpd.GeoDataFrame(
        assets,
        geometry=gpd.points_from_xy(assets["__lon"], assets["__lat"]),
        crs="EPSG:4326",
    )
    if category_col:
        raw = assets_gdf[category_col].astype(str).str.strip()

        def _map_category(value: str) -> str:
            v = value.lower()
            if "primary" in v:
                return "Primary Care"
            if "specialist" in v:
                return "Specialist Hospital"
            if "acute" in v:
                return "Acute Hospital"
            if "mental" in v:
                return "Mental Health"
            if "community" in v:
                return "Community Health"
            if v == "" or v == "nan":
                return "Void"
            return "Void"

        assets_gdf["__category"] = raw.map(_map_category)
    else:
        assets_gdf["__category"] = "Void"
    return assets_gdf


def main() -> None:
    print("[info] Downloading LAD boundaries (UK) and filtering to Greater London...")
    lad = arcgis_query_to_gdf(LAD_FS_BASE, out_sr=4326)

    lad_name_col = None
    for cand in ["LAD23NM", "LAD24NM", "LAD22NM", "LADNM", "NAME"]:
        if cand in lad.columns:
            lad_name_col = cand
            break
    if lad_name_col is None:
        raise ValueError(f"Could not find LAD name column. Available columns: {list(lad.columns)}")

    icb_map = {
        borough: icb
        for icb, boroughs in ICB_BOROUGHS_BY_LAD.items()
        for borough in boroughs
    }
    london_boroughs = lad[lad[lad_name_col].isin(LONDON_BOROUGHS_AND_CITY)].copy()
    if len(london_boroughs) == 0:
        raise ValueError("No London boroughs matched. Check LAD name field / spelling.")
    london_boroughs["__icb"] = london_boroughs[lad_name_col].map(icb_map)

    if SCOPE_ICB:
        london_boroughs = london_boroughs[london_boroughs["__icb"] == SCOPE_ICB].copy()
        if len(london_boroughs) == 0:
            raise ValueError(f"No boroughs matched scope ICB: {SCOPE_ICB}")

    xmin, ymin, xmax, ymax = london_boroughs.total_bounds
    pad = 0.05
    env = (xmin - pad, ymin - pad, xmax + pad, ymax + pad)
    print(f"[info] London envelope (EPSG:4326) = {env}")

    print("[info] Downloading LSOA boundaries clipped to London envelope...")
    lsoa = arcgis_query_to_gdf(LSOA_FS_BASE, out_sr=4326, geometry=env)

    print("[info] Clipping LSOAs to borough boundary...")
    london_union = london_boroughs.to_crs(4326).unary_union
    lsoa = lsoa[lsoa.intersects(london_union)].copy()

    lsoa_code_col = None
    for cand in ["LSOA21CD", "LSOA11CD", "LSOA_CODE", "CODE", "LSOA21CD "]:
        if cand in lsoa.columns:
            lsoa_code_col = cand
            break
    if lsoa_code_col is None:
        for c in lsoa.columns:
            if "lsoa" in c.lower() and c.lower().endswith("cd"):
                lsoa_code_col = c
                break
    if lsoa_code_col is None:
        raise ValueError(f"Could not find LSOA code column in boundaries. Columns: {list(lsoa.columns)}")

    pop = load_latest_lsoa_population_65plus(ONS_LSOA_POP_XLSX_URL)
    pop_lsoa_col = find_lsoa_code_col(pop)

    lsoa = lsoa.merge(
        pop,
        left_on=lsoa_code_col,
        right_on=pop_lsoa_col,
        how="left",
        validate="m:1",
    )

    lsoa_27700 = lsoa.to_crs(27700)
    area_km2 = lsoa_27700.geometry.area / 1_000_000.0
    lsoa["__density_65plus"] = lsoa["population"] / area_km2

    lsoa_3857 = lsoa.to_crs(3857)
    bor_3857 = london_boroughs.to_crs(3857)

    assets_3857 = None
    if PLOT_ASSETS:
        try:
            assets_3857 = load_assets_points(ASSETS_CSV, bounds=(xmin, ymin, xmax, ymax)).to_crs(3857)
            print(f"[info] Loaded {len(assets_3857)} assets with valid coordinates.")
        except Exception as e:
            print(f"[warn] Assets layer skipped: {e}")

    print("[info] Plotting 65+ density...")
    fig, ax = plt.subplots(1, 1, figsize=FIGSIZE)
    cax = inset_axes(
        ax,
        width="5%",
        height="30%",
        loc="lower right",
        borderpad=2,
    )

    lsoa_3857.plot(
        ax=ax,
        column="__density_65plus",
        legend=True,
        cmap=DENSITY_CMAP,
        alpha=DENSITY_ALPHA,
        linewidth=0.0,
        missing_kwds={"color": "lightgrey", "label": "Missing"},
        legend_kwds={"cax": cax},
    )
    cax.tick_params(labelsize=7, length=0, pad=2)
    cax.yaxis.set_ticks_position("left")
    cax.set_ylabel("65+ density\n(people per km²)", fontsize=7)

    bor_3857.boundary.plot(ax=ax, linewidth=1.0)

    icb_outline = london_boroughs.dropna(subset=["__icb"]).dissolve(by="__icb").to_crs(3857)
    icb_outline.boundary.plot(
        ax=ax,
        linewidth=ICB_OUTLINE_WIDTH,
        linestyle=ICB_OUTLINE_STYLE,
        color=ICB_OUTLINE_COLOR,
        alpha=0.8,
        zorder=4,
    )

    if assets_3857 is not None and len(assets_3857) > 0:
        categories = [c for c in ASSET_CATEGORY_ORDER if c in set(assets_3857["__category"])]
        for cat in categories:
            subset = assets_3857[assets_3857["__category"] == cat]
            subset.plot(
                ax=ax,
                markersize=ASSET_POINT_SIZE,
                color=ASSET_CATEGORY_COLOR_MAP.get(cat, ASSET_POINT_COLOR),
                alpha=0.85,
                zorder=5,
                label=cat,
            )
        ax.legend(title="Assets", loc="lower left", fontsize=8, title_fontsize=9)

    if HAS_CTX:
        try:
            ctx.add_basemap(ax)
        except Exception as e:
            print(f"[warn] Basemap failed: {e}")

    ax.set_axis_off()
    ax.set_title("South East London: 65+ Population Density")

    plt.tight_layout()
    fig.savefig(OUTPUT_PNG, dpi=DPI)
    print(f"[done] Saved: {OUTPUT_PNG}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

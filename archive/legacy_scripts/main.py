"""
London Borough + LSOA + Deprivation (IMD) map

What it does
- Downloads borough-equivalent boundaries (LAD Dec 2023) from ONS ArcGIS FeatureServer
- Filters to Greater London boroughs + City of London
- Downloads LSOA Dec 2021 boundaries, clipped to London via an envelope query + pagination
- Downloads / reads Indices of Deprivation 2025 (IoD25) File 7 CSV, merges onto LSOAs
- Plots: borough outlines + LSOA choropleth by IMD decile (1 = most deprived)
- Saves a PNG output

Data sources
- LAD Dec 2023 boundaries UK BGC (ONS) FeatureServer (listed on data.gov.uk)
- LSOA Dec 2021 boundaries EW BGC V5 (ONS) FeatureServer (listed on data.gov.uk)
- English Indices of Deprivation 2025 (GOV.UK) File 7 CSV
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

# ONS ArcGIS FeatureServers (from data.gov.uk dataset pages)
LAD_FS_BASE = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Local_Authority_Districts_December_2023_Boundaries_UK_BGC/FeatureServer/0"
)
LSOA_FS_BASE = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V5/FeatureServer/0"
)

# IoD 2025 File 7 CSV (from GOV.UK release page)
IOD25_FILE7_CSV_URL = (
    "https://assets.publishing.service.gov.uk/media/691ded56d140bbbaa59a2a7d/"
    "File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv"
)

# Output
OUTPUT_PNG = "london_lsoa_imd25.png"
OUTPUT_PNG_PRIMARY = "london_lsoa_imd25_primary_care.png"
OUTPUT_PNG_OTHER = "london_lsoa_imd25_other_assets.png"
FIGSIZE = (12, 12)
DPI = 200
ASSETS_CSV = "assets.csv"
ASSET_POINT_SIZE = 18
ASSET_POINT_COLOR = "#111111"
ASSET_CATEGORY_COLOR_MAP = {
    "Primary Care": "#1A5CBA",
    "Acute Hospital": "#E91E8C",
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
IMD_CMAP = LinearSegmentedColormap.from_list(
    "LightWarm",
    ["#fff7ec", "#fee8c8", "#fdd49e", "#fdbb84", "#fd8d3c", "#fb6a4a", "#ef3b2c"],
)
IMD_ALPHA = 0.7
ICB_OUTLINE_COLOR = "#2B2B2B"
ICB_OUTLINE_WIDTH = 1.6
ICB_OUTLINE_STYLE = "--"

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

# Greater London borough names + City (match LAD name field)
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

REQUEST_TIMEOUT = 60
USER_AGENT = "London-IMD-mapper/1.0 (+python requests)"


# -----------------------------
# HELPERS
# -----------------------------

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
    geometry: Optional[Tuple[float, float, float, float]] = None,  # xmin,ymin,xmax,ymax
    geometry_type: str = "esriGeometryEnvelope",
    spatial_rel: str = "esriSpatialRelIntersects",
    page_size: int = 2000,
) -> gpd.GeoDataFrame:
    """
    Downloads *all* features from an ArcGIS FeatureServer layer.
    Supports optional envelope clipping using geometry=(xmin,ymin,xmax,ymax).
    Paginates using resultOffset/resultRecordCount.
    Returns GeoDataFrame in EPSG:out_sr (default 4326).
    """
    query_url = f"{layer_base_url}/query"

    # Determine total count first
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

        # geopandas can read geojson from a bytes buffer
        part = gpd.read_file(io.BytesIO(r.content))
        if len(part) == 0:
            # Avoid infinite loops if the service behaves unexpectedly
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
    # Common patterns for IoD/IMD files
    preferred = ["LSOA21CD", "LSOA11CD", "lsoa_code", "LSOA code (2011)", "LSOA code (2021)"]
    col = find_col(df, preferred)
    if col:
        return col

    # Heuristic: first column containing 'lsoa' and ending with 'cd' or 'code'
    for c in df.columns:
        cl = c.lower()
        if "lsoa" in cl and (cl.endswith("cd") or "code" in cl):
            return c

    raise ValueError("Could not identify an LSOA code column in the IoD file.")


def find_imd_decile_col(df: pd.DataFrame) -> str:
    preferred = ["IMD25_Decile", "IMD_Decile", "imd_decile", "Index of Multiple Deprivation (IMD) Decile"]
    col = find_col(df, preferred)
    if col:
        return col

    # Heuristic: look for columns containing 'imd' and 'decile'
    for c in df.columns:
        cl = c.lower()
        if "imd" in cl and "decile" in cl:
            return c

    # Some files label it as "IoD25 Decile" etc.
    for c in df.columns:
        cl = c.lower()
        if ("index of multiple deprivation" in cl or "iod" in cl) and "decile" in cl:
            return c

    raise ValueError("Could not identify an IMD decile column in the IoD file.")


def load_assets_points(
    csv_path: str,
    bounds: Optional[Tuple[float, float, float, float]] = None,  # xmin,ymin,xmax,ymax
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


# -----------------------------
# MAIN
# -----------------------------

def main() -> None:
    print("[info] Downloading LAD boundaries (UK) and filtering to Greater London...")
    lad = arcgis_query_to_gdf(LAD_FS_BASE, out_sr=4326)

    # Common LAD name fields in ONS boundary products
    lad_name_col = None
    for cand in ["LAD23NM", "LAD24NM", "LAD22NM", "LADNM", "NAME"]:
        if cand in lad.columns:
            lad_name_col = cand
            break
    if lad_name_col is None:
        raise ValueError(f"Could not find LAD name column. Available columns: {list(lad.columns)}")

    london_boroughs = lad[lad[lad_name_col].isin(LONDON_BOROUGHS_AND_CITY)].copy()
    if len(london_boroughs) == 0:
        raise ValueError("No London boroughs matched. Check LAD name field / spelling.")

    # Map boroughs to ICBs for outline plotting
    icb_map = {
        borough: icb
        for icb, boroughs in ICB_BOROUGHS_BY_LAD.items()
        for borough in boroughs
    }
    london_boroughs["__icb"] = london_boroughs[lad_name_col].map(icb_map)
    missing_icb = london_boroughs["__icb"].isna().sum()
    if missing_icb:
        print(f"[warn] {missing_icb} boroughs are missing an ICB mapping.")

    # London extent (envelope) for faster LSOA download
    xmin, ymin, xmax, ymax = london_boroughs.total_bounds
    pad = 0.05  # degrees padding to avoid edge misses
    env = (xmin - pad, ymin - pad, xmax + pad, ymax + pad)
    print(f"[info] London envelope (EPSG:4326) = {env}")

    print("[info] Downloading LSOA boundaries clipped to London envelope...")
    lsoa = arcgis_query_to_gdf(LSOA_FS_BASE, out_sr=4326, geometry=env)

    # Spatially clip to actual London borough geometry (remove envelope spillover)
    print("[info] Clipping LSOAs to London borough boundary...")
    london_union = london_boroughs.to_crs(4326).unary_union
    lsoa = lsoa[lsoa.intersects(london_union)].copy()

    # Identify LSOA code field in boundary layer
    lsoa_code_col = None
    for cand in ["LSOA21CD", "LSOA11CD", "LSOA_CODE", "CODE", "LSOA21CD "]:
        if cand in lsoa.columns:
            lsoa_code_col = cand
            break
    if lsoa_code_col is None:
        # heuristic
        for c in lsoa.columns:
            if "lsoa" in c.lower() and c.lower().endswith("cd"):
                lsoa_code_col = c
                break
    if lsoa_code_col is None:
        raise ValueError(f"Could not find LSOA code column in boundaries. Columns: {list(lsoa.columns)}")

    print(f"[info] Using LSOA boundary code column: {lsoa_code_col}")

    print("[info] Downloading IoD 2025 File 7 (CSV) and extracting IMD deciles...")
    iod = pd.read_csv(IOD25_FILE7_CSV_URL, dtype=str)

    iod_lsoa_col = find_lsoa_code_col(iod)
    iod_decile_col = find_imd_decile_col(iod)

    # Keep only what's needed; cast decile to numeric
    iod_small = iod[[iod_lsoa_col, iod_decile_col]].copy()
    iod_small[iod_decile_col] = pd.to_numeric(iod_small[iod_decile_col], errors="coerce")

    print(f"[info] Using IoD LSOA column: {iod_lsoa_col}")
    print(f"[info] Using IoD IMD decile column: {iod_decile_col}")

    print("[info] Merging IMD deciles onto LSOAs...")
    lsoa = lsoa.merge(
        iod_small,
        left_on=lsoa_code_col,
        right_on=iod_lsoa_col,
        how="left",
        validate="m:1",
    )

    missing = int(lsoa[iod_decile_col].isna().sum())
    print(f"[info] Missing IMD decile for {missing} LSOAs (likely geography mismatch if using different LSOA vintage).")

    # Plot in Web Mercator for basemap
    lsoa_3857 = lsoa.to_crs(3857)
    bor_3857 = london_boroughs.to_crs(3857)
    assets_3857 = None
    try:
        assets_3857 = load_assets_points(ASSETS_CSV, bounds=(xmin, ymin, xmax, ymax)).to_crs(3857)
        print(f"[info] Loaded {len(assets_3857)} assets with valid coordinates.")
    except Exception as e:
        print(f"[warn] Assets layer skipped: {e}")

    print("[info] Plotting...")
    def plot_map(
        assets_subset: Optional[gpd.GeoDataFrame],
        output_path: str,
        title: str,
    ) -> None:
        fig, ax = plt.subplots(1, 1, figsize=FIGSIZE)
        cax = inset_axes(
            ax,
            width="5%",
            height="30%",
            loc="lower right",
            borderpad=2,
        )

        # Choropleth
        lsoa_3857.plot(
            ax=ax,
            column=iod_decile_col,
            legend=True,
            cmap=IMD_CMAP.reversed(),
            alpha=IMD_ALPHA,
            linewidth=0.0,
            missing_kwds={"color": "lightgrey", "label": "Missing"},
            legend_kwds={"cax": cax},
        )
        cax.tick_params(labelsize=7, length=0, pad=2)
        cax.yaxis.set_ticks_position("left")
        if len(cax.get_yticks()) >= 2:
            cax.set_yticks([cax.get_yticks()[0], cax.get_yticks()[-1]])
        cax.set_yticklabels(["Most deprived", "Least deprived"])
        for label in cax.get_yticklabels():
            label.set_horizontalalignment("right")
        cax.set_ylabel("")

        # Borough outlines
        bor_3857.boundary.plot(ax=ax, linewidth=1.0)

        # ICB outlines (dissolved boroughs)
        icb_outline = london_boroughs.dropna(subset=["__icb"]).dissolve(by="__icb").to_crs(3857)
        icb_outline.boundary.plot(
            ax=ax,
            linewidth=ICB_OUTLINE_WIDTH,
            linestyle=ICB_OUTLINE_STYLE,
            color=ICB_OUTLINE_COLOR,
            alpha=0.8,
            zorder=4,
        )

        # Assets points
        if assets_subset is not None and len(assets_subset) > 0:
            categories = [c for c in ASSET_CATEGORY_ORDER if c in set(assets_subset["__category"])]
            for cat in categories:
                subset = assets_subset[assets_subset["__category"] == cat]
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
                ctx.add_basemap(ax)  # default provider; requires internet at runtime
            except Exception as e:
                print(f"[warn] Basemap failed: {e}")

        ax.set_axis_off()
        ax.set_title(title)

        plt.tight_layout()
        fig.savefig(output_path, dpi=DPI)
        print(f"[done] Saved: {output_path}")

    primary_assets = None
    other_assets = None
    if assets_3857 is not None:
        primary_assets = assets_3857[assets_3857["__category"] == "Primary Care"]
        other_assets = assets_3857[assets_3857["__category"] != "Primary Care"]

    plot_map(
        primary_assets,
        OUTPUT_PNG_PRIMARY,
        "Greater London: LSOA Deprivation (IMD 2025 Decile) + Primary Care",
    )
    plot_map(
        other_assets,
        OUTPUT_PNG_OTHER,
        "Greater London: LSOA Deprivation (IMD 2025 Decile) + Other Assets",
    )
    plot_map(
        assets_3857,
        OUTPUT_PNG,
        "Greater London: LSOA Deprivation (IMD 2025 Decile) + All Assets",
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

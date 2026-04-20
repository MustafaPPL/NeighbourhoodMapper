from __future__ import annotations

import io
import os
import re
import sys
import time
import urllib.parse
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import requests
from matplotlib.colors import LinearSegmentedColormap
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

from project_paths import get_maps_dir, get_older_people_dir, get_primary_care_dir


ROOT = Path(__file__).resolve().parent
DATA_DIR = get_older_people_dir()
MAPS_DIR = get_maps_dir()
PRIMARY_CARE_DIR = get_primary_care_dir()

LSOA_65_CSV = DATA_DIR / "65+ Population London LSOA.csv"
GP_WORKBOOK = DATA_DIR / "Combined List - GPs.xlsx"
NEIGHBOURHOOD_SHP = DATA_DIR / "neighbourhoods_shapefile.shp"
PHARMACY_CSV = DATA_DIR / "Pharmacy List.csv"
FAMILY_HUB_CSV = DATA_DIR / "Family Hub Sites.csv"
GP_GEO_CACHE_CSV = DATA_DIR / "combined_gps_geocoded.csv"
PHARMACY_GEO_CACHE_CSV = DATA_DIR / "pharmacy_geocoded.csv"
FAMILY_HUB_GEO_CACHE_CSV = DATA_DIR / "family_hub_geocoded.csv"
EXISTING_GP_COORDS = PRIMARY_CARE_DIR / "gp_practices_tomtom_geocoded.csv"

OUTPUT_PNG = MAPS_DIR / "london_65plus_proportion_neighbourhood_ward_gp.png"
ICB_OUTPUT_DIR = MAPS_DIR / "ICB 65+ maps"

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

ONS_LSOA_POP_XLSX_URL = (
    "https://www.ons.gov.uk/file?uri=/peoplepopulationandcommunity/"
    "populationandmigration/populationestimates/datasets/"
    "lowersuperoutputareamidyearpopulationestimatesnationalstatistics/"
    "mid2022revisednov2025tomid2024/sapelsoabroadage20222024.xlsx"
)

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

USER_AGENT = "London-65plus-GP-mapper/1.0 (+python requests)"
REQUEST_TIMEOUT = 60
FIGSIZE = (13, 13)
DPI = 250

CHOROPLETH_CMAP = LinearSegmentedColormap.from_list(
    "Aged65Plus",
    ["#f7fbff", "#deebf7", "#c6dbef", "#9ecae1", "#6baed6", "#3182bd", "#08519c"],
)

NEIGHBOURHOOD_LINE_MAIN_WIDTH = 1.0
NEIGHBOURHOOD_LINE_HALO_WIDTH = 1.6
LONDON_HWB_PATTERN = (
    "BARKING|BARNET|BEXLEY|BRENT|BROMLEY|CAMDEN|CITY OF LONDON|CROYDON|EALING|ENFIELD|"
    "GREENWICH|HACKNEY|HAMMERSMITH|HARINGEY|HARROW|HAVERING|HILLINGDON|HOUNSLOW|ISLINGTON|"
    "KENSINGTON|KINGSTON|LAMBETH|LEWISHAM|MERTON|NEWHAM|REDBRIDGE|RICHMOND|SOUTHWARK|"
    "SUTTON|TOWER HAMLETS|WALTHAM FOREST|WANDSWORTH|WESTMINSTER"
)


def _request_json(url: str, params: Dict, max_retries: int = 5) -> Dict:
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            if attempt == max_retries:
                raise
            sleep_s = min(2 ** attempt, 20)
            print(f"[warn] Request failed ({attempt}/{max_retries}): {exc}. Retrying in {sleep_s}s.")
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
        count_params.update(
            {
                "geometry": f"{xmin},{ymin},{xmax},{ymax}",
                "geometryType": geometry_type,
                "inSR": out_sr,
                "spatialRel": spatial_rel,
            }
        )

    total = int(_request_json(query_url, count_params).get("count", 0))
    print(f"[info] {layer_base_url.split('/')[-1]} features to fetch: {total}")

    parts: List[gpd.GeoDataFrame] = []
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
                    "geometryType": geometry_type,
                    "inSR": out_sr,
                    "spatialRel": spatial_rel,
                }
            )

        r = requests.get(query_url, params=params, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        part = gpd.read_file(io.BytesIO(r.content))
        if len(part) == 0:
            break
        parts.append(part)
        fetched += len(part)
        print(f"[info] fetched {fetched}/{total}")

    if not parts:
        return gpd.GeoDataFrame(geometry=[], crs=f"EPSG:{out_sr}")
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=f"EPSG:{out_sr}")


def find_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    cols = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        key = cand.lower().strip()
        if key in cols:
            return cols[key]
    return None


def normalize_name(name: str) -> str:
    text = str(name).strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def find_header_row(raw_df: pd.DataFrame) -> int:
    for idx, row in raw_df.iterrows():
        values = [str(v).strip().lower() for v in row.tolist()]
        if "practice name" in values and "practice code" in values:
            return int(idx)
    return 0


def load_lsoa_65plus_counts(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    lsoa_col = find_col(df, ["Lower layer Super Output Areas Code", "LSOA21CD", "LSOA code"])
    count_col = find_col(df, ["Observation", "Value", "Count"])
    age_col = find_col(df, ["Age (6 categories)", "Age", "Age group"])
    if not lsoa_col or not count_col:
        raise ValueError("Could not identify LSOA and count columns in 65+ population CSV.")

    if age_col:
        age_mask = df[age_col].astype(str).str.contains("65", case=False, na=False)
        df = df.loc[age_mask].copy()

    out = df[[lsoa_col, count_col]].copy()
    out.columns = ["LSOA_code", "population_65_plus"]
    out["population_65_plus"] = pd.to_numeric(out["population_65_plus"], errors="coerce")
    out = out.dropna(subset=["population_65_plus"])
    out["LSOA_code"] = out["LSOA_code"].astype(str).str.strip()
    return out


def load_lsoa_total_population(xlsx_url: str) -> pd.DataFrame:
    r = requests.get(xlsx_url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    xls = pd.ExcelFile(io.BytesIO(r.content))

    mid_sheets: List[Tuple[int, str]] = []
    for sheet in xls.sheet_names:
        lowered = sheet.lower()
        if lowered.startswith("mid-") and "lsoa 2021" in lowered:
            try:
                year = int(sheet.split()[0].replace("Mid-", ""))
                mid_sheets.append((year, sheet))
            except Exception:
                continue
    if not mid_sheets:
        raise ValueError("Could not identify latest ONS LSOA 2021 population sheet.")

    mid_sheets.sort()
    _, latest_sheet = mid_sheets[-1]
    df = pd.read_excel(xls, sheet_name=latest_sheet, header=3)
    lsoa_col = find_col(df, ["LSOA 2021 Code", "LSOA21CD", "LSOA Code (2021)"])
    total_col = find_col(df, ["Total", "All ages", "Population"])
    if not lsoa_col or not total_col:
        raise ValueError(f"Could not find LSOA/Total columns in sheet '{latest_sheet}'.")

    out = df[[lsoa_col, total_col]].copy()
    out.columns = ["LSOA_code", "population_total"]
    out["LSOA_code"] = out["LSOA_code"].astype(str).str.strip()
    out["population_total"] = pd.to_numeric(out["population_total"], errors="coerce")
    out = out.dropna(subset=["population_total"])
    print(f"[info] Using ONS sheet: {latest_sheet}")
    return out


def load_gp_list_from_workbook(path: Path) -> pd.DataFrame:
    xls = pd.ExcelFile(path)
    frames: List[pd.DataFrame] = []

    for sheet in xls.sheet_names:
        raw = pd.read_excel(xls, sheet_name=sheet, header=None)
        header_row = find_header_row(raw.head(20))
        df = pd.read_excel(xls, sheet_name=sheet, header=header_row)
        df.columns = [str(c).strip() for c in df.columns]

        name_col = find_col(df, ["Practice Name"])
        code_col = find_col(df, ["Practice Code"])
        borough_col = find_col(df, ["Borough"])
        if not name_col or not code_col:
            continue

        gp = df[[name_col, code_col] + ([borough_col] if borough_col else [])].copy()
        gp.columns = ["Practice Name", "Practice Code"] + (["Borough"] if borough_col else [])
        if "Borough" not in gp.columns:
            gp["Borough"] = ""
        gp["Sheet"] = sheet.strip()
        frames.append(gp)

    if not frames:
        raise ValueError("No GP practice tables found in workbook.")

    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["Practice Name", "Practice Code"])
    out["Practice Name"] = out["Practice Name"].astype(str).str.strip()
    out["Practice Code"] = out["Practice Code"].astype(str).str.strip().str.upper()
    out["Borough"] = out["Borough"].astype(str).str.strip()
    out["__name_norm"] = out["Practice Name"].map(normalize_name)
    out = out.drop_duplicates(subset=["Practice Code", "__name_norm"], keep="first")
    return out


def load_existing_gp_coords(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["Practice Code", "__name_norm", "Latitude", "Longitude"])

    df = pd.read_csv(path, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    code_col = find_col(df, ["Practice code", "Practice Code"])
    name_col = find_col(df, ["Practice name", "Practice Name"])
    lat_col = find_col(df, ["Latitude", "Lat"])
    lon_col = find_col(df, ["Longitude", "Lon", "Long"])
    if not code_col or not name_col or not lat_col or not lon_col:
        return pd.DataFrame(columns=["Practice Code", "__name_norm", "Latitude", "Longitude"])

    out = df[[code_col, name_col, lat_col, lon_col]].copy()
    out.columns = ["Practice Code", "Practice Name", "Latitude", "Longitude"]
    out["Practice Code"] = out["Practice Code"].astype(str).str.strip().str.upper()
    out["__name_norm"] = out["Practice Name"].astype(str).map(normalize_name)
    out["Latitude"] = pd.to_numeric(out["Latitude"], errors="coerce")
    out["Longitude"] = pd.to_numeric(out["Longitude"], errors="coerce")
    out = out.dropna(subset=["Latitude", "Longitude"])
    return out[["Practice Code", "__name_norm", "Latitude", "Longitude"]]


def load_tomtom_api_key() -> Optional[str]:
    env_key = os.getenv("TOMTOM_API_KEY")
    if env_key:
        return env_key.strip()

    script_path = PRIMARY_CARE_DIR / "primary_care.py"
    if not script_path.exists():
        return None
    text = script_path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r'TOMTOM_API_KEY\s*=\s*"([^"]+)"', text)
    if match:
        return match.group(1).strip()
    return None


def tomtom_geocode(practice_name: str, borough: str, api_key: str) -> Optional[Tuple[float, float]]:
    base_url = "https://api.tomtom.com/search/2/search"
    queries = [
        f"{practice_name}, {borough}, London, UK".strip(", "),
        f"{practice_name}, London, UK",
    ]
    for query in queries:
        url = f"{base_url}/{urllib.parse.quote(query)}.json"
        params = {"key": api_key, "limit": 1, "countrySet": "GB"}
        try:
            r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
            if r.status_code != 200:
                continue
            data = r.json()
            results = data.get("results") or []
            if not results:
                continue
            pos = results[0].get("position") or {}
            lat = pos.get("lat")
            lon = pos.get("lon")
            if lat is None or lon is None:
                continue
            return float(lat), float(lon)
        except Exception:
            continue
    return None


def normalize_postcode(value: str) -> str:
    text = str(value).upper().strip()
    text = re.sub(r"\s+", "", text)
    return text


def normalize_text(value: str) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def postcode_lookup_batch(postcodes: List[str]) -> Dict[str, Tuple[float, float]]:
    results: Dict[str, Tuple[float, float]] = {}
    if not postcodes:
        return results

    url = "https://api.postcodes.io/postcodes"
    for i in range(0, len(postcodes), 100):
        batch = postcodes[i : i + 100]
        payload = {"postcodes": batch}
        try:
            r = requests.post(url, json=payload, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                continue
            data = r.json().get("result") or []
            for entry in data:
                query = entry.get("query")
                result = entry.get("result")
                if not query or not result:
                    continue
                lat = result.get("latitude")
                lon = result.get("longitude")
                if lat is None or lon is None:
                    continue
                results[normalize_postcode(query)] = (float(lat), float(lon))
        except Exception:
            continue
        time.sleep(0.1)
    return results


def geocode_postcodes_with_cache(
    df: pd.DataFrame,
    postcode_col: str,
    cache_path: Path,
    site_label: str,
) -> pd.DataFrame:
    out = df.copy()
    out["__postcode_norm"] = out[postcode_col].astype(str).map(normalize_postcode)
    out = out[out["__postcode_norm"].str.len().between(5, 8)].copy()
    out["Latitude"] = pd.NA
    out["Longitude"] = pd.NA

    if cache_path.exists():
        cache = pd.read_csv(cache_path, dtype=str)
        cache.columns = [c.strip() for c in cache.columns]
        if {"Postcode", "Latitude", "Longitude"}.issubset(set(cache.columns)):
            cache["__postcode_norm"] = cache["Postcode"].astype(str).map(normalize_postcode)
            cache["Latitude"] = pd.to_numeric(cache["Latitude"], errors="coerce")
            cache["Longitude"] = pd.to_numeric(cache["Longitude"], errors="coerce")
            cache = cache.dropna(subset=["Latitude", "Longitude"])
            out = out.merge(
                cache[["__postcode_norm", "Latitude", "Longitude"]].drop_duplicates("__postcode_norm"),
                on="__postcode_norm",
                how="left",
                suffixes=("", "_cache"),
            )
            out["Latitude"] = out["Latitude"].combine_first(out["Latitude_cache"])
            out["Longitude"] = out["Longitude"].combine_first(out["Longitude_cache"])
            out = out.drop(columns=["Latitude_cache", "Longitude_cache"])

    missing = out["Latitude"].isna() | out["Longitude"].isna()
    missing_postcodes = out.loc[missing, "__postcode_norm"].dropna().drop_duplicates().tolist()
    if missing_postcodes:
        print(f"[info] Geocoding {len(missing_postcodes)} missing {site_label} postcodes via postcodes.io...")
        url = "https://api.postcodes.io/postcodes"
        for i in range(0, len(missing_postcodes), 100):
            batch = missing_postcodes[i : i + 100]
            payload = {"postcodes": batch}
            try:
                r = requests.post(url, json=payload, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    continue
                data = r.json().get("result") or []
                batch_rows = []
                for entry in data:
                    query = entry.get("query")
                    result = entry.get("result")
                    if not query or not result:
                        continue
                    lat = result.get("latitude")
                    lon = result.get("longitude")
                    if lat is None or lon is None:
                        continue
                    batch_rows.append({"__postcode_norm": normalize_postcode(query), "Latitude": lat, "Longitude": lon})
                if batch_rows:
                    batch_df = pd.DataFrame(batch_rows).drop_duplicates("__postcode_norm")
                    out = out.merge(batch_df, on="__postcode_norm", how="left", suffixes=("", "_new"))
                    out["Latitude"] = pd.to_numeric(out["Latitude"], errors="coerce").combine_first(
                        pd.to_numeric(out["Latitude_new"], errors="coerce")
                    )
                    out["Longitude"] = pd.to_numeric(out["Longitude"], errors="coerce").combine_first(
                        pd.to_numeric(out["Longitude_new"], errors="coerce")
                    )
                    out = out.drop(columns=["Latitude_new", "Longitude_new"])
            except Exception:
                continue
            time.sleep(0.1)

    cache_save = out[["__postcode_norm", "Latitude", "Longitude"]].copy()
    cache_save = cache_save.dropna(subset=["Latitude", "Longitude"]).drop_duplicates("__postcode_norm")
    cache_save = cache_save.rename(columns={"__postcode_norm": "Postcode"})
    cache_save.to_csv(cache_path, index=False)
    out["Latitude"] = pd.to_numeric(out["Latitude"], errors="coerce")
    out["Longitude"] = pd.to_numeric(out["Longitude"], errors="coerce")
    return out


def build_pharmacy_address_text(row: pd.Series) -> str:
    parts = [
        row.get("PHARMACY_TRADING_NAME", ""),
        row.get("ORGANISATION_NAME", ""),
        row.get("ADDRESS_FIELD_1", ""),
        row.get("ADDRESS_FIELD_2", ""),
        row.get("ADDRESS_FIELD_3", ""),
        row.get("ADDRESS_FIELD_4", ""),
        row.get("POST_CODE", ""),
        row.get("HEALTH_AND_WELLBEING_BOARD", ""),
        "UK",
    ]
    parts = [str(part).strip() for part in parts if str(part).strip() and str(part).strip().lower() != "nan"]
    return ", ".join(parts)


def tomtom_search_candidates(query: str, api_key: str, limit: int = 5) -> List[Dict]:
    url = f"https://api.tomtom.com/search/2/search/{urllib.parse.quote(query)}.json"
    params = {"key": api_key, "limit": limit, "countrySet": "GB"}
    try:
        r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get("results") or []
    except Exception:
        return []


def pharmacy_candidate_rank(candidate: Dict, row: pd.Series) -> float:
    address = candidate.get("address") or {}
    source_postcode = normalize_postcode(row.get("POST_CODE", ""))
    candidate_postcode = normalize_postcode(address.get("postalCode", ""))
    freeform = normalize_text(address.get("freeformAddress", ""))
    source_address = normalize_text(
        " ".join(
            [
                str(row.get("ADDRESS_FIELD_1", "")),
                str(row.get("ADDRESS_FIELD_2", "")),
                str(row.get("ADDRESS_FIELD_3", "")),
                str(row.get("ADDRESS_FIELD_4", "")),
                str(row.get("PHARMACY_TRADING_NAME", "")),
            ]
        )
    )

    score = float(candidate.get("score") or 0.0)
    if candidate_postcode == source_postcode and source_postcode:
        score += 100.0
    elif source_postcode and candidate_postcode[: len(source_postcode) - 3] == source_postcode[: len(source_postcode) - 3]:
        score += 15.0

    if source_address and freeform:
        score += 20.0 * SequenceMatcher(None, source_address, freeform).ratio()
        source_tokens = set(source_address.split())
        matched_tokens = set(freeform.split())
        if source_tokens:
            score += 30.0 * (len(source_tokens & matched_tokens) / len(source_tokens))
    return score


def geocode_pharmacy_record(row: pd.Series, api_key: str) -> Tuple[Optional[float], Optional[float], str, str]:
    source_postcode = normalize_postcode(row.get("POST_CODE", ""))
    queries = [
        build_pharmacy_address_text(row),
        ", ".join(
            [
                str(row.get("ADDRESS_FIELD_1", "")).strip(),
                str(row.get("ADDRESS_FIELD_2", "")).strip(),
                str(row.get("ADDRESS_FIELD_3", "")).strip(),
                str(row.get("ADDRESS_FIELD_4", "")).strip(),
                str(row.get("POST_CODE", "")).strip(),
                "UK",
            ]
        ),
        ", ".join(
            [
                str(row.get("PHARMACY_TRADING_NAME", "")).strip(),
                str(row.get("ADDRESS_FIELD_1", "")).strip(),
                str(row.get("POST_CODE", "")).strip(),
                "UK",
            ]
        ),
    ]

    best_candidate: Optional[Dict] = None
    best_score = float("-inf")
    for query in queries:
        query = ", ".join([part for part in query.split(", ") if part and part.lower() != "nan"])
        if not query:
            continue
        candidates = tomtom_search_candidates(query, api_key=api_key, limit=5)
        for candidate in candidates:
            rank = pharmacy_candidate_rank(candidate, row)
            if rank > best_score:
                best_score = rank
                best_candidate = candidate

    if best_candidate:
        address = best_candidate.get("address") or {}
        candidate_postcode = normalize_postcode(address.get("postalCode", ""))
        if candidate_postcode == source_postcode and source_postcode:
            pos = best_candidate.get("position") or {}
            lat = pos.get("lat")
            lon = pos.get("lon")
            if lat is not None and lon is not None:
                return float(lat), float(lon), "tomtom_address", str(address.get("freeformAddress", ""))

    return None, None, "unresolved", ""


def load_community_pharmacies(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    type_col = find_col(df, ["CONTRACT_TYPE", "Contract Type"])
    postcode_col = find_col(df, ["POST_CODE", "Postcode", "POSTCODE"])
    name_col = find_col(df, ["PHARMACY_TRADING_NAME", "ORGANISATION_NAME", "Name"])
    ods_col = find_col(df, ["PHARMACY_ODS_CODE_F_CODE", "ODS_CODE", "ODS Code"])
    if not postcode_col:
        raise ValueError("Could not find postcode column in pharmacy file.")

    if type_col:
        df = df[df[type_col].astype(str).str.contains("community", case=False, na=False)].copy()
    hwb_col = find_col(df, ["HEALTH_AND_WELLBEING_BOARD"])
    if hwb_col:
        df = df[df[hwb_col].astype(str).str.contains(LONDON_HWB_PATTERN, case=False, na=False)].copy()

    keep_candidates = [
        ods_col,
        name_col,
        find_col(df, ["ORGANISATION_NAME"]),
        find_col(df, ["ADDRESS_FIELD_1"]),
        find_col(df, ["ADDRESS_FIELD_2"]),
        find_col(df, ["ADDRESS_FIELD_3"]),
        find_col(df, ["ADDRESS_FIELD_4"]),
        postcode_col,
        find_col(df, ["HEALTH_AND_WELLBEING_BOARD"]),
    ]
    keep_cols = [col for col in keep_candidates if col]
    df = df[keep_cols].copy()
    rename_map = {
        postcode_col: "POST_CODE",
    }
    if ods_col:
        rename_map[ods_col] = "PHARMACY_ODS_CODE_F_CODE"
    if name_col:
        rename_map[name_col] = "PHARMACY_TRADING_NAME"
    org_col = find_col(df, ["ORGANISATION_NAME"])
    if org_col:
        rename_map[org_col] = "ORGANISATION_NAME"
    for field in ["ADDRESS_FIELD_1", "ADDRESS_FIELD_2", "ADDRESS_FIELD_3", "ADDRESS_FIELD_4", "HEALTH_AND_WELLBEING_BOARD"]:
        col = find_col(df, [field])
        if col:
            rename_map[col] = field
    df = df.rename(columns=rename_map)
    if "PHARMACY_TRADING_NAME" not in df.columns:
        df["PHARMACY_TRADING_NAME"] = "Community pharmacy"
    if "PHARMACY_ODS_CODE_F_CODE" not in df.columns:
        df["PHARMACY_ODS_CODE_F_CODE"] = df["PHARMACY_TRADING_NAME"].map(normalize_name)

    df["SiteName"] = df["PHARMACY_TRADING_NAME"].astype(str).str.strip()
    df["Postcode"] = df["POST_CODE"].astype(str).str.strip()
    df["Latitude"] = pd.NA
    df["Longitude"] = pd.NA
    df["GeocodeMethod"] = pd.NA
    df["MatchedAddress"] = pd.NA

    if PHARMACY_GEO_CACHE_CSV.exists():
        cache = pd.read_csv(PHARMACY_GEO_CACHE_CSV, dtype=str)
        cache.columns = [c.strip() for c in cache.columns]
        req = {"PHARMACY_ODS_CODE_F_CODE", "Latitude", "Longitude"}
        if req.issubset(set(cache.columns)):
            cache["PHARMACY_ODS_CODE_F_CODE"] = cache["PHARMACY_ODS_CODE_F_CODE"].astype(str).str.strip()
            cache["Latitude"] = pd.to_numeric(cache["Latitude"], errors="coerce")
            cache["Longitude"] = pd.to_numeric(cache["Longitude"], errors="coerce")
            cache = cache.dropna(subset=["Latitude", "Longitude"])
            carry_cols = ["PHARMACY_ODS_CODE_F_CODE", "Latitude", "Longitude"]
            for extra in ["GeocodeMethod", "MatchedAddress"]:
                if extra in cache.columns:
                    carry_cols.append(extra)
            df = df.merge(cache[carry_cols].drop_duplicates("PHARMACY_ODS_CODE_F_CODE"), on="PHARMACY_ODS_CODE_F_CODE", how="left", suffixes=("", "_cache"))
            df["Latitude"] = df["Latitude"].combine_first(df["Latitude_cache"])
            df["Longitude"] = df["Longitude"].combine_first(df["Longitude_cache"])
            if "GeocodeMethod_cache" in df.columns:
                df["GeocodeMethod"] = df["GeocodeMethod"].combine_first(df["GeocodeMethod_cache"])
            if "MatchedAddress_cache" in df.columns:
                df["MatchedAddress"] = df["MatchedAddress"].combine_first(df["MatchedAddress_cache"])
            df = df.drop(columns=[c for c in df.columns if c.endswith("_cache")])

    unresolved = df["Latitude"].isna() | df["Longitude"].isna()
    unresolved_count = int(unresolved.sum())
    print(f"[info] Pharmacy coordinates ready from cache: {len(df) - unresolved_count}/{len(df)}")
    unresolved = df["Latitude"].isna() | df["Longitude"].isna()
    unresolved_postcodes = (
        df.loc[unresolved, "POST_CODE"].astype(str).map(normalize_postcode).dropna().drop_duplicates().tolist()
    )
    if unresolved_postcodes:
        print(f"[info] Bulk postcode lookup for {len(unresolved_postcodes)} London pharmacy postcodes...")
        postcode_map = postcode_lookup_batch(unresolved_postcodes)
        for idx in df.index[unresolved]:
            postcode = normalize_postcode(df.at[idx, "POST_CODE"])
            coords = postcode_map.get(postcode)
            if coords:
                df.at[idx, "Latitude"] = coords[0]
                df.at[idx, "Longitude"] = coords[1]
                df.at[idx, "GeocodeMethod"] = "postcode_centroid"

    # Address geocoding is only worth the cost when postcode centroid is ambiguous.
    postcode_counts = df["POST_CODE"].astype(str).map(normalize_postcode).value_counts()
    ambiguous_postcodes = set(postcode_counts[postcode_counts > 1].index)
    needs_refinement = df["POST_CODE"].astype(str).map(normalize_postcode).isin(ambiguous_postcodes)
    refine_idx = df.index[needs_refinement].tolist()
    api_key = load_tomtom_api_key()
    if refine_idx and api_key:
        print(f"[info] Refining {len(refine_idx)} pharmacies with shared postcodes using address matching...")
        for i, idx in enumerate(refine_idx, start=1):
            lat, lon, method, matched_address = geocode_pharmacy_record(df.loc[idx], api_key)
            if lat is not None and lon is not None:
                df.at[idx, "Latitude"] = lat
                df.at[idx, "Longitude"] = lon
                df.at[idx, "GeocodeMethod"] = method
                df.at[idx, "MatchedAddress"] = matched_address
            if i % 50 == 0:
                print(f"[info] Refined {i}/{len(refine_idx)} ambiguous pharmacies")

    cache_save_cols = [
        "PHARMACY_ODS_CODE_F_CODE",
        "SiteName",
        "Postcode",
        "Latitude",
        "Longitude",
        "GeocodeMethod",
        "MatchedAddress",
    ]
    cache_save = df[cache_save_cols].copy()
    cache_save = cache_save.dropna(subset=["Latitude", "Longitude"]).drop_duplicates("PHARMACY_ODS_CODE_F_CODE")
    cache_save.to_csv(PHARMACY_GEO_CACHE_CSV, index=False)

    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    return df


def load_family_hubs(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    region_col = find_col(df, ["Region"])
    postcode_col = find_col(df, ["Postcode", "POST_CODE", "POSTCODE"])
    name_col = find_col(df, ["Family_Hub", "Family Hub", "Name"])
    if not postcode_col:
        raise ValueError("Could not find postcode column in family hub file.")

    if region_col:
        df = df[df[region_col].astype(str).str.contains("london", case=False, na=False)].copy()

    keep_cols = [postcode_col]
    if name_col:
        keep_cols.append(name_col)
    df = df[keep_cols].copy()
    df = df.rename(columns={postcode_col: "Postcode", (name_col or postcode_col): "SiteName"})
    if "SiteName" not in df.columns:
        df["SiteName"] = "Family hub"
    return geocode_postcodes_with_cache(df, "Postcode", FAMILY_HUB_GEO_CACHE_CSV, "family hub")


def attach_gp_coordinates(gps: pd.DataFrame) -> pd.DataFrame:
    gps = gps.copy()
    gps["Latitude"] = pd.NA
    gps["Longitude"] = pd.NA

    if GP_GEO_CACHE_CSV.exists():
        cached = pd.read_csv(GP_GEO_CACHE_CSV, dtype=str)
        cached.columns = [c.strip() for c in cached.columns]
        req_cols = {"Practice Code", "Latitude", "Longitude"}
        if req_cols.issubset(set(cached.columns)):
            cached["Practice Code"] = cached["Practice Code"].astype(str).str.strip().str.upper()
            cached["Latitude"] = pd.to_numeric(cached["Latitude"], errors="coerce")
            cached["Longitude"] = pd.to_numeric(cached["Longitude"], errors="coerce")
            cached = cached.dropna(subset=["Latitude", "Longitude"])
            gps = gps.merge(
                cached[["Practice Code", "Latitude", "Longitude"]].drop_duplicates("Practice Code"),
                on="Practice Code",
                how="left",
                suffixes=("", "_cache"),
            )
            gps["Latitude"] = gps["Latitude"].combine_first(gps["Latitude_cache"])
            gps["Longitude"] = gps["Longitude"].combine_first(gps["Longitude_cache"])
            gps = gps.drop(columns=["Latitude_cache", "Longitude_cache"])
            print(f"[info] Loaded cached coordinates from {GP_GEO_CACHE_CSV.name}")

    existing = load_existing_gp_coords(EXISTING_GP_COORDS)
    if not existing.empty:
        by_code = existing.drop_duplicates("Practice Code")[["Practice Code", "Latitude", "Longitude"]]
        gps = gps.merge(by_code, on="Practice Code", how="left", suffixes=("", "_code"))
        gps["Latitude"] = pd.to_numeric(gps["Latitude"], errors="coerce").combine_first(
            pd.to_numeric(gps["Latitude_code"], errors="coerce")
        )
        gps["Longitude"] = pd.to_numeric(gps["Longitude"], errors="coerce").combine_first(
            pd.to_numeric(gps["Longitude_code"], errors="coerce")
        )
        gps = gps.drop(columns=["Latitude_code", "Longitude_code"])

        by_name = existing.drop_duplicates("__name_norm")[["__name_norm", "Latitude", "Longitude"]]
        gps = gps.merge(by_name, on="__name_norm", how="left", suffixes=("", "_name"))
        gps["Latitude"] = pd.to_numeric(gps["Latitude"], errors="coerce").combine_first(
            pd.to_numeric(gps["Latitude_name"], errors="coerce")
        )
        gps["Longitude"] = pd.to_numeric(gps["Longitude"], errors="coerce").combine_first(
            pd.to_numeric(gps["Longitude_name"], errors="coerce")
        )
        gps = gps.drop(columns=["Latitude_name", "Longitude_name"])

    missing_mask = gps["Latitude"].isna() | gps["Longitude"].isna()
    missing_count = int(missing_mask.sum())
    print(f"[info] GP coordinates ready: {len(gps) - missing_count}/{len(gps)}")

    if missing_count == 0:
        return gps

    api_key = load_tomtom_api_key()
    if not api_key:
        print("[warn] TOMTOM_API_KEY not found. Missing GP points will be skipped.")
        return gps

    print(f"[info] Geocoding {missing_count} missing GP locations via TomTom...")
    missing_idx = gps.index[missing_mask].tolist()
    for i, idx in enumerate(missing_idx, start=1):
        row = gps.loc[idx]
        result = tomtom_geocode(str(row["Practice Name"]), str(row["Borough"]), api_key)
        if result:
            gps.at[idx, "Latitude"] = result[0]
            gps.at[idx, "Longitude"] = result[1]
        if i % 25 == 0:
            resolved = int(gps["Latitude"].notna().sum())
            print(f"[info] Geocoded {i}/{missing_count}; total resolved {resolved}/{len(gps)}")
            gps.drop(columns=["__name_norm"], errors="ignore").to_csv(GP_GEO_CACHE_CSV, index=False)
        time.sleep(0.15)

    gps.drop(columns=["__name_norm"], errors="ignore").to_csv(GP_GEO_CACHE_CSV, index=False)
    resolved = int(gps["Latitude"].notna().sum())
    print(f"[info] Final GP coordinates resolved: {resolved}/{len(gps)}")
    return gps


def plot_map(
    output_path: Path,
    title: str,
    lsoa_3857: gpd.GeoDataFrame,
    wards_3857: gpd.GeoDataFrame,
    neighbourhoods_3857: gpd.GeoDataFrame,
    gps_3857: gpd.GeoDataFrame,
    pharmacies_3857: gpd.GeoDataFrame,
    family_hubs_3857: gpd.GeoDataFrame,
    icb_outline_3857: Optional[gpd.GeoDataFrame] = None,
    show_icb_labels: bool = False,
    focus_geom_3857=None,
) -> None:
    fig, ax = plt.subplots(1, 1, figsize=FIGSIZE)
    cax = inset_axes(ax, width="4%", height="30%", loc="lower right", borderpad=2)

    lsoa_3857.plot(
        ax=ax,
        column="prop_65_plus",
        cmap=CHOROPLETH_CMAP,
        linewidth=0.0,
        alpha=0.9,
        legend=True,
        legend_kwds={"cax": cax},
        missing_kwds={"color": "#E5E5E5", "label": "Missing"},
    )
    cax.tick_params(labelsize=8, length=0, pad=2)
    cax.yaxis.set_ticks_position("left")
    cax.set_ylabel("Proportion aged 65+", fontsize=8)

    wards_3857.boundary.plot(ax=ax, linewidth=0.25, color="#585858", alpha=0.55, zorder=3)
    # Lighter neighbourhood boundaries: thinner dark line with a soft halo.
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

    if icb_outline_3857 is not None and len(icb_outline_3857) > 0:
        for _, row in icb_outline_3857.iterrows():
            icb_name = row["__icb"]
            row_gdf = gpd.GeoDataFrame([row], geometry="geometry", crs=icb_outline_3857.crs)
            row_gdf.boundary.plot(
                ax=ax,
                linewidth=2.0,
                color="white",
                alpha=0.7,
                zorder=6,
            )
            row_gdf.boundary.plot(
                ax=ax,
                linewidth=0.9,
                color="#4A4A4A",
                linestyle=(0, (6, 6)),
                alpha=0.55,
                zorder=6.1,
            )
            if show_icb_labels:
                rep = row.geometry.representative_point()
                label = icb_name.replace("NHS ", "").replace(" ICB", "")
                ax.text(
                    rep.x,
                    rep.y,
                    label,
                    fontsize=7,
                    color="#2A2A2A",
                    ha="center",
                    va="center",
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.65, "pad": 1.0},
                    zorder=8,
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

    if len(gps_3857) > 0 or len(pharmacies_3857) > 0 or len(family_hubs_3857) > 0:
        ax.legend(loc="lower left", fontsize=8, frameon=True)

    if focus_geom_3857 is not None and not focus_geom_3857.is_empty:
        minx, miny, maxx, maxy = focus_geom_3857.bounds
        pad_x = (maxx - minx) * 0.03
        pad_y = (maxy - miny) * 0.03
        ax.set_xlim(minx - pad_x, maxx + pad_x)
        ax.set_ylim(miny - pad_y, maxy + pad_y)

    ax.set_axis_off()
    ax.set_title(title)
    plt.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    print(f"[done] Saved map: {output_path}")


def main() -> None:
    if not LSOA_65_CSV.exists():
        raise FileNotFoundError(f"Missing file: {LSOA_65_CSV}")
    if not GP_WORKBOOK.exists():
        raise FileNotFoundError(f"Missing file: {GP_WORKBOOK}")
    if not NEIGHBOURHOOD_SHP.exists():
        raise FileNotFoundError(f"Missing file: {NEIGHBOURHOOD_SHP}")
    if not PHARMACY_CSV.exists():
        raise FileNotFoundError(f"Missing file: {PHARMACY_CSV}")
    if not FAMILY_HUB_CSV.exists():
        raise FileNotFoundError(f"Missing file: {FAMILY_HUB_CSV}")

    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    ICB_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[info] Loading local 65+ population and GP files...")
    lsoa_65 = load_lsoa_65plus_counts(LSOA_65_CSV)
    gp_df = load_gp_list_from_workbook(GP_WORKBOOK)
    gp_df = attach_gp_coordinates(gp_df)
    pharmacy_df = load_community_pharmacies(PHARMACY_CSV)
    family_hub_df = load_family_hubs(FAMILY_HUB_CSV)

    print("[info] Downloading LAD boundaries and filtering to Greater London...")
    lad = arcgis_query_to_gdf(LAD_FS_BASE, out_sr=4326)
    lad_name_col = find_col(lad, ["LAD23NM", "LAD24NM", "LAD22NM", "LADNM", "NAME"])
    if not lad_name_col:
        raise ValueError(f"Could not find LAD name column. Available: {list(lad.columns)}")
    london_boroughs = lad[lad[lad_name_col].isin(LONDON_BOROUGHS_AND_CITY)].copy()
    if london_boroughs.empty:
        raise ValueError("No London boroughs matched in LAD layer.")
    borough_to_icb = {
        borough: icb
        for icb, boroughs in ICB_BOROUGHS_BY_LAD.items()
        for borough in boroughs
    }
    london_boroughs["__icb"] = london_boroughs[lad_name_col].map(borough_to_icb)

    xmin, ymin, xmax, ymax = london_boroughs.total_bounds
    pad = 0.05
    env = (xmin - pad, ymin - pad, xmax + pad, ymax + pad)

    print("[info] Downloading LSOA boundaries...")
    lsoa = arcgis_query_to_gdf(LSOA_FS_BASE, out_sr=4326, geometry=env)
    london_union = london_boroughs.unary_union
    lsoa = lsoa[lsoa.intersects(london_union)].copy()

    lsoa_code_col = find_col(lsoa, ["LSOA21CD", "LSOA11CD", "LSOA_CODE", "CODE"])
    if not lsoa_code_col:
        for col in lsoa.columns:
            cl = str(col).lower()
            if "lsoa" in cl and cl.endswith("cd"):
                lsoa_code_col = col
                break
    if not lsoa_code_col:
        raise ValueError("Could not find LSOA code column in boundaries.")

    print("[info] Loading total population by LSOA from ONS...")
    lsoa_total = load_lsoa_total_population(ONS_LSOA_POP_XLSX_URL)

    print("[info] Building 65+ proportion layer...")
    lsoa = lsoa.merge(lsoa_65, left_on=lsoa_code_col, right_on="LSOA_code", how="left", validate="1:1")
    lsoa = lsoa.merge(lsoa_total, left_on=lsoa_code_col, right_on="LSOA_code", how="left", validate="1:1")
    lsoa["prop_65_plus"] = lsoa["population_65_plus"] / lsoa["population_total"]
    lsoa.loc[~lsoa["prop_65_plus"].between(0, 1), "prop_65_plus"] = pd.NA

    print("[info] Downloading ward boundaries and clipping to London...")
    wards = arcgis_query_to_gdf(WARD_FS_BASE, out_sr=4326, geometry=env)
    wards = wards[wards.intersects(london_union)].copy()

    print("[info] Loading neighbourhood boundaries...")
    neighbourhoods = gpd.read_file(NEIGHBOURHOOD_SHP).to_crs(4326)
    if "__icb" not in neighbourhoods.columns:
        ngh_icb_col = find_col(neighbourhoods, ["ICB", "icb"])
        if ngh_icb_col:
            abbrev_to_full = {
                "NCL": "NHS North Central London ICB",
                "NEL": "NHS North East London ICB",
                "NWL": "NHS North West London ICB",
                "SEL": "NHS South East London ICB",
                "SWL": "NHS South West London ICB",
            }
            neighbourhoods["__icb"] = neighbourhoods[ngh_icb_col].astype(str).str.strip().str.upper().map(abbrev_to_full)

    gp_points = gp_df.dropna(subset=["Latitude", "Longitude"]).copy()
    gp_points = gpd.GeoDataFrame(
        gp_points,
        geometry=gpd.points_from_xy(gp_points["Longitude"], gp_points["Latitude"]),
        crs="EPSG:4326",
    )
    gp_points = gp_points[gp_points.intersects(london_union)].copy()
    if "Borough" in gp_points.columns:
        gp_points["__icb"] = gp_points["Borough"].map(borough_to_icb)

    pharmacy_points = pharmacy_df.dropna(subset=["Latitude", "Longitude"]).copy()
    pharmacy_points = gpd.GeoDataFrame(
        pharmacy_points,
        geometry=gpd.points_from_xy(pharmacy_points["Longitude"], pharmacy_points["Latitude"]),
        crs="EPSG:4326",
    )
    pharmacy_points = pharmacy_points[pharmacy_points.intersects(london_union)].copy()

    family_hub_points = family_hub_df.dropna(subset=["Latitude", "Longitude"]).copy()
    family_hub_points = gpd.GeoDataFrame(
        family_hub_points,
        geometry=gpd.points_from_xy(family_hub_points["Longitude"], family_hub_points["Latitude"]),
        crs="EPSG:4326",
    )
    family_hub_points = family_hub_points[family_hub_points.intersects(london_union)].copy()

    lsoa_3857 = lsoa.to_crs(3857)
    wards_3857 = wards.to_crs(3857)
    neighbourhoods_3857 = neighbourhoods.to_crs(3857)
    gps_3857 = gp_points.to_crs(3857)
    pharmacies_3857 = pharmacy_points.to_crs(3857)
    family_hubs_3857 = family_hub_points.to_crs(3857)
    icb_outline_3857 = london_boroughs.dropna(subset=["__icb"]).dissolve(by="__icb").reset_index().to_crs(3857)

    print("[info] Plotting London-wide map...")
    plot_map(
        output_path=OUTPUT_PNG,
        title="London LSOA Proportion Aged 65+ with Neighbourhood, Ward and Service Sites",
        lsoa_3857=lsoa_3857,
        wards_3857=wards_3857,
        neighbourhoods_3857=neighbourhoods_3857,
        gps_3857=gps_3857,
        pharmacies_3857=pharmacies_3857,
        family_hubs_3857=family_hubs_3857,
        icb_outline_3857=icb_outline_3857,
        show_icb_labels=True,
        focus_geom_3857=london_boroughs.to_crs(3857).unary_union,
    )

    print("[info] Plotting one map per ICB...")
    lsoa_4326 = lsoa_3857.to_crs(4326)
    wards_4326 = wards_3857.to_crs(4326)
    neighbourhoods_4326 = neighbourhoods_3857.to_crs(4326)
    gps_4326 = gps_3857.to_crs(4326)
    pharmacies_4326 = pharmacies_3857.to_crs(4326)
    family_hubs_4326 = family_hubs_3857.to_crs(4326)
    for icb_name in ICB_BOROUGHS_BY_LAD:
        icb_outline = icb_outline_3857[icb_outline_3857["__icb"] == icb_name]
        if icb_outline.empty:
            continue
        icb_union = icb_outline.to_crs(4326).unary_union
        icb_union_3857 = icb_outline.unary_union

        lsoa_icb = lsoa_3857[lsoa_4326.intersects(icb_union)]
        wards_icb = wards_3857[wards_4326.intersects(icb_union)]
        neighbourhoods_icb = neighbourhoods_3857[neighbourhoods_4326.intersects(icb_union)]
        gps_icb = gps_3857[gps_4326.intersects(icb_union)]
        pharmacies_icb = pharmacies_3857[pharmacies_4326.intersects(icb_union)]
        family_hubs_icb = family_hubs_3857[family_hubs_4326.intersects(icb_union)]

        # Hard clip layers to the ICB footprint to avoid large off-area whitespace.
        lsoa_icb = lsoa_icb.clip(icb_union_3857)
        wards_icb = wards_icb.clip(icb_union_3857)
        neighbourhoods_icb = neighbourhoods_icb.clip(icb_union_3857)
        gps_icb = gps_icb[gps_icb.intersects(icb_union_3857)]
        pharmacies_icb = pharmacies_icb[pharmacies_icb.intersects(icb_union_3857)]
        family_hubs_icb = family_hubs_icb[family_hubs_icb.intersects(icb_union_3857)]

        slug = (
            icb_name.replace("NHS ", "")
            .replace(" ICB", "")
            .replace(" ", "_")
            .replace("/", "_")
            .lower()
        )
        icb_output = ICB_OUTPUT_DIR / f"{slug}_65plus_gp_map.png"
        plot_map(
            output_path=icb_output,
            title=f"{icb_name}: LSOA Proportion Aged 65+ and Service Sites",
            lsoa_3857=lsoa_icb,
            wards_3857=wards_icb,
            neighbourhoods_3857=neighbourhoods_icb,
            gps_3857=gps_icb,
            pharmacies_3857=pharmacies_icb,
            family_hubs_3857=family_hubs_icb,
            icb_outline_3857=icb_outline,
            show_icb_labels=False,
            focus_geom_3857=icb_union_3857,
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

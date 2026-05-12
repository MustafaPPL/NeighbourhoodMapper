"""
Batch script: geocode ERIC 2024/25 NHS estate sites for London trusts.

Usage:
    python scripts/analysis/build_eric_geocoded.py --eric-csv data/eric_2024_25.csv

Output:
    data/cache/eric_sites_geocoded.csv
    Columns: site_name, trust_name, postcode, latitude, longitude, geocode_source
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

OUTPUT_PATH = Path("data/cache/eric_sites_geocoded.csv")
POSTCODES_IO_BASE = "https://api.postcodes.io/postcodes"
REQUEST_DELAY_S = 0.1

# London NHS organisation code prefixes (STP/ICB and trust codes)
_LONDON_ORG_PREFIXES = ("Q", "R")  # Q = ICB/CCG, R = NHS trust
_LONDON_KEYWORDS = (
    "london",
    "barnet",
    "camden",
    "enfield",
    "haringey",
    "islington",
    "hackney",
    "tower hamlets",
    "newham",
    "waltham forest",
    "redbridge",
    "havering",
    "barking",
    "dagenham",
    "bexley",
    "greenwich",
    "lewisham",
    "southwark",
    "lambeth",
    "wandsworth",
    "merton",
    "sutton",
    "croydon",
    "bromley",
    "kingston",
    "richmond",
    "hounslow",
    "ealing",
    "hillingdon",
    "harrow",
    "brent",
    "kensington",
    "chelsea",
    "westminster",
    "hammersmith",
    "fulham",
    "city of london",
)


def _is_london_row(row: pd.Series, org_col: str | None, trust_col: str | None) -> bool:
    if org_col and isinstance(row.get(org_col), str):
        code = str(row[org_col]).strip().upper()
        if any(code.startswith(p) for p in _LONDON_ORG_PREFIXES):
            return True
    if trust_col and isinstance(row.get(trust_col), str):
        name_lower = str(row[trust_col]).lower()
        if any(kw in name_lower for kw in _LONDON_KEYWORDS):
            return True
    return False


def _detect_col(columns: list[str], candidates: list[str]) -> str | None:
    normalised = {c.strip().lower(): c for c in columns}
    for cand in candidates:
        match = normalised.get(cand.lower())
        if match is not None:
            return match
    return None


def _geocode_postcode(postcode: str) -> tuple[float, float] | None:
    normalised = "".join(postcode.upper().split())
    try:
        resp = requests.get(f"{POSTCODES_IO_BASE}/{normalised}", timeout=20)
        if resp.status_code != 200:
            return None
        result = resp.json().get("result")
        if not isinstance(result, dict):
            return None
        lat = result.get("latitude")
        lon = result.get("longitude")
        if lat is None or lon is None:
            return None
        return float(lat), float(lon)
    except Exception:
        return None


def load_eric_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, low_memory=False, encoding="latin-1")
    df.columns = df.columns.str.strip()
    return df


def filter_london_sites(df: pd.DataFrame) -> pd.DataFrame:
    # Try filtering by Commissioning Region first (most reliable for ERIC format)
    region_col = _detect_col(list(df.columns), ["commissioning region", "region"])
    if region_col and df[region_col].str.contains("LONDON", case=False, na=False).any():
        return df[df[region_col].str.contains("LONDON", case=False, na=False)].copy()

    org_col = _detect_col(list(df.columns), ["trust code", "org_code", "organisation_code", "OrganisationCode", "OrgCode"])
    trust_col = _detect_col(list(df.columns), ["trust name", "trust_name", "TrustName", "organisation_name", "OrganisationName"])
    mask = df.apply(lambda row: _is_london_row(row, org_col, trust_col), axis=1)
    return df[mask].copy()


def build_geocoded(df: pd.DataFrame, cache_path: Path | None = None) -> pd.DataFrame:
    site_col = _detect_col(list(df.columns), ["site name", "site_name", "SiteName"])
    trust_col = _detect_col(list(df.columns), ["trust name", "trust_name", "TrustName", "organisation_name", "OrganisationName"])
    postcode_col = _detect_col(list(df.columns), ["post code", "site_postcode", "SitePostcode", "postcode", "Postcode"])
    lat_col = _detect_col(list(df.columns), ["latitude", "Latitude", "lat"])
    lon_col = _detect_col(list(df.columns), ["longitude", "Longitude", "lon", "long"])

    existing_cache: dict[str, tuple[float, float]] = {}
    if cache_path and cache_path.exists():
        cached = pd.read_csv(cache_path, dtype=str)
        for _, row in cached.iterrows():
            pc = "".join(str(row.get("postcode", "")).upper().split())
            try:
                existing_cache[pc] = (float(row["latitude"]), float(row["longitude"]))
            except (ValueError, KeyError):
                pass

    rows: list[dict] = []
    failed: list[str] = []

    for _, row in df.iterrows():
        site_name = str(row[site_col]).strip() if site_col else ""
        trust_name = str(row[trust_col]).strip() if trust_col else ""
        postcode_raw = str(row[postcode_col]).strip() if postcode_col else ""
        postcode_norm = "".join(postcode_raw.upper().split())

        # Use embedded coordinates if available
        if lat_col and lon_col:
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    rows.append({
                        "site_name": site_name,
                        "trust_name": trust_name,
                        "postcode": postcode_raw,
                        "latitude": lat,
                        "longitude": lon,
                        "geocode_source": "eric_csv_coordinates",
                    })
                    continue
            except (ValueError, TypeError):
                pass

        if not postcode_norm:
            failed.append(site_name or "unknown")
            continue

        if postcode_norm in existing_cache:
            lat, lon = existing_cache[postcode_norm]
            rows.append({
                "site_name": site_name,
                "trust_name": trust_name,
                "postcode": postcode_raw,
                "latitude": lat,
                "longitude": lon,
                "geocode_source": "cached_postcodes_io",
            })
            continue

        result = _geocode_postcode(postcode_norm)
        time.sleep(REQUEST_DELAY_S)
        if result is None:
            failed.append(f"{site_name} ({postcode_raw})")
            continue
        lat, lon = result
        existing_cache[postcode_norm] = (lat, lon)
        rows.append({
            "site_name": site_name,
            "trust_name": trust_name,
            "postcode": postcode_raw,
            "latitude": lat,
            "longitude": lon,
            "geocode_source": "postcodes_io",
        })

    return pd.DataFrame(rows), failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocode ERIC 2024/25 NHS estate sites for London")
    parser.add_argument("--eric-csv", required=True, type=Path, help="Path to the ERIC 2024/25 site CSV")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output CSV path")
    args = parser.parse_args()

    if not args.eric_csv.exists():
        print(f"ERROR: ERIC CSV not found: {args.eric_csv}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading ERIC CSV: {args.eric_csv}")
    df = load_eric_csv(args.eric_csv)
    print(f"  Total rows: {len(df)}")

    london = filter_london_sites(df)
    print(f"  London rows: {len(london)}")

    if london.empty:
        print("No London sites found — check column names in the ERIC CSV.")
        sys.exit(1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    geocoded, failed = build_geocoded(london, cache_path=args.output)

    geocoded.to_csv(args.output, index=False)
    print(f"Written {len(geocoded)} geocoded sites to {args.output}")
    if failed:
        print(f"Failed to geocode {len(failed)} site(s):")
        for name in failed:
            print(f"  - {name}")


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable

import pandas as pd

from project_paths import OUTPUT_DIR, get_older_people_dir


ROOT = Path(__file__).resolve().parent
DATA_DIR = get_older_people_dir()

PHARMACY_CSV = DATA_DIR / "Pharmacy List.csv"
PHARMACY_GEO_CSV = DATA_DIR / "pharmacy_geocoded.csv"
FAMILY_HUB_CSV = DATA_DIR / "Family Hub Sites.csv"
FAMILY_HUB_GEO_CSV = DATA_DIR / "family_hub_geocoded.csv"

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

SHEET_NAMES = {
    "NHS North Central London ICB": "North Central London",
    "NHS North East London ICB": "North East London",
    "NHS North West London ICB": "North West London",
    "NHS South East London ICB": "South East London",
    "NHS South West London ICB": "South West London",
}

UPPER_BOROUGH_NORMALIZATION = {
    "BARKING AND DAGENHAM": "Barking and Dagenham",
    "BARNET": "Barnet",
    "BEXLEY": "Bexley",
    "BRENT": "Brent",
    "BROMLEY": "Bromley",
    "CAMDEN": "Camden",
    "CITY OF LONDON": "City of London",
    "CROYDON": "Croydon",
    "EALING": "Ealing",
    "ENFIELD": "Enfield",
    "GREENWICH": "Greenwich",
    "HACKNEY": "Hackney",
    "HAMMERSMITH AND FULHAM": "Hammersmith and Fulham",
    "HARINGEY": "Haringey",
    "HARROW": "Harrow",
    "HAVERING": "Havering",
    "HILLINGDON": "Hillingdon",
    "HOUNSLOW": "Hounslow",
    "ISLINGTON": "Islington",
    "KENSINGTON AND CHELSEA": "Kensington and Chelsea",
    "KINGSTON": "Kingston upon Thames",
    "KINGSTON UPON THAMES": "Kingston upon Thames",
    "LAMBETH": "Lambeth",
    "LEWISHAM": "Lewisham",
    "MERTON": "Merton",
    "NEWHAM": "Newham",
    "REDBRIDGE": "Redbridge",
    "RICHMOND": "Richmond upon Thames",
    "RICHMOND UPON THAMES": "Richmond upon Thames",
    "SOUTHWARK": "Southwark",
    "SUTTON": "Sutton",
    "TOWER HAMLETS": "Tower Hamlets",
    "WALTHAM FOREST": "Waltham Forest",
    "WANDSWORTH": "Wandsworth",
    "WESTMINSTER": "Westminster",
}


def normalize_postcode(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip().upper().replace(" ", "")
    return text


def borough_to_icb_map() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for icb, boroughs in ICB_BOROUGHS_BY_LAD.items():
        for borough in boroughs:
            mapping[borough] = icb
    return mapping


def reorder_columns(df: pd.DataFrame, first_columns: Iterable[str]) -> pd.DataFrame:
    first = [col for col in first_columns if col in df.columns]
    remainder = [col for col in df.columns if col not in first]
    return df[first + remainder]


def write_workbook(path: Path, sheets: Dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for icb_name in ICB_BOROUGHS_BY_LAD:
            sheet_name = SHEET_NAMES[icb_name]
            df = sheets[icb_name].copy()
            df.to_excel(writer, sheet_name=sheet_name, index=False)


def build_pharmacy_dataset() -> Dict[str, pd.DataFrame]:
    df = pd.read_csv(PHARMACY_CSV, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df = df[df["CONTRACT_TYPE"].fillna("").str.contains("community", case=False, na=False)].copy()
    df = df[df["HEALTH_AND_WELLBEING_BOARD"].fillna("").str.contains(LONDON_HWB_PATTERN, case=False, na=False)].copy()

    df["Borough"] = (
        df["HEALTH_AND_WELLBEING_BOARD"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .map(UPPER_BOROUGH_NORMALIZATION)
    )
    df["ICB"] = df["Borough"].map(borough_to_icb_map())
    df["Postcode_normalized"] = df["POST_CODE"].map(normalize_postcode)

    geocoded = pd.read_csv(PHARMACY_GEO_CSV, dtype=str)
    geocoded.columns = [c.strip() for c in geocoded.columns]
    geocoded["Postcode_normalized"] = geocoded["Postcode"].map(normalize_postcode)
    geocoded = geocoded.rename(
        columns={
            "PHARMACY_ODS_CODE_F_CODE": "PHARMACY_ODS_CODE_F_CODE",
            "Postcode": "Geocode_Postcode",
            "Latitude": "Latitude",
            "Longitude": "Longitude",
            "GeocodeMethod": "GeocodeMethod",
            "MatchedAddress": "MatchedAddress",
        }
    )

    df = df.merge(
        geocoded[
            [
                "PHARMACY_ODS_CODE_F_CODE",
                "Geocode_Postcode",
                "Latitude",
                "Longitude",
                "GeocodeMethod",
                "MatchedAddress",
            ]
        ].drop_duplicates("PHARMACY_ODS_CODE_F_CODE"),
        on="PHARMACY_ODS_CODE_F_CODE",
        how="left",
    )

    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    df = reorder_columns(
        df,
        [
            "ICB",
            "Borough",
            "PHARMACY_ODS_CODE_F_CODE",
            "PHARMACY_TRADING_NAME",
            "ORGANISATION_NAME",
            "POST_CODE",
            "Postcode_normalized",
            "Latitude",
            "Longitude",
            "GeocodeMethod",
            "MatchedAddress",
        ],
    )

    return {icb: df[df["ICB"] == icb].sort_values(["Borough", "PHARMACY_TRADING_NAME", "POST_CODE"]) for icb in ICB_BOROUGHS_BY_LAD}


def build_family_hub_dataset() -> Dict[str, pd.DataFrame]:
    df = pd.read_csv(FAMILY_HUB_CSV, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df = df[df["Region"].fillna("").str.contains("london", case=False, na=False)].copy()

    df["Borough"] = df["Local_Authority"].fillna("").astype(str).str.strip()
    df["ICB"] = df["Borough"].map(borough_to_icb_map())
    df["Postcode_normalized"] = df["Postcode"].map(normalize_postcode)

    geocoded = pd.read_csv(FAMILY_HUB_GEO_CSV, dtype=str)
    geocoded.columns = [c.strip() for c in geocoded.columns]
    geocoded["Postcode_normalized"] = geocoded["Postcode"].map(normalize_postcode)
    geocoded = geocoded.rename(
        columns={
            "Postcode": "Geocode_Postcode",
            "Latitude": "Latitude",
            "Longitude": "Longitude",
        }
    )

    df = df.merge(
        geocoded[["Postcode_normalized", "Geocode_Postcode", "Latitude", "Longitude"]].drop_duplicates(
            "Postcode_normalized"
        ),
        on="Postcode_normalized",
        how="left",
    )

    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    df = reorder_columns(
        df,
        [
            "ICB",
            "Borough",
            "Family_Hub",
            "Postcode",
            "Postcode_normalized",
            "Latitude",
            "Longitude",
            "Programme",
            "Region",
        ],
    )

    return {icb: df[df["ICB"] == icb].sort_values(["Borough", "Family_Hub", "Postcode"]) for icb in ICB_BOROUGHS_BY_LAD}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pharmacy_sheets = build_pharmacy_dataset()
    family_hub_sheets = build_family_hub_dataset()

    write_workbook(OUTPUT_DIR / "community_pharmacy_by_icb.xlsx", pharmacy_sheets)
    write_workbook(OUTPUT_DIR / "family_hubs_by_icb.xlsx", family_hub_sheets)

    print("Created:")
    print(OUTPUT_DIR / "community_pharmacy_by_icb.xlsx")
    for icb, df in pharmacy_sheets.items():
        print(f"  {SHEET_NAMES[icb]}: {len(df)} rows")
    print(OUTPUT_DIR / "family_hubs_by_icb.xlsx")
    for icb, df in family_hub_sheets.items():
        print(f"  {SHEET_NAMES[icb]}: {len(df)} rows")


if __name__ == "__main__":
    main()


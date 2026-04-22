from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from build_weighted_priority_map import (
    DEFAULT_65PLUS_CSV,
    DEFAULT_DEPRIVATION_CSV,
    DEFAULT_POPULATION_CSV,
    FAMILY_HUB_CSV,
    FAMILY_HUB_GEO_CACHE_CSV,
    GP_GEO_CACHE_CSV,
    ICB_BOROUGHS_BY_LAD,
    NEIGHBOURHOOD_SHP,
    PHARMACY_CSV,
    PHARMACY_GEO_CACHE_CSV,
)


WGS84 = "EPSG:4326"
BRITISH_NATIONAL_GRID = "EPSG:27700"


@dataclass(frozen=True)
class AppConfig:
    deprivation_csv: Path = DEFAULT_DEPRIVATION_CSV
    population_csv: Path = DEFAULT_POPULATION_CSV
    older_people_csv: Path = DEFAULT_65PLUS_CSV
    gp_geocoded_csv: Path = GP_GEO_CACHE_CSV
    pharmacy_csv: Path = PHARMACY_CSV
    pharmacy_geocoded_csv: Path = PHARMACY_GEO_CACHE_CSV
    family_hub_csv: Path = FAMILY_HUB_CSV
    family_hub_geocoded_csv: Path = FAMILY_HUB_GEO_CACHE_CSV
    neighbourhoods_path: Path = NEIGHBOURHOOD_SHP
    lsoa_source: str = "live_arcgis"
    local_lsoa_path: Path | None = None
    postcode_lsoa_lookup_csv: Path = Path("data/PCD to LSOA.csv")
    postcode_source: str = "postcodes_io"
    postcode_coordinate_lookup_csv: Path | None = None
    postcode_api_base_url: str = "https://api.postcodes.io/postcodes"


ICB_CHOICES = list(ICB_BOROUGHS_BY_LAD)

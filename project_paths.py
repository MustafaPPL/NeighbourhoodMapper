from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
OLDER_PEOPLE_DIR = DATA_DIR / "older_people"
PRIMARY_CARE_DIR = DATA_DIR / "primary_care"
OUTPUT_DIR = ROOT / "output"
MAPS_DIR = OUTPUT_DIR / "maps"

LEGACY_OLDER_PEOPLE_DIR = ROOT / "65+ Data"
LEGACY_PRIMARY_CARE_DIR = ROOT / "primary_care"
LEGACY_MAPS_DIR = ROOT / "Maps"


def first_existing_path(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def get_older_people_dir() -> Path:
    return first_existing_path(OLDER_PEOPLE_DIR, LEGACY_OLDER_PEOPLE_DIR)


def get_primary_care_dir() -> Path:
    return first_existing_path(PRIMARY_CARE_DIR, LEGACY_PRIMARY_CARE_DIR)


def get_maps_dir() -> Path:
    return first_existing_path(MAPS_DIR, LEGACY_MAPS_DIR)

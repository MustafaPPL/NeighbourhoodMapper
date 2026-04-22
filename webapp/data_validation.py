from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from webapp.config import AppConfig


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    message: str
    remediation: str


@dataclass(frozen=True)
class SourceStatus:
    label: str
    path: str
    exists: bool
    updated_at: str
    required_for: str


@dataclass(frozen=True)
class ValidationReport:
    blocking_issues: list[ValidationIssue]
    warnings: list[ValidationIssue]
    sources: list[SourceStatus]
    index_lsoa_count: int | None
    asset_count: int | None

    @property
    def can_run_analysis(self) -> bool:
        return not self.blocking_issues


def _timestamp_for(path: Path) -> str:
    if not path.exists():
        return "Missing"
    return pd.Timestamp(path.stat().st_mtime, unit="s").strftime("%Y-%m-%d %H:%M")


def _source_status(label: str, path: Path, required_for: str) -> SourceStatus:
    return SourceStatus(
        label=label,
        path=str(path),
        exists=path.exists(),
        updated_at=_timestamp_for(path),
        required_for=required_for,
    )


def _count_rows(path: Path, **read_csv_kwargs: object) -> int | None:
    if not path.exists():
        return None
    try:
        return len(pd.read_csv(path, **read_csv_kwargs))
    except Exception:
        return None


def validate_config(config: AppConfig) -> ValidationReport:
    blocking_issues: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    local_sources = [
        _source_status("Deprivation index", config.deprivation_csv, "Need model"),
        _source_status("Population", config.population_csv, "Need model"),
        _source_status("65+ population", config.older_people_csv, "Need model"),
        _source_status("Neighbourhood polygons", config.neighbourhoods_path, "ICB annotation"),
        _source_status("Postcode to LSOA lookup", config.postcode_lsoa_lookup_csv, "Host LSOA assignment"),
        _source_status("GP geocoded sites", config.gp_geocoded_csv, "Audit panel"),
        _source_status("Pharmacy source list", config.pharmacy_csv, "Audit panel"),
        _source_status("Pharmacy geocoded sites", config.pharmacy_geocoded_csv, "Audit panel"),
        _source_status("Family hub source list", config.family_hub_csv, "Audit panel"),
        _source_status("Family hub geocoded sites", config.family_hub_geocoded_csv, "Audit panel"),
    ]

    for source in local_sources:
        if not source.exists:
            blocking_issues.append(
                ValidationIssue(
                    severity="error",
                    message=f"Missing required file: {source.label}",
                    remediation=f"Provide the file at `{source.path}` or update the app configuration.",
                )
            )

    if config.lsoa_source == "local_file":
        if config.local_lsoa_path is None or not config.local_lsoa_path.exists():
            blocking_issues.append(
                ValidationIssue(
                    severity="error",
                    message="Local LSOA boundary file is not configured.",
                    remediation=(
                        "Supply a shapefile or GeoPackage containing London LSOA polygons and an LSOA code column, "
                        "or switch the LSOA source to the live ArcGIS service."
                    ),
                )
            )
    else:
        warnings.append(
            ValidationIssue(
                severity="warning",
                message="LSOA boundaries are configured to come from a live ArcGIS service.",
                remediation=(
                    "This is required for polygon joins and centroid distances. For a fully offline workflow, cache "
                    "London LSOA boundaries locally and point the app at that file."
                ),
            )
        )

    if config.postcode_source == "local_lookup":
        if config.postcode_coordinate_lookup_csv is None or not config.postcode_coordinate_lookup_csv.exists():
            blocking_issues.append(
                ValidationIssue(
                    severity="error",
                    message="Local postcode coordinate lookup is not configured.",
                    remediation=(
                        "Provide a postcode lookup with postcode, latitude, and longitude fields, for example ONSPD "
                        "or NSPL, then point the app at that file."
                    ),
                )
            )
    elif config.postcode_source == "postcodes_io":
        warnings.append(
            ValidationIssue(
                severity="warning",
                message="Candidate postcode geocoding is configured to use the live Postcodes.io API.",
                remediation="This external dependency is used only for postcode coordinates and map points.",
            )
        )
    else:
        blocking_issues.append(
            ValidationIssue(
                severity="error",
                message="No postcode geocoding source is configured.",
                remediation=(
                    "The hub-ranking workflow cannot start without postcode coordinates. Configure a local postcode "
                    "coordinate lookup or enable the Postcodes.io API option."
                ),
            )
        )

    if config.local_lsoa_path is not None:
        local_sources.append(_source_status("Local LSOA boundaries", config.local_lsoa_path, "Spatial joins"))
    if config.postcode_coordinate_lookup_csv is not None:
        local_sources.append(
            _source_status(
                "Local postcode coordinate lookup",
                config.postcode_coordinate_lookup_csv,
                "Candidate geocoding",
            )
        )

    index_lsoa_count = _count_rows(config.deprivation_csv, dtype={"LSOA_code": str})
    gp_count = _count_rows(config.gp_geocoded_csv, dtype=str) or 0
    pharmacy_count = _count_rows(config.pharmacy_geocoded_csv, dtype=str) or 0
    family_hub_count = _count_rows(config.family_hub_geocoded_csv, dtype=str) or 0
    asset_count = gp_count + pharmacy_count + family_hub_count

    return ValidationReport(
        blocking_issues=blocking_issues,
        warnings=warnings,
        sources=local_sources,
        index_lsoa_count=index_lsoa_count,
        asset_count=asset_count,
    )

# London ICB Neighbourhood Health Mapping

This repository contains Python scripts for building London neighbourhood health maps and supporting datasets for Integrated Care Boards (`ICBs`).

The main focus is:
- `LSOA`-level weighted priority mapping
- neighbourhood-level asset density / service desert mapping
- hub travel-time analysis
- ICB asset workbook generation

The outputs are intended to support neighbourhood health strategy, place-based planning, access analysis, and service gap identification across London.

## Repository Structure

```text
london_int/
├─ data/
│  ├─ older_people/
│  ├─ primary_care/
│  ├─ core20_lsoa_latest.csv
│  ├─ LSOA Population.csv
│  ├─ london_civic_centres.csv
│  ├─ london_libraries.csv
│  └─ london_nhs_trusts.xlsx
├─ output/
│  ├─ maps/
│  └─ ...
├─ archive/
├─ build_weighted_priority_map.py
├─ build_hub_travel_times.py
├─ build_asset_density_map.py
├─ build_icb_asset_workbooks.py
├─ build_weighted_map_legend.py
└─ project_paths.py
```

## Active Scripts

### `build_weighted_priority_map.py`
Builds the main `LSOA` weighted priority dataset and map for London.

Inputs:
- deprivation data by `LSOA`
- total population by `LSOA`
- `65+` population by `LSOA`
- geocoded GP / pharmacy / family hub data
- neighbourhood shapefile

Outputs:
- `output/weighted_lsoa_priority_scores.csv`
- `output/weighted_lsoa_priority_map.png`
- `output/deprivation_priority_map.png`
- `output/age_65_plus_priority_map.png`
- `output/age_65_plus_density_map.png`
- `output/population_priority_map.png`

### `build_hub_travel_times.py`
Calculates travel times from London `LSOA` centroids to the nearest hubs.

Supports:
- `driving`, `walking`, `cycling` via `OSRM`
- `transit` via `TfL JourneyResults`

Outputs:
- `output/lsoa_hub_travel_times.csv`
- cached API responses under `output/travel_time_cache/`

### `build_asset_density_map.py`
Builds a neighbourhood-level asset density / service desert dataset and map.

Measures:
- GP sites per `10,000` residents
- pharmacies per `10,000` residents
- family hubs per child population

Outputs:
- `output/neighbourhood_asset_density.csv`
- `output/neighbourhood_service_desert_map.png`

### `build_icb_asset_workbooks.py`
Builds ICB-level Excel workbooks for community pharmacies and family hubs.

Outputs:
- `output/community_pharmacy_by_icb.xlsx`
- `output/family_hubs_by_icb.xlsx`

### `build_weighted_map_legend.py`
Builds a standalone legend graphic for the weighted map outputs.

Output:
- `output/weighted_map_legend.png`

## Data Requirements

### Core repo data

`data/`
- `core20_lsoa_latest.csv`
- `LSOA Population.csv`
- `london_civic_centres.csv`
- `london_libraries.csv`
- `london_nhs_trusts.xlsx`

`data/older_people/`
- `65+ Population London LSOA.csv`
- `Combined List - GPs.xlsx`
- `combined_gps_geocoded.csv`
- `Pharmacy List.csv`
- `pharmacy_geocoded.csv`
- `Family Hub Sites.csv`
- `family_hub_geocoded.csv`
- `neighbourhoods_shapefile.shp` plus sidecar files

`data/primary_care/`
- primary care reference files used by older workflows

## Setup

This repo currently assumes a local virtual environment at `.venv`.

Use:

```powershell
.\.venv\Scripts\python.exe --version
```

If the environment needs recreating, install at least:

```text
pandas
geopandas
matplotlib
requests
openpyxl
numpy
```

## Example Commands

### Build weighted priority outputs

```powershell
.\.venv\Scripts\python.exe build_weighted_priority_map.py
```

### Build asset density / service desert outputs

```powershell
.\.venv\Scripts\python.exe build_asset_density_map.py
```

### Build ICB asset workbooks

```powershell
.\.venv\Scripts\python.exe build_icb_asset_workbooks.py
```

### Build weighted map legend

```powershell
.\.venv\Scripts\python.exe build_weighted_map_legend.py
```

### Build hub travel times

Driving example:

```powershell
.\.venv\Scripts\python.exe build_hub_travel_times.py --hub-type gp --hub-type pharmacy --profile driving
```

Transit example:

```powershell
.\.venv\Scripts\python.exe build_hub_travel_times.py --hub-type gp --hub-type pharmacy --profile transit --date 20260421 --time 1000 --time-is Departing --tfl-app-key YOUR_KEY
```

## Notes

- `project_paths.py` is the shared path configuration module for the repo.
- Older exploratory scripts and loose outputs have been moved to `archive/`.
- Some workflows fetch live geographies from `ONS ArcGIS` services, so internet access may be required.
- `build_hub_travel_times.py` uses external routing APIs and is slower for `transit` than for road modes.

## Current Focus

The current active workflow is:

1. Build weighted LSOA need outputs
2. Build neighbourhood asset density / service desert outputs
3. Build hub access / travel-time outputs
4. Produce supporting asset workbooks for ICB use

This gives a practical sequence of:
- `need`
- `provision`
- `access`

for London neighbourhood health planning.

## Web App

The repository now also includes a separate Streamlit application entry point:

- `app.py`
- `webapp/config.py`
- `webapp/data_validation.py`
- `webapp/data_access.py`
- `webapp/analysis.py`

This does not replace `build_weighted_priority_map.py`. The original static mapping workflow still runs independently.

### What the web app does

The web app ranks proposed Neighbourhood Hub locations using:

1. an `LSOA`-level Need Score built from user-selected indices and weights
2. a proximity-weighted Hub Score around each candidate postcode

The app includes three pages:

- `Introduction`
- `Configure Inputs`
- `Outputs`

The `Configure Inputs` page now includes a neighbourhood footprint builder:

- select all London or a specific `ICB`
- optionally filter the neighbourhood list by borough
- select one or more neighbourhoods to focus the analysis
- preview the selected neighbourhood footprint on a live map before running the model

### Current validated data status

The current workspace contains the main need-model inputs:

- deprivation by `LSOA`
- total population by `LSOA`
- `65+` population by `LSOA`
- neighbourhood polygons
- geocoded GP, pharmacy, and family hub asset files

The current workspace now contains a postcode-to-`LSOA` lookup:

- `data/PCD to LSOA.csv`

This is used to assign each candidate postcode to a host `LSOA`.

The workflow still needs postcode coordinates before it can:

- calculate centroid distances
- compute the final Hub Score
- place the candidate hub on the map

Practical options:

- use `data/PCD to LSOA.csv` for host `LSOA` assignment
- and let the app use the live `Postcodes.io` API for postcode coordinates
- or add a second local postcode coordinate lookup such as `ONSPD` / `NSPL`

The app now defaults to:

- `PCD to LSOA.csv` for host `LSOA` assignment
- `Postcodes.io` for postcode coordinates

So the analytical workflow should run in the current workspace, assuming internet access is available for postcode geocoding and live `LSOA` boundaries.

The repo also does not currently include a local London `LSOA` boundary cache. Your existing script already fetches these from a live ArcGIS service, and the app can do the same. For a fully offline workflow, add a local `LSOA` polygon file and point the app at it in the sidebar configuration.

### Install web app dependencies

Install the packages in `requirements.txt`, for example:

```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt
```

### Run the web app

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

### Configure the app

Use the sidebar to configure:

- source file paths
- `LSOA` boundary source:
  - live ArcGIS service
  - local file
- postcode-to-`LSOA` lookup file
- postcode coordinate source:
  - local lookup file
  - `Postcodes.io`

### Web app analytical method

For each selected `LSOA`, the app:

- standardises each selected index using min-max scaling within the selected geography
- applies the user-defined weights
- calculates:

`NeedScore = sum(standardised index x weight fraction)`

For each candidate postcode, the app:

1. geocodes the postcode to get coordinates
2. assigns it to a host `LSOA` using the postcode-to-`LSOA` lookup
3. calculates point-to-centroid distances to all `LSOAs`
4. calculates:
   - host `LSOA` Need Score
   - mean Need Score within `500m`
   - mean Need Score between `500m` and `2km`
5. ranks candidates using:

`HubScore = (0.60 x host) + (0.25 x mean 0-500m) + (0.15 x mean 500m-2km)`

# London Neighbourhood Hub Decision Explorer — Logic Summary

## Purpose

The app ranks candidate Neighbourhood Hub locations across London by estimating how much nearby population need each site would serve. It uses LSOA-level need data as its analytical base and applies a proximity-weighted scoring model around each candidate postcode.

---

## Data Inputs

| Input | Source | Used for |
|---|---|---|
| Deprivation CSV | Local file (`core20_lsoa_latest.csv`) | IMD decile per LSOA |
| Population CSV | Local file (`LSOA Population.csv`) | Total resident population per LSOA |
| 65+ Population CSV | Local file | Older people count per LSOA |
| Neighbourhood polygons | Shapefile (`neighbourhoods_shapefile.shp`) | Assigning LSOAs to named neighbourhoods |
| LSOA boundaries | Live ArcGIS service or local file | Spatial footprint of each LSOA |
| Postcode-to-LSOA lookup | Local CSV | Mapping candidate postcodes to their host LSOA |
| Postcode coordinates | Postcodes.io API or local lookup CSV | Geocoding candidate hub postcodes |

---

## Step 1 — Scope Filtering

The user selects either **All London** or a **specific ICB** (NCL, NEL, NWL, SEL, or SWL). When a specific ICB is selected, LSOAs are filtered by their `ICB` attribute before any scoring takes place. Optionally, the user can further narrow the scope to specific named neighbourhoods.

---

## Step 2 — LSOA-to-Neighbourhood Assignment

Each LSOA is assigned to a neighbourhood, borough, and ICB via a **spatial join** on LSOA centroids:

1. LSOA polygon centroids are computed in British National Grid (EPSG:27700).
2. Centroids are spatially joined (`within`) against the neighbourhood polygons shapefile.
3. Where one centroid falls inside multiple neighbourhood polygons, the first match is used.
4. LSOAs whose centroid does not fall within any neighbourhood polygon receive null values for `nghbrhd`, `borough`, and `ICB` and are excluded from scoped analysis.

---

## Step 3 — Need Score Calculation

For each LSOA in the selected scope, a **Need Score** is calculated from user-selected indices. Up to four indices are available:

| Index | Derivation |
|---|---|
| Deprivation | `11 − IMD_decile` (inverted so higher = more deprived; valid range 1–10 becomes 1–10 inverted) |
| Population | Total resident population |
| 65+ population | Count of residents aged 65 and over |
| 65+ proportion | 65+ count ÷ total population (clamped to 0–1) |

**For each selected index:**

1. The raw values are **min-max scaled** across the in-scope LSOAs only (not all London), so the lowest-need LSOA scores 0 and the highest scores 1.
2. The scaled value is multiplied by the user-defined **weight / 100**.

**Need Score** = sum of all weighted scaled indices. This is then multiplied by 100 and rounded to 2 decimal places (`need_score_pct`) for display. Weights must sum to exactly 100 before the analysis can run.

---

## Step 4 — Candidate Postcode Geocoding

Each candidate postcode is resolved to a latitude/longitude using one of two configured sources:

- **Postcodes.io API** — live lookup via `GET /postcodes/{postcode}`. Any postcode returning a non-200 response or missing coordinates is flagged as invalid.
- **Local coordinate lookup CSV** — postcode strings are normalised (uppercased, spaces stripped) and matched against the file. Unmatched postcodes are flagged as unresolved.

Each geocoded candidate is then matched to its **host LSOA** using the postcode-to-LSOA lookup CSV (same normalisation applied). Candidates whose host LSOA is not in the in-scope need scores are flagged as unresolved and excluded from ranking.

---

## Step 5 — Hub Score Calculation

For each valid candidate, a **Hub Score** is calculated using a **proximity-weighted demand model**. All geometry is projected to British National Grid for distance calculations.

The LSOA centroids of the scored scope are used as demand points. For each candidate:

| Component | Definition | Weight |
|---|---|---|
| Host LSOA need | Need Score of the LSOA containing the candidate postcode | **60%** |
| Local mean need | Mean Need Score of all other LSOA centroids within **500 m** | **25%** |
| Wider mean need | Mean Need Score of all LSOA centroids **500 m – 2 km** away | **15%** |

```
Hub Score = 0.60 × host_need + 0.25 × mean_need_0–500m + 0.15 × mean_need_500m–2km
```

If the host LSOA has no valid Need Score, the Hub Score is null and the candidate is excluded from ranking. Hub Scores are multiplied by 100 and rounded to 2 decimal places for display. Candidates are ranked in descending Hub Score order, with host Need Score as the tiebreaker.

---

## Key Assumptions and Limitations

- **Centroid-based proximity** — distances are measured from LSOA centroids, not from population-weighted points within each LSOA. In large rural or irregular LSOAs this may under- or over-estimate true proximity.
- **Min-max scaling is scope-relative** — changing the selected geography (e.g. switching from All London to a single ICB) will shift all scaled values, so scores are not comparable across different runs with different scopes.
- **Weights must sum to 100** — any deviation prevents the analysis from running. There is no partial weighting or normalisation fallback.
- **Single LSOA host assignment** — a candidate postcode is assigned to exactly one host LSOA. If the postcode sits on a boundary the first match in the lookup table wins.
- **No estate or accessibility checks** — the Hub Score reflects population need only. It does not account for transport links, building availability, clinical suitability, or existing service catchments.
- **Outputs are decision-support only** — they do not replace local service planning, estate checks, or clinical judgement.

---

## QOF Disease Prevalence Indices

Four optional disease prevalence indices can be included in the Need Model:

| Index | QOF Register |
|---|---|
| Cardiovascular disease (CHD) | Coronary Heart Disease register |
| COPD | Chronic Obstructive Pulmonary Disease register |
| Diabetes | Diabetes Mellitus (DM) register |
| Depression | Depression (DEP) register |

**Data source:** NHS Quality and Outcomes Framework (QOF) 2024-25, practice-level register size data.

**Attribution method:** For each LSOA, the top-5 nearest GP practices are identified by straight-line distance from the LSOA centroid (no hard cutoff, so every LSOA receives a non-null value). Each practice is weighted by `list_size / distance_km²`. The LSOA-level prevalence is the weighted mean of the practice-level crude prevalence rates (%) across the top-5 practices.

**Caveat:** QOF prevalence is *recorded* prevalence on the GP register, not epidemiological prevalence. It reflects diagnostic activity and registration patterns as much as underlying disease burden. Use alongside — not instead of — deprivation and population indices.

**Prepared by:** `scripts/analysis/build_qof_lsoa.py` → `data/cache/qof_lsoa_2024-25.csv`

---

## Ethnicity Equity Indices

Five optional ethnicity proportion fields can be included in the Need Model:

| Field | ONS TS021 group mapping |
|---|---|
| `pct_asian_residents` | Asian, Asian British or Asian Welsh |
| `pct_black_residents` | Black, Black British, Black Welsh, Caribbean or African |
| `pct_mixed_residents` | Mixed or Multiple ethnic groups |
| `pct_other_ethnic_group_residents` | Other ethnic group |
| `pct_white_other_residents` | White: Other White (excludes British, Irish, and Gypsy or Irish Traveller) |

**Data source:** ONS Census 2021, table TS021 (*Ethnic group*), downloaded from Nomis (reference C2021TS021). Each proportion is the count in that group divided by the total usual resident population of the LSOA, clamped to [0, 1].

**Important caveat:** These fields are an **equity lens**, not a deprivation substitute. They indicate the share of residents from specific communities and should only be included when there is a specific planning question about equitable access for those communities. Selecting these indices does not imply that any ethnic group has inherently higher need.

**Prepared by:** `scripts/analysis/build_ethnicity_lsoa.py` → `data/cache/ethnicity_lsoa_2021.csv`

---

## Travel-Time Catchments

When a routed travel mode is selected, the straight-line catchment radius is replaced by a pre-computed travel-time matrix. Two modes are available:

| Mode | Routing engine | Notes |
|---|---|---|
| Walking | OSRM (Open Source Routing Machine) | Public endpoint `router.project-osrm.org`, foot profile |
| Public transport | R5 (Conveyal) with London GTFS | Departure: Tuesday 10:00 am (representative off-peak AM) |

**GTFS feeds used for transit:** TfL Bus GTFS, TfL Tube/Rail GTFS, Elizabeth line, and National Rail feeds covering Greater London.

**Scoring formula:** Each LSOA in the catchment receives a time-decay weight:

```
weight = max(0, 1 − travel_time_minutes / 30)
```

LSOAs with travel time > 30 minutes receive weight 0 and are excluded from the catchment mean. This replaces the straight-line distance-decay formula used in the default mode.

**Band thresholds (map colouring):**

| Band | Travel time | Map colour |
|---|---|---|
| Inner | 0–10 min | Green |
| Middle | 10–20 min | Amber |
| Outer | 20–30 min | Red |
| Beyond | > 30 min or no route | Grey |

Band colours are assigned relative to the top-ranked candidate hub's host LSOA.

**Prepared by:** `scripts/analysis/build_travel_time_matrix.py --mode walking|transit`

---

## Estate Availability Flags

When an ERIC geocoded sites file is configured, each candidate hub location is checked for proximity to NHS estate.

**Data source:** Estates Returns Information Collection (ERIC) 2024/25, NHS England. Covers NHS trust-owned sites across England; filtered to London trusts by organisation code prefix and trust name.

**Geocoding method:** Site postcodes are geocoded via the Postcodes.io API. If the ERIC CSV includes non-null latitude/longitude columns, those are used directly without an API call. Results are cached to avoid re-geocoding on repeated runs.

**Proximity calculation:** Distances are computed in British National Grid (EPSG:27700). The default search radius is **1 km** (configurable via the Settings sidebar, range 500 m – 2 km). A candidate is flagged as having nearby NHS estate if at least one site centroid falls within the search radius.

**Important:** Estate proximity flags are **informational only**. They do not affect the numeric Hub Score. A high Hub Score with nearby estate is a strong candidate for further feasibility assessment; a high score without estate nearby may indicate a greenfield opportunity.

# PRD: Neighbourhood Hub Ranker — Four Enhancement Features

## Problem Statement

ICB analysts using the Neighbourhood Hub Ranker currently rank candidate hub locations using only straight-line distance catchments and three deprivation-based indices (IMD decile, total population, 65+ population). This produces recommendations that miss clinical need patterns, community equity considerations, how patients actually travel across the road network and public transport, and whether suitable NHS estate exists near high-need areas. As a result, ICBs cannot use the tool to answer questions such as: "Is this candidate site also near communities with high cardiovascular disease burden?", "Can most residents reach it within 20 minutes by bus?", or "Is there underutilised NHS space nearby that could host the hub?"

## Solution

Add four optional enhancement layers to the existing Hub Ranker, each independently selectable and non-breaking to the base workflow. The existing straight-line scoring remains the default. All new indices participate in the existing min-max scaling and weighting framework already used for deprivation, population, and 65+ indices.

**Delivery order:** QOF disease prevalence → Ethnicity indices → Travel-time catchments → Estate availability flags

## User Stories

### QOF Disease Prevalence

1. As an ICB analyst, I want to add a cardiovascular disease prevalence index to the Need Model, so that hub recommendations reflect areas with high recorded CHD burden.
2. As an ICB analyst, I want to add a respiratory disease prevalence index, so that I can prioritise areas with high COPD prevalence.
3. As an ICB analyst, I want to add a diabetes/metabolic prevalence index, so that hub placements can reflect areas with high diabetes burden.
4. As an ICB analyst, I want to add a mental health prevalence index, so that hub placements can reflect areas with high recorded depression prevalence.
5. As an ICB analyst, I want each QOF index to be optional and off by default, so that I can run a standard analysis without clinical need layers if not required.
6. As an ICB analyst, I want to see which QOF year and attribution method were used in each run, so that I can justify outputs to commissioners.
7. As an ICB analyst, I want the tool to clearly explain that QOF reflects recorded prevalence rather than true epidemiological prevalence, so that I do not overstate the clinical evidence.
8. As an ICB analyst, I want the QOF indices to participate in the existing weighting sliders, so that I can balance clinical need against deprivation and population factors.
9. As an ICB analyst, I want the app to work normally if no QOF file is configured, so that colleagues without the data file are not blocked.
10. As an ICB analyst, I want to see a clear message when QOF data is not configured, so that I know the feature exists and how to enable it.

### Ethnicity Indices

11. As an ICB analyst, I want to add a percentage Asian residents index to the Need Model, so that I can identify LSOAs where South Asian communities may face language or cultural access barriers.
12. As an ICB analyst, I want to add a percentage Black residents index, so that I can identify LSOAs with significant Black community populations when planning equity-focused hub locations.
13. As an ICB analyst, I want to add a percentage Mixed ethnicity residents index, so that I can include mixed-heritage communities in equity planning.
14. As an ICB analyst, I want to add a percentage Other ethnic group residents index, so that communities not captured in the larger categories are included.
15. As an ICB analyst, I want to add a percentage White Other residents index (non-British White), so that I can identify areas with significant migrant or non-English-speaking White communities who may face language access barriers.
16. As an ICB analyst, I want to explicitly choose which ethnicity field to include, rather than having a single composite ethnicity score applied automatically, so that I remain in control of the equity framing.
17. As an ICB analyst, I want methodology text to explain that ethnicity fields are an equity lens and not a deprivation substitute, so that outputs are not misread or misused.
18. As an ICB analyst, I want all ethnicity indices to be off by default, so that analyses without an equity lens are not inadvertently affected.
19. As an ICB analyst, I want to see the Census 2021 source year displayed for each ethnicity field, so that stakeholders understand the data vintage.
20. As an ICB analyst, I want the app to work normally if no ethnicity file is configured, so that colleagues without the file are not blocked.

### Travel-Time Catchments

21. As an ICB analyst, I want to switch from straight-line radius to walking travel time, so that hub catchments reflect realistic pedestrian access rather than as-the-crow-flies distance.
22. As an ICB analyst, I want to switch from straight-line radius to public transport travel time, so that hub catchments reflect how patients actually travel by bus and rail.
23. As an ICB analyst, I want the straight-line radius to remain available as a fallback, so that I can run legacy-compatible analyses when travel-time data is not available.
24. As an ICB analyst, I want LSOAs to be scored by travel-time decay rather than distance decay when a routed mode is selected, so that scoring is consistent with the access model.
25. As an ICB analyst, I want the scoring decay to be continuous (proportional to time) rather than step-function by band, so that small differences in travel time produce proportionate differences in score.
26. As an ICB analyst, I want the output map to shade LSOAs by travel-time band (0–10 min, 10–20 min, 20–30 min) when a routed mode is selected, so that I can visually understand the catchment structure.
27. As an ICB analyst, I want transit travel times to reflect an off-peak Tuesday 10am departure, so that I understand the assumption and can explain it to stakeholders.
28. As an ICB analyst, I want travel-time results to be pre-computed and cached, so that analyses run quickly without hitting external APIs during a live session.
29. As an ICB analyst, I want manual candidate postcodes to also benefit from accurate travel-time lookup, so that manually specified locations are not treated as second-class candidates.
30. As an ICB analyst, I want the routing provider and mode to be recorded in the run metadata, so that outputs are reproducible and auditable.
31. As an ICB analyst, I want the app to fall back to straight-line mode if the travel-time cache files are absent, so that the base workflow is never broken.

### Estate Availability Flags

32. As an ICB analyst, I want to see whether NHS estate exists within 1 km of each top-ranked candidate, so that I can quickly assess feasibility alongside need scores.
33. As an ICB analyst, I want to see the count of NHS estate sites within the search radius for each candidate, so that I understand how many options are nearby.
34. As an ICB analyst, I want to see the name and distance to the nearest NHS estate site for each candidate, so that I can investigate specific sites.
35. As an ICB analyst, I want to configure the estate proximity search radius (500 m to 2 km), so that I can adjust the definition of "nearby" to suit local geography.
36. As an ICB analyst, I want estate proximity flags to appear in the output table, map tooltip, and CSV export, so that the information is accessible at every point of the workflow.
37. As an ICB analyst, I want estate flags to be informational only and not affect the hub score, so that need-based ranking is not distorted by estate availability.
38. As an ICB analyst, I want the estate dataset name and year to appear in run metadata, so that I know which version of ERIC was used.
39. As an ICB analyst, I want the app to work normally if no estate file is configured, so that the feature is truly optional.

### Cross-Cutting

40. As an ICB analyst, I want to download a metadata JSON file alongside my CSV export, so that anyone receiving my outputs can see exactly which data sources, years, attribution methods, and modes were active in that run.
41. As an ICB analyst, I want enhancement features that are not yet configured to appear greyed out with a tooltip explaining what file to add, so that I can discover capabilities and know how to unlock them.
42. As an ICB analyst, I want the base hub-scoring logic to remain unchanged unless I explicitly select a new travel or access mode, so that existing workflows produce identical results.

## Implementation Decisions

### Delivery and Architecture

- Features are built and shipped sequentially: QOF → Ethnicity → Travel Time → Estate. Each is independently deployable and non-breaking.
- All new indices follow the existing `INDEX_DEFINITIONS` pattern in the analysis module: a loader function produces an LSOA-level column, which is registered in the definitions dict, and the UI checkbox and weight slider are generated automatically.
- Enhancement data files are split into two locations: raw downloaded source files in `data/`, and script-generated derived/cached files in `data/cache/`. The `data/cache/` directory is mounted as a Docker volume in deployment and excluded from the Docker image.
- Each analysis run writes a companion `_metadata.json` file alongside the CSV export, recording which enhancement layers were active, their source datasets, years, attribution methods, and routing assumptions.
- When an enhancement data file is absent, the corresponding UI control is rendered greyed out with a tooltip: "X data not configured — add a path in Settings to enable." The app never errors due to a missing optional file.
- Methodology for all four features lives in `docs/METHODOLOGY.md`, one section per feature, added as each feature is built.

### QOF Disease Prevalence

- Four disease indices for MVP: cardiovascular (CHD register), respiratory (COPD register), metabolic (diabetes register), mental health (depression register). One canonical register per theme.
- QOF is published at GP-practice level. Attribution to LSOA uses weighted allocation: for each LSOA, identify the 5 nearest GP practices by centroid distance, then compute a weighted prevalence using `weight = list_size / distance²`. No hard radius cutoff — the inverse-square decay naturally limits distant practice influence while guaranteeing every LSOA receives a value.
- GP site coordinates come from the existing geocoded GP file already in the repo. GP list size data is provided separately by the user (reminder: user to supply list size file when QOF ingestion is being built).
- QOF year is managed at script level: the ingestion script is parameterised by year and writes a year-stamped cache file. No in-app year switcher in MVP.
- Methodology text must note that QOF records registered prevalence, not true epidemiological prevalence.

### Ethnicity Indices

- Five transparent derived fields: `pct_asian_residents`, `pct_black_residents`, `pct_mixed_residents`, `pct_other_ethnic_group_residents`, `pct_white_other_residents`. No composite diversity index in MVP.
- `pct_white_other` is included as a proxy for migrant or non-English-speaking White communities facing potential language access barriers.
- Source: ONS TS021 Census 2021 dataset, downloaded as a static CSV from Nomis (reference: `C2021TS021`). No live API call — Census 2021 data is static (last updated March 2023).
- Methodology text must frame these explicitly as an equity lens, not a deprivation proxy or automatic need score.

### Travel-Time Catchments

- Pre-computed full LSOA × LSOA travel-time matrix. At runtime, any candidate (suggested or manual) is snapped to its host LSOA centroid and travel times to all other LSOAs are read from the cached table. Instant lookups; no live API calls during analysis.
- **Walking matrix:** OSRM batch table endpoint — computes the full ~5,000 × 5,000 LSOA centroid matrix in a single API call. Output cached as parquet.
- **Transit matrix:** R5 (Conveyal open-source routing engine) with London GTFS feeds (freely available from TfL) and OSM pedestrian network. Computes the full LSOA × LSOA transit matrix in approximately 30 minutes to 2 hours as a one-time batch job. Output cached as parquet. The batch job is Dockerised for reproducibility.
- Fixed transit departure assumption: **Tuesday 10:00 am** (off-peak weekday). This is the standard NHS accessibility modelling departure time and must be documented in methodology.
- **Catchment scoring:** when travel-time mode is active, the existing distance decay formula is replaced by a continuous time decay: `weight = 1 − (travel_time_minutes / 30)`. LSOAs beyond 30 minutes receive zero weight. This is structurally identical to the existing linear distance decay and requires no new parameters.
- **Map visualisation:** LSOAs are shaded by travel-time band (green = 0–10 min, amber = 10–20 min, red = 20–30 min) when a routed mode is selected. This replaces the current catchment circle overlay. Isochrone polygon rendering is deferred to Phase 2.
- Fixed band thresholds (0–10, 10–20, 20–30 min) are hardcoded for MVP. Bands are used only for map colour coding; scoring uses continuous decay. Configurable thresholds are deferred to Phase 2.
- If travel-time cache files are absent, the app falls back to straight-line mode automatically.

### Estate Availability Flags

- MVP is proximity-only: for each ranked candidate, compute the count of NHS estate sites within the search radius, the nearest site name, and the distance to the nearest site. No underutilised or void proxy in MVP — this is deferred until the ERIC data dictionary has been inspected and a defensible proxy agreed.
- ERIC 2024/25 site data CSV must be downloaded. The implementation assumes geocoding from postcode via postcodes.io (the same geocoder the app already uses). Native coordinates in ERIC are a bonus if present.
- Default search radius: **1 km**. Configurable via `AppConfig` from 500 m to 2 km.
- Estate flags appear in the output candidate table, map popup/tooltip, and CSV export. They do not affect the numeric hub score.

## Testing Decisions

A good test asserts observable output for a given input — it does not inspect internal state or implementation steps. Tests should be runnable without external API access (mock or fixture data is acceptable for network-dependent functions).

**Modules to test:**

- **QOF attribution logic:** Given a set of LSOA centroids, practice locations, list sizes, and disease register counts, assert that the weighted LSOA prevalence values are computed correctly. Verify that every LSOA receives a value (no nulls), that closer practices with larger list sizes dominate, and that the inverse-square weighting produces the expected output for known inputs.

- **Ethnicity proportion derivation:** Given raw ONS TS021 count data for a set of LSOAs, assert that the five derived proportion columns sum to a value ≤ 1 per LSOA, that no column contains negative values, and that the correct ONS group codes map to the correct output column names.

- **Travel-time scoring:** Given a travel-time lookup table and a candidate LSOA, assert that the continuous decay weighting (`1 − t/30`) is applied correctly, that LSOAs beyond 30 minutes receive zero weight, and that the resulting catchment need score is numerically identical to the straight-line equivalent when all travel times equal their distance-equivalent (regression test for parity).

- **Travel-time band assignment:** Given travel times for a set of LSOAs, assert that each LSOA is assigned to exactly one band, that band boundaries are correctly applied (inclusive/exclusive at 10 and 20 minutes), and that the map colour assignment matches the band.

- **Graceful failure:** For each of the four enhancement features, assert that the app initialises and runs a complete straight-line analysis successfully when the relevant cache file is absent. Assert that the corresponding UI control is rendered in a disabled state.

- **Estate proximity calculation:** Given a candidate location and a set of geocoded estate sites, assert that the count, nearest site name, and distance returned are correct for known inputs.

## Out of Scope

- **Isochrone polygon rendering** on the map — deferred to Phase 2. MVP uses LSOA polygon shading by band.
- **Configurable travel-time band thresholds** — fixed at 0–10, 10–20, 20–30 min for MVP.
- **Peak-hour transit table** — only off-peak (Tuesday 10am) in MVP. A second table could be added in Phase 2 if ICBs request it.
- **Driving travel time** — listed in the requirements as optional later. Not in MVP.
- **Underutilised estate flags** — deferred until ERIC data dictionary has been reviewed and a proxy agreed.
- **QOF frailty index** — no standard QOF frailty register exists. Deferred pending clinical definition.
- **In-app QOF year switcher** — year management is script-level only in MVP.
- **Ethnicity diversity index** — deferred; transparent proportions are sufficient for MVP governance conversations.
- **Multi-provider transit routing** (e.g. Traveline, OpenRouteService) — MVP uses R5 with London GTFS only.
- **Changing the base hub score formula** — existing deprivation/population/65+ scoring is unchanged unless the user selects a new travel mode.

## Further Notes

- The GP list size data needed for QOF attribution is held by the user and must be provided when the QOF ingestion script is being built. The ingestion script should validate that the list size file contains a Practice Code column joinable to the QOF and GP geocoded files.
- R5 (Conveyal) requires Java. The batch job should be wrapped in a Dockerfile so it can be run reproducibly without requiring a local Java installation. London GTFS feeds should be documented (bus, Tube, Elizabeth line, national rail) with download links recorded in the batch script or its accompanying README.
- The OSRM instance used for walking should be the public `router.project-osrm.org` endpoint (already used in the existing travel-time script), with a note that a self-hosted instance should be considered if request volumes increase.
- The `data/cache/` volume mount means that after a fresh Docker deployment the operator must mount a pre-populated cache directory. Deployment documentation should describe which cache files are required for each feature and how to regenerate them.
- ERIC data filtering: after download, the site CSV must be filtered to London NHS trusts before geocoding. Trust names or organisation codes should be used for this filter, not postcode alone, to avoid edge cases at the London boundary.

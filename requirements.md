# Neighbourhood Hub Ranker: Additional Requirements

## Purpose

This document turns four shortlisted enhancement ideas into implementation-ready requirements for the current London `ICB` Neighbourhood Hub Ranker app.

Before going into detailed design or implementation, the receiving `LLM` should first provide a time estimate for the work.

The current app:

- is a Streamlit app with the main UI in `app.py`
- calculates `LSOA`-level Need Scores in `webapp/analysis.py`
- ranks candidate hub locations using host-`LSOA` need plus a straight-line centroid catchment
- validates local inputs in `webapp/config.py` and `webapp/data_validation.py`
- already contains a separate travel-time script in `scripts/analysis/build_hub_travel_times.py` using `OSRM` for road modes and `TfL JourneyResults` for transit

## Delivery Principles

- Keep all new features optional and non-breaking.
- Preserve the current straight-line workflow as a fallback or legacy mode.
- Record provenance for every new data layer in metadata, outputs, and methodology text.
- Prefer open/public data and reusable local caches over hard dependencies on live APIs.
- Surface caveats clearly where a dataset is a proxy rather than a direct measure.
- Do not silently convert sensitive demographic variables into a default "need" score without explicit user choice.

## Required First Step: Estimation Before Design

Before breaking down the implementation in detail, the receiving `LLM` should first return an estimate covering:

1. estimated effort per requirement
2. estimated total effort
3. the main assumptions behind each estimate
4. the main uncertainties or blockers that could change the estimate
5. a recommended delivery order
6. a distinction between:
   - `MVP effort`
   - `full implementation effort`

The estimate should be expressed in:

- engineer-days as the primary unit
- an optional calendar-time range assuming one engineer working part-time or full-time

The estimate should explicitly call out that:

- travel time has the biggest technical and performance risk
- `QOF` looks simple at first but `LSOA` attribution is the main methodological dependency
- estate flags depend on how usable the `ERIC` site fields are in practice
- ethnicity is low technical effort but needs careful framing and governance

Only after providing that estimate should the `LLM` move on to detailed solution design or implementation planning.

## Summary

| Feature | User priority | Likely effort | Main challenge | Notes |
|---|---|---:|---|---|
| Travel Time Catchments | High impact | Medium | Replacing straight-line catchments with routed access logic and map output | Easier than greenfield because the repo already has `OSRM` and `TfL` travel-time code patterns |
| QOF Disease Prevalence Data | High impact | Low to medium | Mapping practice-level QOF data to `LSOA` in a defensible way | Data acquisition is easy; small-area attribution is the non-trivial part |
| Estate Availability Flags | Medium impact | Medium | Deriving a useful "available / underutilised" signal from `ERIC` site-level data | Existing estates workbook code and archived void-centre data reduce effort |
| Ethnicity Index | Medium impact | Low technical / medium governance | Defining an ethical and explicit scoring approach | Technically easy if treated as an optional equity lens rather than a default deficit score |

## Cross-Cutting Implementation Requirements

Any implementation of the four features should also do the following:

1. Add new file paths and/or API settings through the existing config and validation pattern.
2. Cache any expensive API calls or geocoding outputs locally.
3. Expose source year, dataset name, and update date in the analysis metadata.
4. Keep all new indices optional in the UI.
5. Update output tables, map tooltips, and audit metadata so users can see which enhancement layers were active in a run.
6. Fail gracefully when a non-core enhancement source is missing.
7. Avoid changing the existing base hub-scoring logic unless the user explicitly selects a new travel/access mode.

## Requirement 1: Travel Time Catchments

### Goal

Replace or supplement the current straight-line catchment radius with walking and public-transport accessibility so recommendations better reflect how patients actually travel.

### Current state

- Current hub ranking uses straight-line centroid distances and a single radius catchment in `webapp/analysis.py`.
- The repo already contains `scripts/analysis/build_hub_travel_times.py`, which uses:
  - `OSRM` for `driving`, `walking`, and `cycling`
  - `TfL JourneyResults` for `transit`

This means the app already has useful routing patterns, caching approaches, and London-specific transit logic that can be reused.

### Functional requirements

1. Add a new access model option to the app:
   - `Straight-line radius` (existing behavior)
   - `Walking travel time`
   - `Public transport travel time`
   - optional later: `Driving travel time`
2. Allow the user to define travel-time bands instead of only metres, for example:
   - inner band: `0-10` minutes
   - middle band: `10-20` minutes
   - outer band: `20-30` minutes
3. Score candidate hubs using travel-time-based `LSOA` inclusion rather than Euclidean radius when a routed mode is selected.
4. Show routed catchments on the output map. If true polygon isochrones are too heavy for the first iteration, an acceptable MVP is:
   - score by routed travel-time bands to `LSOA` centroids
   - render centroid-band membership or simplified travel polygons
5. Keep the current straight-line radius available as fallback if routing data is unavailable.
6. Store routing metadata per run:
   - mode
   - provider
   - request date/time
   - departure/arrival assumption for transit
   - cache status
7. Cache responses locally so repeated analyses do not repeatedly hit external APIs.

### Data / provider options

#### Best near-term option for the current London app

- Reuse the repo's existing `OSRM` and `TfL` logic.
- `TfL` is especially attractive for London-only public transport because it is already aligned to the app's geography.

#### Alternative / broader options

- `OpenRouteService` is a strong open-source-friendly option for isochrones and route matrices.
- `Traveline` can support wider public-transport coverage beyond London.

### Important source notes

- `TfL Unified API` requires registration for an application ID and key, and exposes a `Journey` API.
- `OpenRouteService` free plans have rate and volume limits. Its public limits include `500` isochrones/day on the standard plan and `2,500`/day on the collaborative plan; on-premise deployment removes public API limits.
- `Traveline` states that the Traveline National Dataset is updated overnight Monday to Thursday and can be downloaded for free once subscribed, but it also notes some services may be chargeable.

### Complexity / ease

- Overall effort remains `medium`.
- It is easier than a greenfield build because the repo already has travel-time code patterns and caching logic.
- The hardest parts are:
  - interactive performance
  - transit variability by departure time
  - API limits / resilience
  - moving from circle-based mapping to travel-time-based catchments

### Recommended implementation approach

1. MVP:
   - reuse `OSRM` for walking
   - reuse `TfL JourneyResults` for London transit
   - score by travel time to `LSOA` centroids
   - keep the current straight-line model as fallback
2. Phase 2:
   - add full isochrone polygon rendering
   - abstract routing providers so the app is not locked to `TfL`
   - evaluate `OpenRouteService` or self-hosted routing for scale

### Acceptance criteria

- Users can run a hub analysis using `walking` or `public transport` access instead of a metre radius.
- Candidate scoring changes when routed modes are selected.
- Output metadata clearly states which routing mode and provider were used.
- The app still works without the enhancement enabled.
- Cached travel results are reused on repeat runs.

## Requirement 2: QOF Disease Prevalence Data

### Goal

Add `QOF` disease prevalence as optional scoring indices so users can plan hubs around specific clinical burdens such as cardiovascular disease or respiratory disease.

### Current state

- The app currently scores need using deprivation, total population, and older-people measures.
- There is no clinical-need layer in the scoring model.

### Functional requirements

1. Add one or more optional `QOF`-derived indices into the Need Model selector.
2. Allow users to select disease-specific indices, for example:
   - cardiovascular
   - respiratory
   - diabetes / metabolic
   - mental health
3. If "frailty" is requested, do not assume it exists as a single standard `QOF` register.
   - Either define a documented proxy with clinical sign-off
   - Or leave frailty out of MVP and document why
4. Map `QOF` practice-level prevalence to `LSOA` so the layer can be used in the existing `LSOA`-level scoring framework.
5. Make the attribution method explicit in metadata and methodology.
6. Keep the feature optional and off by default.
7. Allow refresh by reporting year where possible.

### Preferred attribution approach

`QOF` is published at GP-practice level, not directly at `LSOA`.

The implementation should therefore use one explicit and documented attribution method:

- Preferred:
  - weighted allocation from nearby GP practices to each `LSOA`, using practice list size and inverse distance from `LSOA` centroid to GP site
- Acceptable MVP:
  - nearest-practice assignment per `LSOA`

The chosen method must be visible to the user because this is the main methodological assumption in the feature.

### Data sources

- Official `QOF 2024-25` publication from NHS England / former NHS Digital
- GP-practice-level files published under the `Resources` section
- Raw CSV bundle for indicator definitions and mappings
- Existing repo GP geocoded site file can help with practice location matching

### Important source notes

- NHS England published `QOF 2024-25` on `28 August 2025`.
- The publication includes GP-practice-level files and a raw CSV zip.
- GP practices are already mapped in the publication to `PCNs`, `Sub ICB Locations`, `ICBs`, and regions.
- NHS England explicitly states that `QOF` registers underpin quality indicators and "do not necessarily equate" to epidemiological prevalence.
- `QOF` is aggregate practice data; patient-level comorbidity analysis is not possible from the published files.

### Complexity / ease

- Data acquisition is `low effort`.
- Small-area modelling is `low to medium effort`, depending on attribution method.
- This is not quite as trivial as "drop in another `LSOA` CSV", because `QOF` is practice-based and must be translated into the app's `LSOA` scoring model.

### Recommended implementation approach

1. Build an ingestion layer for a chosen `QOF` year.
2. Create a clean set of derived disease indices.
3. Join to the existing GP practice geocoded dataset.
4. Produce an `LSOA`-level derived `QOF` file cached locally.
5. Add those new columns to the existing index-definition pattern in `webapp/analysis.py`.

### Acceptance criteria

- Users can select at least one `QOF`-derived disease layer in the Need Model UI.
- The layer is optional and participates in the existing weighting workflow.
- The app can explain which `QOF` year and attribution method were used.
- The methodology notes explain that `QOF` is recorded prevalence, not a perfect epidemiological measure.

## Requirement 3: Estate Availability Flags

### Goal

Cross-reference top-ranked candidate locations against nearby NHS estate sites so the outputs better reflect where a hub could realistically go, not just where need is highest.

### Current state

- The app currently ranks need only.
- It does not incorporate site availability, void buildings, or estate capacity into candidate outputs.
- The repo already contains:
  - an estates workbook script: `scripts/analysis/build_icb_estates_workbooks.py`
  - archived void-centre data: `archive/voids/voids_with_geodata.csv`

### Functional requirements

1. Add a non-scoring estate overlay layer to candidate outputs.
2. For each suggested or manual candidate, calculate:
   - `nearby_nhs_estate_flag`
   - count of NHS estate sites within a configurable threshold
   - nearest estate site name
   - distance to nearest estate site
   - source dataset and year
3. If feasible from the chosen fields, also derive:
   - `underutilised_estate_flag`
   - `void_or_low_use_proxy`
4. Show estate flags in:
   - output table
   - map popup / tooltip
   - exported results
5. Keep estate intelligence supplementary in the first version.
   - It should inform feasibility
   - It should not change the numeric hub score unless explicitly requested later
6. Allow configurable search distance, for example `500m`, `1km`, `2km`.

### Data sources

- `ERIC 2024/25` site data CSV
- `ERIC 2024/25` data definitions workbook
- optionally the repo's existing local void dataset as a secondary enrichment source

### Important source notes

- `ERIC` is the `Estates Returns Information Collection`.
- NHS England states the collection is mandatory for all NHS trusts including ambulance trusts.
- NHS England also states that data at trust, site, and `PFI` scheme level are published.
- The `ERIC 2024/25` publication includes:
  - data definitions
  - trust data CSV
  - site data CSV
  - `PFI` data CSV
- NHS England also warns that some fields should be treated cautiously where they are marked unreliable or experimental.

### Complexity / ease

- Overall effort is `medium`.
- The likely hard parts are:
  - geocoding site addresses if coordinates are absent or inconsistent
  - choosing a defensible proxy for "underutilised"
  - normalising site names and duplicates
  - filtering England-wide estate data down to London-relevant records

### Recommended implementation approach

1. Start with a simple proximity flag to NHS-owned estate sites.
2. Add "underutilised" only if the `ERIC` definitions clearly support a robust proxy.
3. Use the archived `voids_with_geodata.csv` as an optional secondary source if it improves London usefulness.
4. Keep the first implementation informational rather than score-altering.

### Acceptance criteria

- Each ranked candidate can show whether NHS estate exists nearby.
- Output tables include nearest site and distance.
- The app states which estate dataset and year were used.
- If "underutilised" is shown, the proxy logic is documented.

## Requirement 4: Ethnicity Index

### Goal

Add `2021 Census` ethnicity data at `LSOA` level as an optional equity-oriented analytical lens for `ICBs` that want to target communities facing cultural, language, or access barriers.

### Current state

- The app has no ethnicity dimension.
- The existing scoring model expects numeric `LSOA`-level indices that can be min-max scaled and weighted.

### Functional requirements

1. Add one or more ethnicity-derived `LSOA` measures as optional indices.
2. Do not create a hidden or hard-coded assumption that higher ethnic diversity automatically equals higher need.
3. Treat ethnicity as an explicit, user-chosen equity lens.
4. Support at least one of the following implementation styles:
   - broad-group proportions, such as percentage of residents in selected ethnic categories
   - an ethnicity diversity measure
   - a small set of clearly named derived fields that users can deliberately select
5. Document exactly what each ethnicity field means.
6. Keep the layer optional and off by default.

### Recommended design choice

The safest MVP is not a single opaque "ethnicity index".

A better first implementation is:

- ingest raw `LSOA` ethnicity counts / proportions
- derive a few transparent fields
- let the user explicitly choose which one, if any, to weight

Example derived fields:

- `pct_asian_residents`
- `pct_black_residents`
- `pct_mixed_residents`
- `pct_other_ethnic_group_residents`
- `ethnic_diversity_index`

This is more interpretable and easier to defend than a single black-box ethnicity score.

### Data sources

- `ONS` `TS021` `Ethnic group` dataset from Census 2021
- `Nomis` `C2021TS021` API / dataset endpoint is also suitable for extraction

### Important source notes

- The `ONS` `TS021` dataset was released on `29 November 2022` and last updated on `28 March 2023`.
- `ONS` states the dataset can be filtered by statistical areas including `MSOA` or `LSOA`.
- The `Nomis` version exposes an API reference code: `C2021TS021`.
- `ONS` notes that Census 2021 small-area data is subject to disclosure control, so small differences between tables can occur.

### Complexity / ease

- Technical implementation is `low effort`.
- Governance / interpretation is `medium effort`.
- The biggest risk is not engineering; it is creating a scoring approach that is hard to justify or easy to misread.

### Recommended implementation approach

1. Create a local cached ethnicity-by-`LSOA` file.
2. Add transparent derived columns rather than a single opaque composite.
3. Expose them through the same optional-index workflow as the other Need Score inputs.
4. Add explicit methodology notes describing how ethnicity is being used.

### Acceptance criteria

- Users can add at least one ethnicity-derived field into the Need Model.
- The field is clearly labelled and optional.
- The app explains the source year and exact derivation.
- Methodology text makes clear that this is an equity lens, not an automatic deprivation substitute.

## Suggested Delivery Order

If these are implemented sequentially, the most practical order is:

1. `QOF` disease prevalence
2. Ethnicity-derived `LSOA` indices
3. Travel-time catchments
4. Estate availability flags

Reason:

- `QOF` and ethnicity fit naturally into the existing `LSOA` need-index framework.
- Travel time is higher impact but touches scoring, caching, and mapping behavior.
- Estate flags are valuable, but they are best added after the core scoring and access logic is stable.

## Recommended Code Touchpoints

The implementing LLM should expect most work to touch these files:

- `app.py`
- `webapp/analysis.py`
- `webapp/data_access.py`
- `webapp/config.py`
- `webapp/data_validation.py`

Likely supporting additions:

- new cached CSVs under `data/` or `output/`
- new loader / transform scripts under `scripts/analysis/`
- methodology updates in `docs/METHODOLOGY.md`

## Sources

- NHS England Digital, `Quality and Outcomes Framework, 2024-25`: https://digital.nhs.uk/data-and-information/publications/statistical/quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data/2024-25
- NHS England Digital, `QOF 2024-25 Technical annex`: https://digital.nhs.uk/data-and-information/publications/statistical/quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data/2024-25/technical-annex
- NHS England Digital, `Estates Return Information Collection (ERIC)`: https://digital.nhs.uk/about-nhs-digital/corporate-information-and-documents/directions-and-data-provision-notices/data-provision-notices-dpns/estates-return-information-collection-eric-data-provision-notice
- NHS England Digital, `ERIC 2024/25`: https://digital.nhs.uk/data-and-information/publications/statistical/estates-returns-information-collection/summary-page-and-dataset-for-eric-2024-25
- ONS, `TS021 Ethnic group`: https://www.ons.gov.uk/datasets/TS021
- Nomis, `C2021TS021`: https://www.nomisweb.co.uk/datasets/c2021ts021
- TfL Unified API: https://api.tfl.gov.uk/
- openrouteservice restrictions: https://openrouteservice.org/restrictions/
- openrouteservice plans: https://staging.openrouteservice.org/plans/
- Traveline developer area: https://www.traveline.info/developer-area

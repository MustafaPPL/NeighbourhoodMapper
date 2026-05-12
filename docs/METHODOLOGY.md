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

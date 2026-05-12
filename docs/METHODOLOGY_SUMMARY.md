# Neighbourhood Hub Ranking Methodology

## Executive Summary

This application was built as an additional interface alongside the existing static geospatial analysis scripts. The original scripts remain intact and runnable on their own. The new web application uses the same data foundations to support NHS / ICB decision-making by ranking proposed Neighbourhood Hub locations against surrounding population need.

The tool is not only a map. Its primary purpose is to compare candidate hub locations and produce a ranked list based on a transparent two-stage weighting model:

1. a weighted `Need Score` is calculated for each `LSOA`
2. a weighted `Hub Score` is calculated for each candidate hub postcode using nearby `LSOA` need

## Objective

The core question the tool is designed to answer is:

Which proposed hub locations appear best placed to serve the highest nearby need, based on the priorities selected by the user?

## Overall Analytical Approach

The model operates in two stages:

1. Build an `LSOA`-level Need Score across the selected geography
2. Rank candidate hub postcodes using a proximity-weighted Hub Score

This makes the method useful for location testing, scenario comparison, and structured planning discussions.

## Geography and Scope

Users can define the analytical footprint by selecting:

- all London
- a specific London `ICB`
- selected neighbourhoods within that chosen geography

This scope affects both:

- which `LSOAs` are included in the analysis
- the population against which index values are standardised

## Stage 1: Building the Need Score

### Inputs

The Need Score is built from `LSOA`-level indicators such as:

- deprivation
- total population
- 65+ population
- 65+ proportion

The app allows the user to choose which indices to include for a given run.

### Standardisation

Because the chosen indicators are on different scales, each selected index is standardised within the selected geography using min-max scaling.

This converts each selected variable onto a common `0 to 1` scale.

### Weighting

Users assign a weight to each selected index.

The application enforces that:

- weights must sum to exactly `100`
- weights are not silently normalised

This ensures that the relative importance of each measure is an explicit user choice.

### Need Score Formula

For each `LSOA`:

`Need Score = sum(standardised index x weight fraction)`

In practice, this means:

- each chosen indicator is scaled
- each scaled indicator is multiplied by its assigned weight
- the weighted components are summed into one overall score

This produces a flexible, comparable `Need Score` across the selected geography.

## Stage 2: Building the Hub Score

Once `LSOA` Need Scores are available, each candidate hub location is evaluated.

### Candidate Hub Inputs

Users enter candidate hub postcodes.

The application then:

- geocodes the postcode to a point
- identifies the host `LSOA` using the postcode-to-`LSOA` lookup

### Spatial Method

For each candidate postcode:

1. the candidate point is located on the map
2. `LSOA` centroids are derived from `LSOA` polygons
3. the distance from the candidate point to all `LSOA` centroids is calculated using projected coordinates
4. `LSOAs` are grouped into three proximity bands:
   - host `LSOA`
   - within `500m`
   - between `500m` and `2km`

### Proximity Weighting

The tool then applies a fixed proximity weighting model:

- `60%` host `LSOA` Need Score
- `25%` mean Need Score within `500m`
- `15%` mean Need Score between `500m` and `2km`

### Hub Score Formula

`Hub Score = (0.60 x host Need Score) + (0.25 x mean Need Score 0-500m) + (0.15 x mean Need Score 500m-2km)`

This reflects the planning assumption that:

- the immediate host area matters most
- nearby surrounding need should still influence the ranking

## Ranking Output

After the Hub Score is calculated for each candidate postcode, locations are ranked in descending order.

The final outputs include:

- an `LSOA` Need Score choropleth
- candidate hub points
- a ranked table of candidate hub locations
- audit information for the run
- optional overlays of existing:
  - GP practices
  - community pharmacies
  - family hubs

## Why This Method Is Useful

This method is stronger than a simple static map because it combines:

- user-defined need priorities
- geography-specific standardisation
- explicit proximity assumptions
- transparent candidate ranking

It supports a more structured discussion around location options by showing not only where need exists, but which candidate hub sites are best placed to serve that need under the chosen weighting model.

## Key Management Message

The most important feature of the tool is its two-layer weighting logic:

1. weighted indexing to define what “need” means
2. weighted proximity scoring to define how that need is captured by each proposed hub

This allows decision-makers to test different assumptions and answer:

Which candidate hub locations appear strongest once both need and nearby catchment are taken into account?

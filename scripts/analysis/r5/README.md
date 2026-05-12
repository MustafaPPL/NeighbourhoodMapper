# R5 Transit Travel-Time Matrix

Computes a full London LSOA × LSOA transit travel-time matrix using the
[Conveyal R5](https://github.com/conveyal/r5) routing engine with TfL GTFS feeds.

The output is `data/cache/travel_time_transit.parquet` with columns:
`origin_lsoa`, `destination_lsoa`, `travel_time_minutes`.

---

## Prerequisites

- Docker (20.10+)
- 16 GB RAM recommended (R5 loads all GTFS feeds into memory)
- ~20 GB disk space for GTFS feeds and output

---

## Step 1 — Download GTFS feeds

Download the following GTFS feeds and place them in a local `data/` directory:

| Feed | URL |
|------|-----|
| TfL Bus | https://data.tfl.gov.uk/tfl/syndication/feeds/bus-sequences.zip |
| TfL Tube + Elizabeth line | https://api.tfl.gov.uk/tfl/syndication/feeds/tfl-gtfs.zip |
| National Rail (London terminals) | https://data.atoc.org/how-to-feed (requires free registration) |

Place all GTFS `.zip` files inside the `data/` directory.

---

## Step 2 — Download London OSM extract

Download the London OSM PBF extract from Geofabrik:

```
curl -o data/london.osm.pbf \
  https://download.geofabrik.de/europe/great-britain/england/greater-london-latest.osm.pbf
```

---

## Step 3 — Prepare LSOA centroids

The script expects `data/lsoa_centroids.csv` with columns:
`LSOA_code`, `latitude`, `longitude`.

Generate it using the QOF script (which optionally accepts a centroid CSV) or
export from any GIS tool:

```
python scripts/analysis/build_qof_lsoa.py ... --lsoa-csv path/to/existing_centroids.csv
```

Or create manually from the ONS LSOA boundary data.

---

## Step 4 — Build the Docker image

From the project root:

```bash
docker build -t london-r5 scripts/analysis/r5/
```

---

## Step 5 — Run the matrix computation

```bash
docker run --rm \
  -v "$(pwd)/data:/data:ro" \
  -v "$(pwd)/data/cache:/output" \
  -e DATA_DIR=/data \
  -e OUTPUT_DIR=/output \
  --memory=14g \
  london-r5
```

The computation takes approximately 30 minutes to 2 hours depending on hardware.
Progress is printed to stdout every 50 chunk pairs.

---

## Output

`data/cache/travel_time_transit.parquet` with schema:

| Column | Type | Description |
|--------|------|-------------|
| `origin_lsoa` | str | LSOA 2021 code of origin |
| `destination_lsoa` | str | LSOA 2021 code of destination |
| `travel_time_minutes` | float | Median transit travel time (NaN = no feasible route) |

---

## Departure time

Fixed at **Tuesday 10:00 AM** for reproducibility. This captures typical
inter-peak service levels. To change, edit `DEPARTURE_DATE` and
`DEPARTURE_TIME` in `run_transit_matrix.py` before building the Docker image.

---

## Troubleshooting

**R5 does not start within 120s**: Increase `--memory` in the docker run command.
R5 needs at least 8 GB to load London GTFS feeds.

**Empty output / all NaN**: Check that the GTFS feeds cover the `DEPARTURE_DATE`.
National Rail feeds have a validity window — ensure the date falls within it.

**URL or network errors**: The container runs fully offline after the image is
built. No network access is needed during computation.

import pandas as pd
import requests
import time
import urllib.parse

# ----------------------------
# CONFIG
# ----------------------------
INPUT_FILE = "voids.csv"
OUTPUT_FILE = "voids_with_geodata.csv"

TOMTOM_API_KEY = "dFrFzSpNgip26DzMcHkSVmojaDOm8822"

BASE_URL = "https://api.tomtom.com/search/2/search"

AUTO_SAVE_EVERY = 20
SLEEP_SECONDS = 0.2

# ----------------------------
# Load CSV
# ----------------------------
df = pd.read_csv(INPUT_FILE)
df.columns = df.columns.str.strip()

if "Voided Centres" not in df.columns:
    raise ValueError("Missing 'Voided Centres' column")

# ----------------------------
# TomTom Search Function
# ----------------------------
def tomtom_search(query):

    encoded_query = urllib.parse.quote(query)
    url = f"{BASE_URL}/{encoded_query}.json"

    params = {
        "key": TOMTOM_API_KEY,
        "limit": 1,
        "countrySet": "GB"
    }

    response = requests.get(url, params=params, timeout=15)

    if response.status_code != 200:
        print(f"   ❌ API Error: {response.status_code}", flush=True)
        return None

    data = response.json()

    if not data.get("results"):
        return None

    result = data["results"][0]

    return {
        "address": result.get("address", {}).get("freeformAddress"),
        "postcode": result.get("address", {}).get("postalCode"),
        "latitude": result.get("position", {}).get("lat"),
        "longitude": result.get("position", {}).get("lon"),
        "score": result.get("score")
    }

# ----------------------------
# Prepare Output Columns
# ----------------------------
df["Full Address"] = None
df["Postcode"] = None
df["Latitude"] = None
df["Longitude"] = None
df["TomTom Score"] = None
df["Match Type"] = None

total = len(df)

direct_matches = 0
fallback_matches = 0
no_matches = 0

print(f"\n🚀 Starting TomTom geocoding for {total} voided centres...\n")

# ----------------------------
# Run Search
# ----------------------------
for i, row in df.iterrows():

    centre = str(row["Voided Centres"]).strip()
    query = f"{centre}, UK"

    print(f"[{i+1}/{total}] Searching: {query}", flush=True)

    result = tomtom_search(query)

    if result:
        print(f"   ✅ MATCH")
        print(f"      Address: {result.get('address')}")
        print(f"      Lat/Lon: {result.get('latitude')}, {result.get('longitude')}")
        print(f"      Score: {result.get('score')}\n", flush=True)

        df.at[i, "Full Address"] = result.get("address")
        df.at[i, "Postcode"] = result.get("postcode")
        df.at[i, "Latitude"] = result.get("latitude")
        df.at[i, "Longitude"] = result.get("longitude")
        df.at[i, "TomTom Score"] = result.get("score")
        df.at[i, "Match Type"] = "Name match"

        direct_matches += 1

    else:
        print("   ❌ No match found\n", flush=True)

        df.at[i, "Match Type"] = "No match"
        no_matches += 1

    # Auto-save periodically
    if (i + 1) % AUTO_SAVE_EVERY == 0:
        df.to_csv(OUTPUT_FILE, index=False)
        print(f"💾 Auto-saved progress at row {i+1}\n", flush=True)

    time.sleep(SLEEP_SECONDS)

# ----------------------------
# Final Save
# ----------------------------
df.to_csv(OUTPUT_FILE, index=False)

# ----------------------------
# Summary
# ----------------------------
print("\n===== ✅ COMPLETE =====")
print(f"Direct matches: {direct_matches}")
print(f"No matches: {no_matches}")
print(f"\nSaved to: {OUTPUT_FILE}")

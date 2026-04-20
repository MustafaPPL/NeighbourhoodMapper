import pandas as pd
import requests
import time
import urllib.parse

# ----------------------------
# CONFIG
# ----------------------------
INPUT_FILE = "primary_care_data.csv"
OUTPUT_FILE = "gp_practices_tomtom_geocoded.csv"

TOMTOM_API_KEY = "dFrFzSpNgip26DzMcHkSVmojaDOm8822"

BASE_URL = "https://api.tomtom.com/search/2/search"

AUTO_SAVE_EVERY = 20   # autosave every N rows
SLEEP_SECONDS = 0.2    # rate control

# ----------------------------
# Load Data
# ----------------------------
df = pd.read_csv(INPUT_FILE)
df.columns = df.columns.str.strip()

if "Practice name" not in df.columns:
    raise ValueError("Missing 'Practice name' column")

if "Post Code" not in df.columns:
    raise ValueError("Missing 'Post Code' column")

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
        "Postcode": result.get("address", {}).get("postalCode"),
        "latitude": result.get("position", {}).get("lat"),
        "longitude": result.get("position", {}).get("lon"),
        "score": result.get("score")
    }

# ----------------------------
# Prepare Output Columns
# ----------------------------
df["Matched Address"] = None
df["Matched Postcode"] = None
df["Latitude"] = None
df["Longitude"] = None
df["TomTom Score"] = None
df["Match Type"] = None

# Counters
direct_matches = 0
fallback_matches = 0
no_matches = 0

total = len(df)

print(f"\n🚀 Starting TomTom geocoding for {total} practices...\n")

# ----------------------------
# Run Search
# ----------------------------
for i, row in df.iterrows():

    practice = str(row["Practice name"]).strip()
    postcode = str(row["Post Code"]).strip()

    query = f"{practice}, {postcode}, UK"

    print(f"[{i+1}/{total}] Searching: {query}", flush=True)

    result = tomtom_search(query)

    if result:
        print(f"   ✅ MATCH")
        print(f"      Address: {result['address']}")
        print(f"      Lat/Lon: {result['latitude']}, {result['longitude']}")
        print(f"      Score: {result['score']}\n", flush=True)

        df.at[i, "Matched Address"] = result["address"]
        df.at[i, "Matched Postcode"] = result.get("postcode")
        df.at[i, "Latitude"] = result["latitude"]
        df.at[i, "Longitude"] = result["longitude"]
        df.at[i, "TomTom Score"] = result["score"]
        df.at[i, "Match Type"] = "Name + postcode match"

        direct_matches += 1

    else:
        print("   ⚠ No direct match. Trying postcode fallback...", flush=True)

        fallback = tomtom_search(f"{postcode}, UK")

        if fallback:
            print(f"   🔁 FALLBACK MATCH")
            print(f"      Address: {fallback['address']}")
            print(f"      Lat/Lon: {fallback['latitude']}, {fallback['longitude']}")
            print(f"      Score: {fallback['score']}\n", flush=True)

            df.at[i, "Matched Address"] = fallback["address"]
            df.at[i, "Matched Postcode"] = fallback["postcode"]
            df.at[i, "Latitude"] = fallback["latitude"]
            df.at[i, "Longitude"] = fallback["longitude"]
            df.at[i, "TomTom Score"] = fallback["score"]
            df.at[i, "Match Type"] = "Postcode fallback"

            fallback_matches += 1

        else:
            print("   ❌ NO MATCH FOUND\n", flush=True)

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
print(f"Fallback matches: {fallback_matches}")
print(f"No matches: {no_matches}")
print(f"\nSaved to: {OUTPUT_FILE}")

#!/usr/bin/env python3
"""Download all public source data into data/raw/. Logs every request to data/raw/fetchlog.txt."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
LOG = RAW / "fetchlog.txt"

MAX_SINGLE = 100 * 1024 * 1024
MAX_TOTAL = 300 * 1024 * 1024

HVI_URL = "https://raw.githubusercontent.com/nychealth/EHDP-data/production/key-topics/heat-vulnerability-index/hvi-nta-2020.csv"
PLACES_URL = "https://data.cdc.gov/resource/yjkw-uj5s.json"
PLACES_PARAMS = {
    "$select": "tractfips,countyfips,totalpopulation,mhlth_crudeprev,depression_crudeprev",
    "$where": "countyfips in('36005','36047','36061','36081','36085')",
    "$limit": "50000",
}
EQUIV_URL = "https://data.cityofnewyork.us/resource/hm78-6dwm.json"
NTA_URL = "https://data.cityofnewyork.us/api/geospatial/9nt8-h7nd?method=export&format=GeoJSON"
TREES_URL = "https://data.cityofnewyork.us/resource/uvpi-gqnh.json"
TREES_WHERE = "status='Alive'"
PAGE = 50000
META = {
    "places": "https://data.cdc.gov/api/views/yjkw-uj5s.json",
    "equiv": "https://data.cityofnewyork.us/api/views/hm78-6dwm.json",
    "nta": "https://data.cityofnewyork.us/api/views/9nt8-h7nd.json",
    "trees": "https://data.cityofnewyork.us/api/views/uvpi-gqnh.json",
}

total_bytes = 0
session = requests.Session()


def get(url, params=None):
    global total_bytes
    r = session.get(url, params=params, timeout=120)
    size = len(r.content)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(LOG, "a") as f:
        f.write(f"{ts}\t{r.status_code}\t{size}\t{r.url}\n")
    r.raise_for_status()
    if size > MAX_SINGLE:
        sys.exit(f"HARD LIMIT: single download {size} bytes > 100 MB ({r.url})")
    total_bytes += size
    if total_bytes > MAX_TOTAL:
        sys.exit(f"HARD LIMIT: total raw data {total_bytes} bytes > 300 MB")
    return r


def save(name, content: bytes):
    (RAW / name).write_bytes(content)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    LOG.write_text("utc\tstatus\tbytes\turl\n")

    save("hvi-nta-2020.csv", get(HVI_URL).content)
    save("places.json", get(PLACES_URL, PLACES_PARAMS).content)
    save("equiv.json", get(EQUIV_URL, {"$limit": "50000"}).content)
    save("nta.geojson", get(NTA_URL).content)
    for key, url in META.items():
        save(f"meta_{key}.json", get(url).content)

    count = get(TREES_URL, {"$select": "count(*)", "$where": TREES_WHERE}).json()
    expected = int(count[0]["count"])
    (RAW / "trees_expected.json").write_text(json.dumps({"expected_alive": expected}))

    trees = []
    offset = 0
    while True:
        rows = get(TREES_URL, {
            "$select": "tree_id,latitude,longitude",
            "$where": TREES_WHERE,
            "$order": "tree_id",
            "$limit": str(PAGE),
            "$offset": str(offset),
        }).json()
        if not rows:
            break
        trees.extend(rows)
        offset += PAGE
    (RAW / "trees.json").write_text(json.dumps(trees))

    print(f"trees expected {expected}, fetched {len(trees)}")
    print(f"total bytes downloaded {total_bytes}")


if __name__ == "__main__":
    main()

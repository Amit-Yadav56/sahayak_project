"""
STEP 1B — Download datasets from data.gov.in
=============================================
Uses the official data.gov.in REST API.
API key registration: https://data.gov.in/user/register

Run:  python -m scrapers.datagovin
Output: data/raw/datagovin_<resource_id>.json  (one file per resource)
"""

import os
import json
import time
import logging
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

API_KEY   = os.getenv("DATA_GOV_API_KEY", "YOUR_API_KEY_HERE")
BASE_URL  = "https://api.data.gov.in/resource"
PAGE_SIZE = 1000     # max records per call the API allows
OUTPUT_DIR = Path("data/raw")
DELAY_SECS = 0.5

# ── Resource IDs to download ──────────────────────────────────────────────────
# Find resource IDs at:  https://data.gov.in/  → search for dataset → "API" button
# Each dataset has a unique resource ID like  "6176ee09-3d56-4a3b-8115-21841ddd696a"

RESOURCES = [
    {
        "id": "6176ee09-3d56-4a3b-8115-21841ddd696a",
        "name": "central_govt_schemes",
        "desc": "Central government welfare schemes list",
    },
    # Add more resource IDs here:
    # {
    #     "id": "another-uuid-here",
    #     "name": "state_schemes_tamil_nadu",
    #     "desc": "Tamil Nadu state schemes",
    # },
]

# ── Core functions ─────────────────────────────────────────────────────────────

def fetch_resource_page(resource_id: str, offset: int = 0, limit: int = PAGE_SIZE) -> dict:
    """Fetch one page of records from a data.gov.in resource."""
    r = requests.get(
        f"{BASE_URL}/{resource_id}",
        params={
            "api-key": API_KEY,
            "format":  "json",
            "offset":  offset,
            "limit":   limit,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def fetch_all_records(resource_id: str) -> list[dict]:
    """
    Paginate through all records for a resource.
    data.gov.in returns:
        { "count": N, "total": T, "records": [...] }
    """
    all_records = []
    offset = 0

    while True:
        log.info(f"  Fetching offset={offset} ...")
        data = fetch_resource_page(resource_id, offset=offset)

        records = data.get("records", [])
        if not records:
            break

        all_records.extend(records)
        total = int(data.get("total", 0))
        log.info(f"  Got {len(all_records)}/{total} records")

        if len(all_records) >= total:
            break

        offset += PAGE_SIZE
        time.sleep(DELAY_SECS)

    return all_records


def download_resource(resource: dict) -> Path:
    """Download a single resource and save to JSON file."""
    rid  = resource["id"]
    name = resource["name"]
    out  = OUTPUT_DIR / f"datagovin_{name}.json"

    log.info(f"Downloading resource '{name}' ({rid}) ...")
    records = fetch_all_records(rid)

    out.write_text(json.dumps({
        "resource_id": rid,
        "name": name,
        "record_count": len(records),
        "records": records,
    }, indent=2, ensure_ascii=False))

    log.info(f"  Saved {len(records)} records → {out}")
    return out


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if API_KEY == "YOUR_API_KEY_HERE":
        raise SystemExit("Set DATA_GOV_API_KEY in .env first. Register at data.gov.in")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for resource in RESOURCES:
        try:
            download_resource(resource)
        except Exception as e:
            log.error(f"Failed for {resource['name']}: {e}")

    log.info("All resources downloaded.")

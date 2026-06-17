"""
STEP 1A — Scrape MyScheme API
=============================

Uses the public search API used by myscheme.gov.in.

Run:
    python -m scrapers.myscheme

Output:
    data/raw/myscheme_raw.json
"""

import json
import time
import logging
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────

SEARCH_API = "https://api.myscheme.gov.in/search/v6/schemes"

HEADERS = {
    "x-api-key": "tYTy5eEhlu9rFjyxuCr7ra7ACp4dv1RH8gWuHTDc",
    "origin": "https://www.myscheme.gov.in",
    "user-agent": "Mozilla/5.0",
    "accept": "application/json"
}

OUTPUT_FILE = Path("data/raw/myscheme_raw.json")

PAGE_SIZE = 100
DELAY_SECS = 1.0

# ─────────────────────────────────────────────────────────────

def get_page(offset: int = 0, size: int = PAGE_SIZE) -> dict:

    params = {
        "lang": "en",
        "q": "[]",
        "keyword": "",
        "sort": "",
        "from": offset,
        "size": size,
    }

    r = requests.get(
        SEARCH_API,
        headers=HEADERS,
        params=params,
        timeout=30,
    )

    r.raise_for_status()

    data = r.json()

    if data.get("statusCode") != 200:
        raise Exception(
            f"MyScheme API error: {data.get('errorDescription')}"
        )

    return data["data"]


# ─────────────────────────────────────────────────────────────

def normalize_item(item: dict) -> dict:

    fields = item.get("fields", {})

    return {
        "id": item.get("id"),
        "slug": fields.get("slug"),
        "scheme_name": fields.get("schemeName"),
        "short_title": fields.get("schemeShortTitle"),
        "level": fields.get("level"),
        "scheme_for": fields.get("schemeFor"),
        "ministry": fields.get("nodalMinistryName"),
        "categories": fields.get("schemeCategory", []),
        "states": fields.get("beneficiaryState", []),
        "description": fields.get("briefDescription"),
        "tags": fields.get("tags", []),
        "close_date": fields.get("schemeCloseDate"),
        "priority": fields.get("priority"),
    }


# ─────────────────────────────────────────────────────────────

def scrape(max_schemes: int | None = None) -> list[dict]:

    results = []

    offset = 0

    while True:

        log.info(f"Fetching offset={offset}")

        data = get_page(offset)

        items = data["hits"]["items"]

        if not items:
            break

        for item in items:

            results.append(
                normalize_item(item)
            )

            if (
                max_schemes is not None
                and len(results) >= max_schemes
            ):
                return results

        total = data["summary"]["total"]

        log.info(
            f"Downloaded {len(results)} / {total}"
        )

        offset += PAGE_SIZE

        time.sleep(DELAY_SECS)

    return results


# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    schemes = scrape()

    # Save raw JSON
    OUTPUT_FILE.write_text(
        json.dumps(schemes, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    # Save CSV
    import pandas as pd

    df = pd.json_normalize(schemes)

    csv_file = Path("data/raw/myscheme_schemes.csv")

    df.to_csv(
        csv_file,
        index=False,
        encoding="utf-8-sig"
    )

    log.info(f"Saved {len(schemes)} schemes → {OUTPUT_FILE}")
    log.info(f"Saved {len(df)} rows → {csv_file}")

    if schemes:
        log.info(
            f"Sample keys: {list(schemes[0].keys())}"
        )
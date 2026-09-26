"""
STEP 1A — Scrape myscheme.gov.in
=================================
myscheme.gov.in loads scheme data via an internal JSON API (not rendered HTML).
We hit that API directly — much more reliable than parsing HTML.

Run:  python -m scrapers.myscheme
Output: data/raw/myscheme_raw.json
"""

import requests
import json
import time
import logging
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# --- Constants ---
BASE_URL   = "https://api.myscheme.gov.in"
LIST_API   = f"{BASE_URL}/search/v6/schemes"   # paginated search/list endpoint
DETAIL_API = f"{BASE_URL}/schemes/v6/public/schemes"   # append ?slug=...&lang=en for detail

HEADERS = {
    "x-api-key": "tYTy5eEhlu9rFjyxuCr7ra7ACp4dv1RH8gWuHTDc",
    "origin": "https://www.myscheme.gov.in",
    "user-agent": "Mozilla/5.0",
    "accept": "application/json"
}

OUTPUT_FILE = Path("data/raw/myscheme_raw.json")
DELAY_SECS  = 1.0   # be polite — 1 second between requests
PAGE_SIZE   = 100   # API accepts 100; larger sizes are rejected


def _extract_items(payload: dict) -> list[dict]:
    """Return the first list-like collection of scheme hits found in a response payload."""
    if not isinstance(payload, dict):
        return []

    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    hits = data.get("hits")
    if isinstance(hits, dict):
        items = hits.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]

    for key in ("schemes", "items", "results", "content"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested_items = value.get("items")
            if isinstance(nested_items, list):
                return [item for item in nested_items if isinstance(item, dict)]

    return []


def _extract_total(payload: dict, default: int = 0) -> int:
    """Return a total count if the API includes one."""
    if not isinstance(payload, dict):
        return default

    data = payload.get("data")
    if not isinstance(data, dict):
        return default

    for key in ("total", "count", "totalCount", "total_count"):
        value = data.get(key)
        if isinstance(value, int):
            return value

    summary = data.get("summary")
    if isinstance(summary, dict):
        for key in ("total", "count", "value"):
            value = summary.get(key)
            if isinstance(value, int):
                return value

    hits = data.get("hits")
    if isinstance(hits, dict):
        page = hits.get("page")
        if isinstance(page, dict):
            value = page.get("total")
            if isinstance(value, int):
                return value

    return default


def _normalize_search_hit(hit: dict) -> dict:
    """Flatten a live search hit into the record shape used by the normalizer."""
    fields = hit.get("fields") if isinstance(hit.get("fields"), dict) else {}
    states = fields.get("beneficiaryState") or []
    categories = fields.get("schemeCategory") or []
    tags = fields.get("tags") or []

    return {
        "id": hit.get("id") or fields.get("slug") or "",
        "slug": fields.get("slug") or "",
        "scheme_name": fields.get("schemeName") or "",
        "short_title": fields.get("schemeShortTitle") or "",
        "level": fields.get("level") or "",
        "scheme_for": fields.get("schemeFor") or "",
        "ministry": fields.get("nodalMinistryName") or "",
        "categories": categories if isinstance(categories, list) else [],
        "states": states if isinstance(states, list) else [],
        "description": fields.get("briefDescription") or "",
        "tags": tags if isinstance(tags, list) else [],
        "close_date": fields.get("schemeCloseDate") or None,
        "priority": fields.get("priority"),
        "raw_json": hit,
    }

# --- Helpers ---

def get_json(url: str, params: dict = None, retries: int = 3) -> dict:
    """GET url, return parsed JSON. Retries on transient errors."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            log.warning(f"Attempt {attempt}/{retries} failed for {url}: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)  # exponential backoff
            else:
                raise


# --- Core scraping functions ---

def fetch_all_scheme_records(max_schemes: int | None = None) -> list[dict]:
    """
    Page through the scheme list API and collect normalized listing records.
    """
    records = []
    page  = 1

    while True:
        log.info(f"Fetching list page {page} ...")
        params = {
            "lang": "en",
            "q": "[]",
            "keyword": "",
            "sort": "",
            "from": (page - 1) * PAGE_SIZE,
            "size": PAGE_SIZE,
        }
        data = get_json(LIST_API, params=params)

        schemes = _extract_items(data)
        if not schemes:
            log.info("No more schemes — stopping pagination.")
            break

        for hit in schemes:
            record = _normalize_search_hit(hit)
            if record.get("slug"):
                records.append(record)
                if max_schemes and len(records) >= max_schemes:
                    return records

        total = _extract_total(data, default=len(records))
        log.info(f"  Got {len(records)}/{total} schemes so far")

        if total and len(records) >= total:
            break
        page += 1
        time.sleep(DELAY_SECS)

    return records


def fetch_scheme_detail(slug: str) -> dict | None:
    """Fetch full detail JSON for a single scheme slug."""
    try:
        data = get_json(DETAIL_API, params={"slug": slug, "lang": "en"})
        return data.get("data") or data  # unwrap if nested under "data"
    except Exception as e:
        log.error(f"Failed to fetch detail for {slug}: {e}")
        return None


# --- Main ---

def scrape(max_schemes: int = None) -> list[dict]:
    """
    Full scrape: list all slugs → fetch each detail → return list of dicts.

    Args:
        max_schemes: optional cap for testing (None = fetch all)
    """
    records = fetch_all_scheme_records(max_schemes=max_schemes)
    log.info(f"Will save {len(records)} schemes")

    return records


if __name__ == "__main__":
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    schemes = scrape()

    OUTPUT_FILE.write_text(json.dumps(schemes, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Saved {len(schemes)} schemes -> {OUTPUT_FILE}")

    # Quick preview
    if schemes:
        first = schemes[0]
        log.info(f"Sample keys: {list(first.keys())}")

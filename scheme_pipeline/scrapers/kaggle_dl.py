"""
STEP 1C — Download datasets from Kaggle
========================================
Uses the official Kaggle Python API.

Setup (one-time):
    pip install kaggle
    Go to https://www.kaggle.com/settings → API → "Create New Token"
    This downloads  kaggle.json  — place it at  ~/.kaggle/kaggle.json
    chmod 600 ~/.kaggle/kaggle.json

    OR set KAGGLE_USERNAME and KAGGLE_KEY in your .env file.

Run:  python -m scrapers.kaggle_dl
Output: data/raw/kaggle/<dataset_name>/  (extracted CSV files)
"""

import os
import logging
import zipfile
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUTPUT_DIR = Path("data/raw/kaggle")

# --- Datasets to download ---
# Format: "owner/dataset-slug"  (from the Kaggle dataset URL)
# Example URL: https://www.kaggle.com/datasets/nehaprabhavalkar/av-healthcare-analytics-ii
#              → "nehaprabhavalkar/av-healthcare-analytics-ii"

DATASETS = [
    {
        "slug": "elchemist/myscheme-india-govt-welfare-schemes",   # example — update to real slug
        "name": "india_govt_schemes",
    },
    # Add more:
    # {
    #     "slug": "another/dataset-slug",
    #     "name": "local_name",
    # },
]


# --- Core ---

def setup_kaggle_auth():
    """
    Kaggle SDK reads credentials from:
      1. ~/.kaggle/kaggle.json
      2. KAGGLE_USERNAME + KAGGLE_KEY environment variables
    We set env vars from .env so both paths work.
    """
    username = os.getenv("KAGGLE_USERNAME")
    key      = os.getenv("KAGGLE_KEY")
    if username and key:
        os.environ["KAGGLE_USERNAME"] = username
        os.environ["KAGGLE_KEY"]      = key
        log.info("Kaggle auth set from environment variables.")
    else:
        log.info("No KAGGLE_USERNAME/KAGGLE_KEY in env — falling back to ~/.kaggle/kaggle.json")


def download_dataset(slug: str, name: str) -> Path:
    """
    Download and unzip a Kaggle dataset.
    Returns the path to the extracted folder.
    """
    import kaggle  # import here so missing install is a clear error

    dest = OUTPUT_DIR / name
    dest.mkdir(parents=True, exist_ok=True)

    log.info(f"Downloading Kaggle dataset: {slug} -> {dest}")
    kaggle.api.dataset_download_files(
        slug,
        path=str(dest),
        unzip=True,     # automatically extracts the zip
        quiet=False,
    )

    csv_files = list(dest.glob("*.csv"))
    log.info(f"  Downloaded files: {[f.name for f in csv_files]}")
    return dest


def list_csvs(folder: Path) -> list[Path]:
    return sorted(folder.glob("**/*.csv"))


# --- Main ---

if __name__ == "__main__":
    setup_kaggle_auth()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for ds in DATASETS:
        try:
            folder = download_dataset(ds["slug"], ds["name"])
            csvs   = list_csvs(folder)
            log.info(f"  CSV files in {folder.name}: {[c.name for c in csvs]}")
        except Exception as e:
            log.error(f"Failed for {ds['slug']}: {e}")
            log.error("Check the dataset slug exists at kaggle.com/datasets/<slug>")

    log.info("Kaggle downloads complete.")

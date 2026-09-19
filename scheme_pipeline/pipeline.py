"""
pipeline.py — Run the full pipeline end-to-end
================================================

Usage:
    python pipeline.py                  # full run
    python pipeline.py --step scrape    # only scraping
    python pipeline.py --step parse     # only normalization
    python pipeline.py --step load      # only DB load
    python pipeline.py --reset-db       # drop tables, then full run
    python pipeline.py --max 50         # scrape only 50 schemes (for testing)
"""

import argparse
import logging
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("pipeline")


def step_scrape(max_schemes: int = None):
    log.info("---------------------------------------------------")
    log.info("STEP 1 - Scraping data sources")
    log.info("---------------------------------------------------")

    # 1a. myscheme.gov.in
    try:
        from scrapers.myscheme import scrape
        import json
        from pathlib import Path
        schemes = scrape(max_schemes=max_schemes)
        out = Path("data/raw/myscheme_raw.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(schemes, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info(f"myscheme: saved {len(schemes)} schemes")
    except Exception as e:
        log.error(f"myscheme scrape failed: {e}")

    # 1b. data.gov.in
    try:
        from scrapers.datagovin import RESOURCES, download_resource
        import os
        if os.getenv("DATA_GOV_API_KEY", "YOUR_API_KEY_HERE") != "YOUR_API_KEY_HERE":
            for r in RESOURCES:
                download_resource(r)
        else:
            log.warning("DATA_GOV_API_KEY not set — skipping data.gov.in")
    except Exception as e:
        log.error(f"data.gov.in download failed: {e}")

    # 1c. Kaggle
    try:
        from scrapers.kaggle_dl import DATASETS, download_dataset, setup_kaggle_auth
        setup_kaggle_auth()
        for ds in DATASETS:
            download_dataset(ds["slug"], ds["name"])
    except Exception as e:
        log.error(f"Kaggle download failed: {e} (set KAGGLE_USERNAME + KAGGLE_KEY in .env)")


def step_parse():
    log.info("---------------------------------------------------")
    log.info("STEP 2 - Parsing & normalizing")
    log.info("---------------------------------------------------")
    from parsers.normalize import run
    run()


def step_load(reset: bool = False):
    log.info("---------------------------------------------------")
    log.info("STEP 3 - Loading into PostgreSQL")
    log.info("---------------------------------------------------")
    from db.loader import main
    main(reset=reset)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=["scrape", "parse", "load"],
                        help="Run only one step")
    parser.add_argument("--reset-db", action="store_true",
                        help="Drop and recreate DB tables before loading")
    parser.add_argument("--max", type=int, default=None,
                        help="Max schemes to scrape from myscheme (for testing)")
    args = parser.parse_args()

    if args.step == "scrape":
        step_scrape(max_schemes=args.max)
    elif args.step == "parse":
        step_parse()
    elif args.step == "load":
        step_load(reset=args.reset_db)
    else:
        # Full pipeline
        step_scrape(max_schemes=args.max)
        step_parse()
        step_load(reset=args.reset_db)

    log.info("Pipeline complete.")


if __name__ == "__main__":
    main()

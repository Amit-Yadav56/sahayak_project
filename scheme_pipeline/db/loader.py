"""
db/loader.py — Load normalized schemes into your EXISTING PostgreSQL table
=============================================================================
Your `schemes` table already exists (it's referenced by saved_schemes via
a foreign key), so this script only INSERTs/UPDATEs the columns that are
already there. It never creates or drops your table.

Columns written: name, ministry, category, subcategory, state, description,
benefit_type, benefit_amount, how_to_apply, documents_required,
application_url, deadline, is_active, eligibility_json, eligibility_summary,
last_updated.

Run directly:
    python -m db.loader              # upsert all normalized schemes
    python -m db.loader --dry-run    # print what would happen, don't write

Called from pipeline.py via:
    from db.loader import main
    main(reset=reset)
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

INPUT_FILE = Path("data/processed/schemes_normalized.json")


# ── DB connection ─────────────────────────────────────────────────────────────

def get_conn():
    """
    Returns a psycopg2 connection using env vars from .env
    Set DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD in .env
    """
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "sahayak"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


# ── Build eligibility_summary from the structured dict ────────────────────────

def build_eligibility_summary(elig: dict) -> str:
    """
    Your table has a separate `eligibility_summary` varchar(255) column —
    a short human-readable line, distinct from the full eligibility_json.
    """
    parts = []

    age = elig.get("age", {})
    if age.get("min") and age.get("max"):
        parts.append(f"Age {age['min']}-{age['max']}")
    elif age.get("min"):
        parts.append(f"Age {age['min']}+")
    elif age.get("max"):
        parts.append(f"Age up to {age['max']}")

    gender = elig.get("gender", "all")
    if gender != "all":
        parts.append(gender.capitalize())

    caste = elig.get("caste", [])
    if caste:
        parts.append("/".join(caste))

    income = elig.get("income_limit", {})
    if income.get("bpl_only"):
        parts.append("BPL only")
    elif income.get("annual_inr"):
        parts.append(f"Income ≤ ₹{income['annual_inr']:,}")

    state = elig.get("state", "all")
    if state and state != "all":
        parts.append(state)

    summary = " · ".join(parts) if parts else "Open to all"
    return summary[:255]  # respect varchar(255) limit


# ── Map a normalized scheme dict onto your exact table columns ────────────────

def prepare_row(scheme: dict) -> dict:
    """
    Columns NOT in your table (source, slug, raw_json, etc.) are dropped here —
    they don't exist in `schemes`, so we never try to write them.
    """
    elig = scheme.get("eligibility_json", {})

    return {
        "name":                scheme["name"][:255],
        "ministry":            (scheme.get("ministry") or "")[:255],
        "category":            (scheme.get("category") or "")[:255],
        "subcategory":         (scheme.get("subcategory") or "")[:255],
        "state":               (scheme.get("state") or "Central")[:255],
        "description":         scheme.get("description") or "",
        "benefit_type":        (scheme.get("benefit_type") or "")[:255],
        "benefit_amount":      (scheme.get("benefit_amount") or "")[:255],
        "how_to_apply":        scheme.get("application_process") or scheme.get("how_to_apply") or "",
        "documents_required":  scheme.get("documents_required") or "",
        "application_url":     (scheme.get("application_url") or "")[:255],
        "deadline":            scheme.get("deadline"),  # None is fine, column is nullable
        "is_active":           scheme.get("is_active", True),
        # Your column is TEXT, not JSONB — store a JSON *string*, not psycopg2.extras.Json
        "eligibility_json":    json.dumps(elig, ensure_ascii=False),
        "eligibility_summary": build_eligibility_summary(elig),
    }


# ── Upsert logic ────────────────────────────────────────────────────────────
#
# Your table has NO unique constraint on `name` (only PRIMARY KEY on `id`),
# so a SQL-level ON CONFLICT upsert isn't available unless you add one
# (see db/schema.sql for the optional ALTER TABLE). Until then, we do the
# existence check in Python: SELECT by name, then INSERT or UPDATE.

SELECT_BY_NAME_SQL = "SELECT id FROM schemes WHERE name = %(name)s LIMIT 1;"

UPDATE_SQL = """
UPDATE schemes SET
    ministry            = %(ministry)s,
    category             = %(category)s,
    subcategory          = %(subcategory)s,
    state                 = %(state)s,
    description           = %(description)s,
    benefit_type          = %(benefit_type)s,
    benefit_amount        = %(benefit_amount)s,
    how_to_apply          = %(how_to_apply)s,
    documents_required    = %(documents_required)s,
    application_url       = %(application_url)s,
    deadline              = %(deadline)s,
    is_active             = %(is_active)s,
    eligibility_json       = %(eligibility_json)s,
    eligibility_summary    = %(eligibility_summary)s,
    last_updated           = NOW()
WHERE id = %(id)s;
"""

INSERT_SQL = """
INSERT INTO schemes (
    name, ministry, category, subcategory, state,
    description, benefit_type, benefit_amount,
    how_to_apply, documents_required, application_url,
    deadline, is_active, eligibility_json, eligibility_summary,
    last_updated
) VALUES (
    %(name)s, %(ministry)s, %(category)s, %(subcategory)s, %(state)s,
    %(description)s, %(benefit_type)s, %(benefit_amount)s,
    %(how_to_apply)s, %(documents_required)s, %(application_url)s,
    %(deadline)s, %(is_active)s, %(eligibility_json)s, %(eligibility_summary)s,
    NOW()
)
RETURNING id;
"""

# ── If you add a UNIQUE constraint on name later (see schema.sql), use this ──
# UPSERT_SQL = """
# INSERT INTO schemes (
#     name, ministry, category, subcategory, state,
#     description, benefit_type, benefit_amount,
#     how_to_apply, documents_required, application_url,
#     deadline, is_active, eligibility_json, eligibility_summary,
#     last_updated
# ) VALUES (
#     %(name)s, %(ministry)s, %(category)s, %(subcategory)s, %(state)s,
#     %(description)s, %(benefit_type)s, %(benefit_amount)s,
#     %(how_to_apply)s, %(documents_required)s, %(application_url)s,
#     %(deadline)s, %(is_active)s, %(eligibility_json)s, %(eligibility_summary)s,
#     NOW()
# )
# ON CONFLICT (name) DO UPDATE SET
#     ministry = EXCLUDED.ministry, category = EXCLUDED.category,
#     subcategory = EXCLUDED.subcategory, state = EXCLUDED.state,
#     description = EXCLUDED.description, benefit_type = EXCLUDED.benefit_type,
#     benefit_amount = EXCLUDED.benefit_amount, how_to_apply = EXCLUDED.how_to_apply,
#     documents_required = EXCLUDED.documents_required, application_url = EXCLUDED.application_url,
#     deadline = EXCLUDED.deadline, is_active = EXCLUDED.is_active,
#     eligibility_json = EXCLUDED.eligibility_json, eligibility_summary = EXCLUDED.eligibility_summary,
#     last_updated = NOW()
# RETURNING id;
# """


def upsert_one(cur, row: dict) -> tuple[int, str]:
    """
    Check if a scheme with this name exists; UPDATE if so, INSERT if not.
    Returns (id, action) where action is 'inserted' or 'updated'.
    """
    cur.execute(SELECT_BY_NAME_SQL, row)
    existing = cur.fetchone()

    if existing:
        row["id"] = existing["id"]
        cur.execute(UPDATE_SQL, row)
        return existing["id"], "updated"
    else:
        cur.execute(INSERT_SQL, row)
        new_id = cur.fetchone()["id"]
        return new_id, "inserted"


def load_schemes(conn, schemes: list[dict], dry_run: bool = False) -> dict:
    """Load all schemes, return counts."""
    stats = {"inserted": 0, "updated": 0, "failed": 0}

    with conn.cursor() as cur:
        for i, scheme in enumerate(schemes, 1):
            try:
                row = prepare_row(scheme)

                if dry_run:
                    log.info(f"[DRY RUN] Would upsert: {row['name']}")
                    log.info(f"  eligibility_summary: {row['eligibility_summary']}")
                    log.info(f"  eligibility_json: {row['eligibility_json'][:150]}...")
                    continue

                _, action = upsert_one(cur, row)
                stats[action] += 1

                if i % 100 == 0:
                    conn.commit()
                    log.info(f"  Progress: {i}/{len(schemes)} processed")

            except Exception as e:
                log.error(f"Failed on '{scheme.get('name', '?')}': {e}")
                stats["failed"] += 1
                conn.rollback()
                continue

        if not dry_run:
            conn.commit()

    return stats


# ── Verification ──────────────────────────────────────────────────────────────

def verify(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM schemes")
        total = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS active FROM schemes WHERE is_active = true")
        active = cur.fetchone()["active"]

        cur.execute("""
            SELECT name, ministry, eligibility_summary
            FROM schemes
            WHERE eligibility_json::text LIKE %s
            LIMIT 5
        """, ('%"gender": "female"%',))
        sample = cur.fetchall()

    log.info(f"\n{'='*50}")
    log.info(f"Total schemes in DB: {total}  (active: {active})")
    log.info("Sample female-eligible schemes:")
    for row in sample:
        log.info(f"  {row['name']} — {row['eligibility_summary']}")
    log.info(f"{'='*50}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main(reset: bool = False, dry_run: bool = False):
    """
    reset: kept for compatibility with pipeline.py's call signature.
           Your table already exists and is referenced by a foreign key
           (saved_schemes), so this NEVER drops or recreates it — reset
           is accepted but ignored, with a warning if True.
    """
    if reset:
        log.warning(
            "--reset-db was passed, but loader.py never drops your `schemes` "
            "table (it's referenced by saved_schemes via FK). Ignoring reset "
            "and proceeding with a normal upsert."
        )

    if not INPUT_FILE.exists():
        raise SystemExit(f"Input not found: {INPUT_FILE}\nRun parsers/normalize.py first.")

    schemes = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    log.info(f"Loaded {len(schemes)} normalized schemes from {INPUT_FILE}")

    conn = get_conn()
    log.info(f"Connected to PostgreSQL: {os.getenv('DB_NAME', 'sahayak')}@{os.getenv('DB_HOST', 'localhost')}")

    try:
        stats = load_schemes(conn, schemes, dry_run=dry_run)
        log.info(f"Done. Inserted: {stats['inserted']}, Updated: {stats['updated']}, Failed: {stats['failed']}")

        if not dry_run:
            verify(conn)

    finally:
        conn.close()
        log.info("Connection closed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load schemes into your existing PostgreSQL schemes table")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen, don't write to DB")
    parser.add_argument("--reset", action="store_true", help="Accepted for CLI symmetry, but ignored — see main() docstring")
    args = parser.parse_args()
    main(reset=args.reset, dry_run=args.dry_run)

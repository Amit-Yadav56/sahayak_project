"""
STEP 2 — Parse & Normalize
===========================
Reads raw JSON/CSV from data/raw/ and produces unified dicts ready for PostgreSQL.
Key output: the `eligibility_json` JSONB field with a consistent schema.

Run:  python -m parsers.normalize
Output: data/processed/schemes_normalized.json
"""

import json
import logging
import re
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

RAW_DIR       = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
OUTPUT_FILE   = PROCESSED_DIR / "schemes_normalized.json"


# ── Eligibility JSON schema ────────────────────────────────────────────────────
#
#  This is the canonical shape stored in the `eligibility_json` JSONB column.
#  All sources are mapped INTO this shape.
#
#  {
#    "age":           { "min": int|null, "max": int|null },
#    "gender":        "all" | "male" | "female" | "transgender",
#    "income_limit":  { "annual_inr": int|null, "bpl_only": bool },
#    "caste":         [ "SC" | "ST" | "OBC" | "EWS" | "General" ],  # [] = all
#    "state":         "all" | "Tamil Nadu" | ...,
#    "occupation":    [ "farmer" | "student" | "widow" | "disabled" | ... ],
#    "disability":    bool,
#    "residence":     "all" | "rural" | "urban",
#  }

def empty_eligibility() -> dict:
    return {
        "age":          {"min": None, "max": None},
        "gender":       "all",
        "income_limit": {"annual_inr": None, "bpl_only": False},
        "caste":        [],
        "state":        "all",
        "occupation":   [],
        "disability":   False,
        "residence":    "all",
    }


# ── Field extraction helpers ───────────────────────────────────────────────────

def parse_age(raw_age) -> dict:
    """
    Parse age from various raw formats:
      "18-60 years"  → {"min": 18, "max": 60}
      "Above 18"     → {"min": 18, "max": None}
      "Below 60"     → {"min": None, "max": 60}
      60             → {"min": None, "max": 60}
    """
    out = {"min": None, "max": None}
    if not raw_age:
        return out
    s = str(raw_age).lower().strip()

    # Only parse numbers that appear in an age-specific context.
    # This prevents unrelated numbers in descriptions from being treated as ages.
    age_contexts = [
        s,
        s[s.find("age"):] if "age" in s else "",
        s[s.find("ages"):] if "ages" in s else "",
    ]

    # "18-60" or "18 to 60"
    for context in age_contexts:
        if not context:
            continue
        m = re.search(r"(?:age|ages?)\D{0,40}(\d+)\s*(?:-|to)\s*(\d+)", context)
        if m:
            out["min"], out["max"] = int(m.group(1)), int(m.group(2))
            return out

    # "above 18" / "minimum 18"
    for context in age_contexts:
        if not context:
            continue
        m = re.search(r"(?:age|ages?)\D{0,40}(?:above|min(?:imum)?|from|over|at\s+least|>)\s*(\d+)", context)
        if m:
            out["min"] = int(m.group(1))
            return out

    # "below 60" / "upto 60" / "maximum 60"
    for context in age_contexts:
        if not context:
            continue
        m = re.search(r"(?:age|ages?)\D{0,40}(?:below|upto|up to|max(?:imum)?|under|<|not\s+more\s+than)\s*(\d+)", context)
        if m:
            out["max"] = int(m.group(1))
            return out

    # "age 19 years" or "age 19"
    for context in age_contexts:
        if not context:
            continue
        m = re.search(r"(?:age|ages?)\D{0,40}(\d+)\s*(?:years?|yrs?)?\b", context)
        if m:
            out["max"] = int(m.group(1))
            return out

    return out


def parse_gender(raw) -> str:
    if not raw:
        return "all"
    s = str(raw).lower()
    # Word boundaries prevent "men" matching inside "emergency", "department",
    # "government", etc. Check female before male since "female" contains "male".
    if re.search(r"\bfemales?\b|\bwomen\b|\bwoman\b|\bgirls?\b", s):
        return "female"
    if re.search(r"\bmales?\b|\bmen\b|\bman\b|\bboys?\b", s):
        return "male"
    if re.search(r"\btransgenders?\b|\btrans\b", s):
        return "transgender"
    return "all"


def parse_caste(raw) -> list[str]:
    if not raw:
        return []
    s = str(raw).upper()
    categories = []
    # Use \b word boundaries so "ST" doesn't match inside "RESIDENT",
    # "GEN" doesn't match inside "GENERATION", etc.
    if re.search(r"\bSC\b", s):              categories.append("SC")
    if re.search(r"\bST\b", s):              categories.append("ST")
    if re.search(r"\bOBC\b", s):             categories.append("OBC")
    if re.search(r"\bEWS\b", s):             categories.append("EWS")
    if re.search(r"\bGENERAL\s+CATEGORY\b|\bGEN\.?\s+CATEGORY\b", s):
        categories.append("General")
    return categories


def is_scheme_active(close_date_str) -> bool:
    """
    A scheme is active if it has no close date, or the close date is
    today or in the future. (Previous version incorrectly treated
    ANY close date as inactive, even future ones.)
    """
    if not close_date_str:
        return True
    try:
        from datetime import date
        close_date = date.fromisoformat(str(close_date_str)[:10])
        return close_date >= date.today()
    except (ValueError, TypeError):
        # Unparseable date string — default to active rather than silently dropping schemes
        return True


def parse_income(raw_income) -> dict:
    out = {"annual_inr": None, "bpl_only": False}
    if not raw_income:
        return out
    s = str(raw_income).lower()

    if "bpl" in s:
        out["bpl_only"] = True

    # look for a number (handle "2,50,000" → 250000)
    clean = re.sub(r"[,\s]", "", s)
    m = re.search(r"(\d+)", clean)
    if m:
        out["annual_inr"] = int(m.group(1))
    return out


def parse_residence(raw) -> str:
    if not raw:
        return "all"
    s = str(raw).lower()
    if "rural" in s:
        return "rural"
    if "urban" in s:
        return "urban"
    return "all"


# ── Source-specific parsers ────────────────────────────────────────────────────

def parse_benefit_type(raw_benefits: str) -> str:
    """Classify the benefit into a short type label your `benefit_type` column expects."""
    if not raw_benefits:
        return ""
    s = raw_benefits.lower()
    if "stipend" in s:
        return "Stipend"
    if "loan" in s or "credit" in s:
        return "Loan"
    if "insurance" in s or "cover" in s:
        return "Insurance"
    if "pension" in s:
        return "Pension"
    if "scholarship" in s:
        return "Scholarship"
    if "subsidy" in s:
        return "Subsidy"
    if "kit" in s or "in kind" in s or "free" in s:
        return "In-kind"
    if "₹" in raw_benefits or "rs." in s or "rs " in s:
        return "Cash assistance"
    return "Other"


def extract_benefit_amount(raw_benefits: str) -> str:
    """
    Pull the first rupee amount mentioned, as a short string for `benefit_amount`.
    Keeps the original phrasing rather than parsing to a number — amounts vary
    too much in shape (lump sum, monthly, percentage) to safely normalize.
    """
    if not raw_benefits:
        return ""
    m = re.search(r"₹\s?[\d,]+(?:\.\d+)?(?:/-|\s*(?:lakh|crore|per\s+\w+))?", raw_benefits, re.IGNORECASE)
    if m:
        return m.group(0).strip()[:255]
    return ""


def extract_application_process(*candidates: str) -> str:
    """
    Pull a process/how-to-apply style description from verbose source text.

    If the source already provides an explicit application_process field, that
    should win. Otherwise this returns a cleaned fallback only when the text
    looks like actual instructions (visit/apply/submit/register/etc.).
    """
    process_hints = (
        r"\bapply\b",
        r"\bapplication\b",
        r"\bvisit\b",
        r"\bsubmit\b",
        r"\bregister\b",
        r"\bportal\b",
        r"\bonline\b",
        r"\boffline\b",
        r"\bdownload\b",
        r"\bfill\b",
        r"\bcontact\b",
        r"\bstep\b",
    )

    for raw in candidates:
        if not raw:
            continue

        text = re.sub(r"\s+", " ", str(raw)).strip()
        if not text:
            continue

        lowered = text.lower()
        if any(re.search(pattern, lowered) for pattern in process_hints):
            return text

    return ""


def parse_myscheme_live_record(raw: dict) -> dict | None:
    """
    Map one record from the LIVE myscheme.gov.in search API (scrapers/myscheme.py)
    into a normalized scheme dict.

    This endpoint (/search/v6/schemes) only returns LISTING fields — there is
    no eligibility, benefits, application_process, or documents_required here.
    Shape produced by normalize_item() in scrapers/myscheme.py:

        id, slug, scheme_name, short_title, level, scheme_for, ministry,
        categories, states, description, tags, close_date, priority

    Because eligibility text simply isn't present in this payload,
    eligibility_json comes back mostly empty (just state, if available).
    Use this as a freshness/discovery source — combine with the Kaggle CSV
    (which has full eligibility text) via merge_live_with_kaggle() in run().
    """
    if not raw:
        return None

    el = empty_eligibility()

    # states is a list in this API (e.g. ["Tamil Nadu"] or ["All"])
    states = raw.get("states") or []
    if isinstance(states, list) and states:
        first_state = str(states[0]).strip()
        el["state"] = first_state if first_state.lower() != "all" else "all"

    el["age"] = parse_age(raw.get("description") or raw.get("short_title") or "")

    # categories is a list here too (e.g. ["Agriculture", "Social welfare"])
    cats = raw.get("categories") or []
    primary_category = str(cats[0]).strip() if isinstance(cats, list) and cats else ""

    return {
        "source":             "myscheme_live",
        "source_id":          str(raw.get("id") or raw.get("slug") or ""),
        "slug":               raw.get("slug") or "",
        "name":               raw.get("scheme_name") or "",
        "ministry":           raw.get("ministry") or "",
        "department":         "",
        "category":           primary_category,
        "subcategory":        "",
        "description":        raw.get("description") or "",
        "benefits":           "",
        "benefit_type":       "",
        "benefit_amount":     "",
        "application_process": extract_application_process(raw.get("description")),
        "documents_required": "",
        "application_url":    f"https://www.myscheme.gov.in/schemes/{raw.get('slug')}" if raw.get("slug") else "",
        "deadline":           raw.get("close_date") or None,
        "is_active":          is_scheme_active(raw.get("close_date")),
        "state":              el["state"],
        "eligibility_json":   el,  # mostly empty — only state is known
        "raw_json":           raw,
    }


def parse_myscheme_record(raw: dict) -> dict | None:
    """
    Map one myscheme.gov.in CSV row → normalized scheme dict.

    Matches the 27-column export format, e.g.:
    slug, scheme_name, short_title, level, state, ministry, department,
    beneficiary_type, target_beneficiaries, benefit_type, categories,
    sub_categories, tags, brief_description, detailed_description,
    benefits, eligibility, exclusions, application_mode,
    application_process, documents_required, references,
    scheme_open_date, scheme_close_date, dbt_scheme, faq_count, source_url
    """
    if not raw:
        return None

    eligibility_text = raw.get("eligibility") or ""
    benefits_text     = raw.get("benefits") or ""

    # ── build eligibility_json from the semicolon-delimited eligibility text ───
    # Dataset's eligibility field is semicolon-delimited into separate clauses
    # (e.g. "age 18-60 years; resident of X; income below Rs 2,50,000").
    # We scope each parser to clauses that look relevant to it, rather than
    # running every parser on the full combined text — otherwise parse_income
    # would grab the "18" out of an age clause, etc.
    el = empty_eligibility()
    clauses = [c.strip() for c in eligibility_text.split(";") if c.strip()]
    combined = " ".join(clauses)

    age_clauses    = [c for c in clauses if re.search(r"\bage\b|\byears?\b|\byrs?\b", c, re.IGNORECASE)]
    income_clauses = [c for c in clauses if re.search(r"\bincome\b|\bbpl\b|\bAPL\b|₹|\brs\.?\b", c, re.IGNORECASE)]

    el["age"]          = parse_age(" ".join(age_clauses) or combined)
    el["gender"]       = parse_gender(combined)
    el["caste"]        = parse_caste(combined)
    el["income_limit"] = parse_income(" ".join(income_clauses))  # empty string if no income clause found — correctly yields {annual_inr: None}
    el["state"]        = (raw.get("state") or "all").strip() or "all"
    el["residence"]    = parse_residence(combined)
    el["disability"]   = "disab" in combined.lower()
    el["age"]          = parse_age(" ".join(age_clauses) or combined or raw.get("description") or raw.get("detailed_description") or raw.get("brief_description") or "")

    btype = raw.get("beneficiary_type") or raw.get("target_beneficiaries") or ""
    el["occupation"] = [t.strip().lower() for t in str(btype).split(";") if t.strip()]

    # ── categories: "categories" is a Python-list-style string in some exports ──
    cats = raw.get("categories") or raw.get("category") or ""
    cats = cats.strip("[]").replace("'", "").strip()
    primary_category = cats.split(",")[0].strip() if cats else ""

    subcats = raw.get("sub_categories") or raw.get("subcategory") or ""
    subcats = subcats.strip("[]").replace("'", "").strip()
    primary_subcategory = subcats.split(",")[0].strip() if subcats else ""

    return {
        "source":             "myscheme",
        "source_id":          str(raw.get("id") or raw.get("slug") or ""),
        "slug":               raw.get("slug") or "",
        "name":               raw.get("scheme_name") or raw.get("name") or "",
        "ministry":           raw.get("ministry") or "",
        "department":         raw.get("department") or "",
        "category":           primary_category,
        "subcategory":        primary_subcategory,
        "description":        raw.get("detailed_description") or raw.get("brief_description") or raw.get("description") or "",
        "benefits":           benefits_text,
        "benefit_type":       raw.get("benefit_type") or parse_benefit_type(benefits_text),
        "benefit_amount":     extract_benefit_amount(benefits_text),
        "application_process": raw.get("application_process") or extract_application_process(
            raw.get("detailed_description"),
            raw.get("brief_description"),
            raw.get("description"),
        ),
        "documents_required": raw.get("documents_required") or "",
        "application_url":    raw.get("source_url") or raw.get("application_url") or "",
        "deadline":           raw.get("scheme_close_date") or None,
        "is_active":          is_scheme_active(raw.get("scheme_close_date")),
        "state":              raw.get("state") or "Central",
        "eligibility_json":   el,
        "raw_json":           raw,
    }


def parse_datagovin_record(raw: dict, resource_name: str) -> dict | None:
    """
    Map one data.gov.in record → normalized scheme dict.
    Field names vary by dataset — inspect your downloaded JSON to calibrate.
    """
    if not raw:
        return None

    el = empty_eligibility()

    # Common field patterns in data.gov.in scheme datasets
    el["state"]        = raw.get("state_name") or raw.get("state") or "all"
    el["gender"]       = parse_gender(raw.get("gender") or raw.get("beneficiary"))
    el["income_limit"] = parse_income(raw.get("income_limit") or raw.get("annual_income"))
    el["age"]          = parse_age(
        raw.get("age")
        or raw.get("age_limit")
        or raw.get("age_group")
        or raw.get("description")
        or raw.get("objective")
        or raw.get("benefits")
        or raw.get("benefit_details")
        or ""
    )

    return {
        "source":           "datagovin",
        "source_id":        str(raw.get("_id") or raw.get("sr_no") or ""),
        "slug":             "",
        "name":             raw.get("scheme_name") or raw.get("name") or "",
        "ministry":         raw.get("ministry") or raw.get("implementing_agency") or "",
        "department":       raw.get("department") or "",
        "category":         raw.get("category") or raw.get("sector") or "",
        "description":      raw.get("description") or raw.get("objective") or "",
        "benefits":         raw.get("benefits") or raw.get("benefit_details") or "",
        "application_process": extract_application_process(
            raw.get("application_process"),
            raw.get("how_to_apply"),
            raw.get("description"),
            raw.get("objective"),
            raw.get("benefits"),
            raw.get("benefit_details"),
        ),
        "application_url":  raw.get("apply_link") or raw.get("website") or "",
        "state":            raw.get("state_name") or "Central",
        "eligibility_json": el,
        "raw_json":         raw,
    }


def parse_kaggle_row(row: dict, filename: str) -> dict | None:
    """
    Map one row from a Kaggle CSV → normalized scheme dict.
    Column names vary — inspect the CSV header to calibrate.
    """
    el = empty_eligibility()
    el["state"]  = row.get("state") or row.get("State") or "all"
    el["gender"] = parse_gender(row.get("gender") or row.get("Gender") or row.get("beneficiary"))
    el["age"]    = parse_age(
        row.get("age")
        or row.get("Age")
        or row.get("description")
        or row.get("Description")
        or row.get("benefits")
        or row.get("Benefits")
        or row.get("eligibility")
        or row.get("Eligibility")
        or ""
    )

    return {
        "source":           "kaggle",
        "source_id":        str(row.get("id") or row.get("Scheme_ID") or ""),
        "slug":             "",
        "name":             row.get("scheme_name") or row.get("Scheme_Name") or row.get("name") or "",
        "ministry":         row.get("ministry") or row.get("Ministry") or "",
        "department":       row.get("department") or "",
        "category":         row.get("category") or row.get("Category") or "",
        "description":      row.get("description") or row.get("Description") or "",
        "benefits":         row.get("benefits") or row.get("Benefits") or "",
        "application_process": extract_application_process(
            row.get("application_process"),
            row.get("Application_Process"),
            row.get("description"),
            row.get("Description"),
            row.get("benefits"),
            row.get("Benefits"),
        ),
        "application_url":  row.get("link") or row.get("URL") or "",
        "state":            row.get("state") or row.get("State") or "Central",
        "eligibility_json": el,
        "raw_json":         row,
    }


# ── Deduplication ─────────────────────────────────────────────────────────────

def dedup(schemes: list[dict]) -> list[dict]:
    """
    Remove duplicate schemes by name (case-insensitive).
    Keeps the first occurrence; prefers 'myscheme' source over others.
    """
    seen   = {}
    result = []
    priority = {"myscheme": 0, "datagovin": 1, "kaggle": 2}

    # Sort so myscheme records win ties
    schemes.sort(key=lambda s: priority.get(s.get("source", ""), 9))

    for s in schemes:
        key = s["name"].lower().strip()
        if not key:
            continue
        if key not in seen:
            seen[key] = True
            result.append(s)
        else:
            log.debug(f"Dedup: skipping duplicate '{s['name']}' from {s['source']}")

    log.info(f"Dedup: {len(schemes)} → {len(result)} schemes")
    return result


# ── Merge: live API records (fresh, but listing-only) + Kaggle (rich eligibility) ──

def merge_live_with_kaggle(live_schemes: list[dict], kaggle_schemes: list[dict]) -> list[dict]:
    """
    The live myscheme.gov.in search API only returns listing fields — no
    eligibility, benefits, or application process. The Kaggle CSV has those,
    but may be stale (doesn't include schemes added after the CSV was built).

    Strategy: index Kaggle records by slug. For every live record, if a
    Kaggle record with the same slug exists, take Kaggle's rich fields
    (eligibility_json, benefits, application_process, documents_required)
    but keep the live record's close_date/is_active/category (more current).
    Live records with no Kaggle match are kept as-is (better than nothing,
    but eligibility_json will be mostly empty for those).
    Kaggle records with no live match are also kept (older schemes that
    might have been delisted from the live search, or just not paginated to).
    """
    kaggle_by_slug = {s["slug"]: s for s in kaggle_schemes if s.get("slug")}
    merged = []
    matched_slugs = set()

    for live in live_schemes:
        slug = live.get("slug")
        kaggle_match = kaggle_by_slug.get(slug) if slug else None

        if kaggle_match:
            matched_slugs.add(slug)
            combined = dict(kaggle_match)  # start from the rich Kaggle record
            # override with live data where it's more current
            combined["deadline"]   = live.get("deadline") or kaggle_match.get("deadline")
            combined["is_active"]  = live.get("is_active")
            combined["category"]  = live.get("category") or kaggle_match.get("category")
            combined["source"]     = "myscheme_merged"
            merged.append(combined)
        else:
            log.debug(f"No Kaggle match for live scheme slug='{slug}' — eligibility will be sparse")
            merged.append(live)

    # Kaggle records that the live API didn't return at all (older/delisted schemes)
    for slug, kaggle_scheme in kaggle_by_slug.items():
        if slug not in matched_slugs:
            merged.append(kaggle_scheme)

    log.info(
        f"Merge: {len(live_schemes)} live + {len(kaggle_schemes)} kaggle "
        f"→ {len(matched_slugs)} matched, {len(merged)} total after merge"
    )
    return merged


# ── Main ──────────────────────────────────────────────────────────────────────

def run() -> list[dict]:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    live_schemes   = []
    kaggle_schemes = []
    other_schemes  = []  # data.gov.in, anything else

    # ── 1a. myscheme.gov.in LIVE search API (scrapers/myscheme.py output) ────
    # This is JSON in the NEW shape: id, slug, scheme_name, short_title, level,
    # scheme_for, ministry, categories, states, description, tags, close_date,
    # priority — listing fields only, no eligibility text.
    myscheme_live_file = RAW_DIR / "myscheme_raw.json"
    if myscheme_live_file.exists():
        raw_list = json.loads(myscheme_live_file.read_text(encoding="utf-8"))
        parsed   = [parse_myscheme_live_record(r) for r in raw_list]
        parsed   = [p for p in parsed if p and p["name"]]
        log.info(f"myscheme (live API): parsed {len(parsed)} schemes")
        live_schemes.extend(parsed)
    else:
        log.warning(f"Not found: {myscheme_live_file} — run scrapers/myscheme.py first")

    # ── 1b. Kaggle CSV — rich shape with eligibility, benefits, etc. ─────────
    # Covers both data/raw/kaggle/**/*.csv (from kaggle_dl.py) and any
    # myscheme_*.csv dropped directly into data/raw/ (manual CSV export).
    kaggle_csv_paths = list((RAW_DIR / "kaggle").glob("**/*.csv")) + list(RAW_DIR.glob("myscheme_*.csv"))
    for csv_file in kaggle_csv_paths:
        try:
            df   = pd.read_csv(csv_file, dtype=str).fillna("")
            rows = df.to_dict("records")
            parsed = [parse_myscheme_record(r) for r in rows]
            parsed = [p for p in parsed if p and p["name"]]
            log.info(f"kaggle/{csv_file.name}: parsed {len(parsed)} schemes (rich eligibility)")
            kaggle_schemes.extend(parsed)
        except Exception as e:
            log.error(f"Failed to parse {csv_file}: {e}")

    # ── 2. data.gov.in ───────────────────────────────────────────────────────
    for f in RAW_DIR.glob("datagovin_*.json"):
        data     = json.loads(f.read_text(encoding="utf-8"))
        records  = data.get("records", [])
        resource = data.get("name", f.stem)
        parsed   = [parse_datagovin_record(r, resource) for r in records]
        parsed   = [p for p in parsed if p and p["name"]]
        log.info(f"datagovin/{resource}: parsed {len(parsed)} records")
        other_schemes.extend(parsed)


    # ── 3. Merge live API + Kaggle, then fold in anything else (data.gov.in) ──
    merged = merge_live_with_kaggle(live_schemes, kaggle_schemes)
    all_schemes = merged + other_schemes

    # ── Dedup & save ─────────────────────────────────────────────────────────
    final = dedup(all_schemes)
    OUTPUT_FILE.write_text(
        json.dumps(final, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    log.info(f"Saved {len(final)} normalized schemes → {OUTPUT_FILE}")

    # Print eligibility sample
    if final:
        log.info(f"Sample eligibility_json: {json.dumps(final[0]['eligibility_json'], indent=2)}")

    return final


if __name__ == "__main__":
    run()

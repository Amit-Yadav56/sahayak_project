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
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Model 2 (NER extractor) — optional, falls back to regex if unavailable ───
try:
    from ml.ner_extractor.extractor import extract_eligibility as _ml_extract_eligibility
    _ML_EXTRACTOR_AVAILABLE = True
except ImportError:
    _ML_EXTRACTOR_AVAILABLE = False

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
#    "education":     [ "8th standard" | "12th standard" | "graduate" | ... ],
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
        "education":    [],
        "caste":        [],
        "state":        "all",
        "occupation":   [],
        "disability":   False,
        "residence":    "all",
    }


def map_model2_output_to_eligibility(ml_result: dict, state_hint: str = "all") -> dict:
    """
    Map Model 2's (ml/ner_extractor/extractor.py) output shape onto the
    eligibility_json shape this pipeline already uses.

    Model 2 returns:
        {min_age, max_age, max_income, categories, gender,
            education, occupation, state, disability, is_widow, requires}

    eligibility_json expects:
        {age: {min, max}, gender, income_limit: {annual_inr, bpl_only},
            education, caste, state, occupation, disability, residence}
    """
    el = empty_eligibility()
    el["age"]["min"] = ml_result.get("min_age")
    el["age"]["max"] = ml_result.get("max_age")
    el["gender"]     = ml_result.get("gender") or "all"
    if el["gender"] == "any":
        el["gender"] = "all"  # Model 2 uses "any", eligibility_json uses "all" — keep consistent

    bpl_only = "bpl_certificate" in (ml_result.get("requires") or [])
    el["income_limit"]["bpl_only"]   = bpl_only
    # Model 2 sets max_income=0 as a BPL marker — don't store 0 as a real
    # income ceiling, store None and let bpl_only carry that meaning instead.
    max_income = ml_result.get("max_income")
    el["income_limit"]["annual_inr"] = max_income if (max_income and max_income > 0) else None

    el["caste"]      = ml_result.get("categories") or []
    el["education"]  = ml_result.get("education") or []
    el["state"]      = state_hint or "all"
    el["occupation"] = ml_result.get("occupation") or []
    el["disability"] = bool(ml_result.get("disability"))
    return el


# ── Field extraction helpers ───────────────────────────────────────────────────

def parse_age(raw_age) -> dict:
    """
    Parse age from various raw formats:
      "18-60 years"  → {"min": 18, "max": 60}
      "Above 18"     → {"min": 18, "max": None}
            "20 years and above" → {"min": 20, "max": None}
      "Below 60"     → {"min": None, "max": 60}
      60             → {"min": None, "max": 60}
    """
    out = {"min": None, "max": None}
    if not raw_age:
        return out
    s = str(raw_age).lower().strip()

    # "18-60" or "18 to 60"
    m = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)", s)
    if m:
        out["min"], out["max"] = int(m.group(1)), int(m.group(2))
        return out

    # "above 18" / "minimum 18"
    m = re.search(r"(?:above|min(?:imum)?|from|>)\s*(\d+)", s)
    if m:
        out["min"] = int(m.group(1))
        return out

    # "20 years and above" / "20 and above" / "20+ years"
    m = re.search(r"(\d+)\s*(?:years?|yrs?)?\s*(?:and\s+)?above", s)
    if m:
        out["min"] = int(m.group(1))
        return out

    # "below 60" / "upto 60" / "maximum 60"
    m = re.search(r"(?:below|upto|up to|max(?:imum)?|<)\s*(\d+)", s)
    if m:
        out["max"] = int(m.group(1))
        return out

    # bare number → treat as max
    m = re.search(r"(\d+)", s)
    if m:
        out["max"] = int(m.group(1))

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


def parse_education(raw_text) -> list[str]:
    if not raw_text:
        return []

    s = str(raw_text).lower()
    found = []

    patterns = [
        (r"\b(?:8th|eighth)\s+(?:standard|class|grade)\b|\bclass\s*8\b", "8th standard"),
        (r"\b(?:9th|ninth)\s+(?:standard|class|grade)\b|\bclass\s*9\b", "9th standard"),
        (r"\b(?:10th|tenth|ssc|matric|matriculation)\s+(?:standard|class|grade)?\b|\bclass\s*10\b|\b10\+2\b", "10th standard"),
        (r"\b(?:12th|twelfth|hsc|intermediate)\s+(?:standard|class|grade)?\b|\bclass\s*12\b|\b\+2\b", "12th standard"),
        (r"\bundergraduate\b|\bgraduat(?:e|ion)\b|\bdegree\b", "graduate"),
        (r"\bpost[-\s]?graduate\b|\bpg\b|\bmphil\b|\bphd\b", "postgraduate"),
        (r"\bdiploma\b", "diploma"),
        (r"\biti\b|\bindustrial training institute\b", "iti"),
        (r"\bpolytechnic\b", "polytechnic"),
    ]

    for pattern, label in patterns:
        if re.search(pattern, s):
            found.append(label)

    return sorted(set(found))


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
        "application_process": "",
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

    # ── build eligibility_json — Model 2 (NER extractor) first, regex fallback ──
    # Dataset's eligibility field is semicolon-delimited into separate clauses
    # (e.g. "age 18-60 years; resident of X; income below Rs 2,50,000").
    clauses = [c.strip() for c in eligibility_text.split(";") if c.strip()]
    combined = " ".join(clauses)
    state_value = (raw.get("state") or "all").strip() or "all"

    if _ML_EXTRACTOR_AVAILABLE and combined:
        ml_result = _ml_extract_eligibility(combined, state_hint=state_value)
        el = map_model2_output_to_eligibility(ml_result, state_hint=state_value)
        # residence isn't covered by Model 2 yet — keep using the regex helper for it
        el["residence"] = parse_residence(combined)
    else:
        # Fallback: original regex-based extraction (used if spaCy isn't
        # installed, or there's no eligibility text to run the model on).
        el = empty_eligibility()
        age_clauses    = [c for c in clauses if re.search(r"\bage\b|\byears?\b|\byrs?\b", c, re.IGNORECASE)]
        income_clauses = [c for c in clauses if re.search(r"\bincome\b|\bbpl\b|\bAPL\b|₹|\brs\.?\b", c, re.IGNORECASE)]

        el["age"]          = parse_age(" ".join(age_clauses) or combined)
        el["gender"]       = parse_gender(combined)
        el["caste"]        = parse_caste(combined)
        el["income_limit"] = parse_income(" ".join(income_clauses))
        el["education"]    = parse_education(combined)
        el["state"]        = state_value
        el["residence"]    = parse_residence(combined)
        el["disability"]   = "disab" in combined.lower()

    btype = raw.get("beneficiary_type") or raw.get("target_beneficiaries") or ""
    if not el["occupation"]:  # Model 2 may have already found occupations from text
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
        "application_process": raw.get("application_process") or "",
        "documents_required": raw.get("documents_required") or "",
        "application_url":    raw.get("source_url") or raw.get("application_url") or "",
        "deadline":           raw.get("scheme_close_date") or None,
        "is_active":          is_scheme_active(raw.get("scheme_close_date")),
        "state":              raw.get("state") or "Central",
        "eligibility_json":   el,
        "raw_json":           raw,
    }


def parse_kaggle_row(row: dict, filename: str) -> dict | None:
    """
    Map one row from a Kaggle CSV → normalized scheme dict.
    Column names vary — inspect the CSV header to calibrate.
    """
    el = empty_eligibility()
    el["state"]  = row.get("state") or row.get("State") or "all"
    el["gender"] = parse_gender(row.get("gender") or row.get("Gender") or row.get("beneficiary"))
    el["education"] = parse_education(
        row.get("eligibility") or row.get("eligibility_text") or row.get("eligibility_summary") or ""
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
    priority = {"myscheme_merged": 0, "myscheme": 1, "myscheme_live": 2, "kaggle": 3}

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

def run(max_records: int | None = None) -> list[dict]:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    live_schemes   = []
    kaggle_schemes = []

    # ── 1. myscheme.gov.in LIVE search API (scrapers/myscheme.py output) ─────
    # This is JSON in the shape: id, slug, scheme_name, short_title, level,
    # scheme_for, ministry, categories, states, description, tags, close_date,
    # priority — listing fields only, no eligibility text.
    myscheme_live_file = RAW_DIR / "myscheme_raw.json"
    if myscheme_live_file.exists():
        raw_list = json.loads(myscheme_live_file.read_text(encoding="utf-8"))
        if max_records:
            raw_list = raw_list[:max_records]
        parsed   = [parse_myscheme_live_record(r) for r in raw_list]
        parsed   = [p for p in parsed if p and p["name"]]
        log.info(f"myscheme (live API): parsed {len(parsed)} schemes")
        live_schemes.extend(parsed)
    else:
        log.warning(f"Not found: {myscheme_live_file} — run scrapers/myscheme.py first")

    # ── 2. Kaggle CSV — rich shape with eligibility, benefits, etc. ──────────
    # Covers both data/raw/kaggle/**/*.csv (from kaggle_dl.py) and any
    # myscheme_*.csv dropped directly into data/raw/ (manual CSV export).
    kaggle_csv_paths = list((RAW_DIR / "kaggle").glob("**/*.csv")) + list(RAW_DIR.glob("myscheme_*.csv"))
    for csv_file in kaggle_csv_paths:
        try:
            df   = pd.read_csv(csv_file, dtype=str).fillna("")
            rows = df.to_dict("records")
            if max_records:
                rows = rows[:max_records]
            parsed = [parse_myscheme_record(r) for r in rows]
            parsed = [p for p in parsed if p and p["name"]]
            log.info(f"kaggle/{csv_file.name}: parsed {len(parsed)} schemes (rich eligibility)")
            kaggle_schemes.extend(parsed)
        except Exception as e:
            log.error(f"Failed to parse {csv_file}: {e}")

    # ── 3. Merge live API + Kaggle ────────────────────────────────────────────
    all_schemes = merge_live_with_kaggle(live_schemes, kaggle_schemes)

    # ── Dedup & save ─────────────────────────────────────────────────────────
    final = dedup(all_schemes)
    if max_records:
        final = final[:max_records]
    OUTPUT_FILE.write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Saved {len(final)} normalized schemes → {OUTPUT_FILE}")

    # Print eligibility sample
    if final:
        log.info(f"Sample eligibility_json: {json.dumps(final[0]['eligibility_json'], indent=2)}")

    return final


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Normalize raw scheme data into structured JSON")
    parser.add_argument("--max", type=int, default=None, help="Limit normalization to the first N records for testing")
    args = parser.parse_args()

    run(max_records=args.max)

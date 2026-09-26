"""
parsers/canonicalize.py
=========================
Free text produces inconsistent strings for the same real-world value:
"Degree" vs "degree", "Class 10th" vs "Class 10" vs "10th standard",
"farmer" vs "farmers", "labourer" vs "laborer" vs "labourers" vs
"laborers". Every one of those is a different string in the DB today,
which means a search/filter UI for "Class 10" or "farmer" silently
misses records that mean the exact same thing but got phrased
differently in the source eligibility text.

This module canonicalizes those values AFTER extraction (rule-based or
NER), as a separate concern from extraction itself — extraction's job is
finding the right span of text; canonicalization's job is making sure
the same real-world value always serializes to the same string.

Run scripts/audit_consistency.py after any change here to confirm the
fix actually collapsed the duplicate-value counts in the real dataset,
not just in a unit test.
"""

import re

# --- Education ---

_CLASS_N_RE = re.compile(r"^class\s*(\d+)\s*(?:st|nd|rd|th)?\.?$", re.IGNORECASE)
_N_STANDARD_RE = re.compile(r"^(\d+)\s*(?:st|nd|rd|th)?\s*standard$", re.IGNORECASE)
# Reversed word order — "10th class", "12th grade", "12th pass" all mean
# the same thing as "class 12"/"10th standard". Deliberately requires a
# DIGIT (\d+), not a spelled-out ordinal — "First Class" / "First Class
# Honours" is an academic marks classification, not "Class 1", and must
# NOT be caught here.
_N_CLASS_OR_GRADE_RE = re.compile(r"^(\d+)\s*(?:st|nd|rd|th)?\s*(?:class|grade|pass|passed)$", re.IGNORECASE)

_EDUCATION_CANONICAL_MAP = {
    "post graduate": "postgraduate",
    "post-graduate": "postgraduate",
    "postgraduate": "postgraduate",
    "post graduation": "postgraduate",
    "post-graduation": "postgraduate",
    "graduation": "graduate",
    "graduate": "graduate",
    "undergraduate": "undergraduate",  # distinct from "graduate" — kept separate deliberately
    "phd": "phd",
    "ph.d": "phd",
    "ph.d.": "phd",
    "mphil": "mphil",
    "m.phil": "mphil",
    "diploma": "diploma",
    "12th standard": "class 12",
    "10+2": "class 12",
    "10 +2": "class 12",
    "matriculation": "class 10",
    "matric": "class 10",
}


def canonicalize_education(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for raw in values or []:
        v = (raw or "").strip().lower()
        if not v:
            continue

        m = _CLASS_N_RE.match(v)
        if m:
            v = f"class {int(m.group(1))}"
        else:
            m2 = _N_STANDARD_RE.match(v)
            if m2:
                v = f"class {int(m2.group(1))}"
            else:
                m3 = _N_CLASS_OR_GRADE_RE.match(v)
                if m3:
                    v = f"class {int(m3.group(1))}"
                else:
                    v = _EDUCATION_CANONICAL_MAP.get(v, v)

        if v not in seen:
            seen.add(v)
            out.append(v)
    return sorted(out)


# --- Occupation ---

_OCCUPATION_CANONICAL_MAP = {
    "farmers": "farmer", "farmer": "farmer",
    "students": "student", "student": "student",
    "widows": "widow", "widow": "widow",
    "entrepreneurs": "entrepreneur", "entrepreneur": "entrepreneur",
    "artisans": "artisan", "artisan": "artisan",
    "weavers": "weaver", "weaver": "weaver",
    "fishermen": "fisherman", "fisherman": "fisherman", "fisherwoman": "fisherman",
    # gender is already tracked in its own field — collapsing fisherman/
    # fisherwoman into one occupation string doesn't lose that information.
    "labourers": "labourer", "labourer": "labourer",
    "laborers": "labourer", "laborer": "labourer",
    "athletes": "athlete", "athlete": "athlete",
    "sportspersons": "sportsperson", "sportsperson": "sportsperson",
    "agricultural labourer": "agricultural_labourer",
    "agricultural labourers": "agricultural_labourer",
    "agricultural laborer": "agricultural_labourer",
    "agricultural laborers": "agricultural_labourer",
    "self-employed": "self_employed",
    "self employed": "self_employed",
    "self help groups (shgs)": "self_help_group",
    "self help group": "self_help_group",
}

# Beneficiary-TYPE classifications (from the CSV's beneficiary_type /
# target_beneficiaries columns, used as a fallback when extraction finds
# no real occupation in the text) — these describe WHO can apply
# structurally (an individual vs. an organization vs. an infrastructure
# project), not a real occupation. Leaving them in "occupation" pollutes
# the field for search: a filter for occupation=farmer shouldn't also
# need to know "individual" is a near-universal non-signal that matches
# almost every record.
NON_OCCUPATION_VALUES = {
    "individual", "family", "infra", "group", "institution",
    "joint liability groups (jlgs)", "business entity",
    "university / institution", "ngo", "organisation", "organization",
    "trust", "society", "company", "enterprise", "association",
}


def canonicalize_occupation(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for raw in values or []:
        v = (raw or "").strip().lower()
        if not v:
            continue
        v = _OCCUPATION_CANONICAL_MAP.get(v, v)
        if v not in seen:
            seen.add(v)
            out.append(v)
    return sorted(out)


def filter_non_occupation_fallback(values: list[str]) -> list[str]:
    """Drop generic beneficiary-type values (individual/infra/family/...)
    from a beneficiary_type-derived fallback list — these aren't
    occupations and shouldn't be searchable as one."""
    return [v for v in (values or []) if v.strip().lower() not in NON_OCCUPATION_VALUES]

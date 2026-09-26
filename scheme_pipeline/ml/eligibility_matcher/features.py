"""
ml/eligibility_matcher/features.py
=====================================
Converts a (user_profile, scheme_eligibility_json) pair into a flat
numeric feature vector for XGBoost.

Two categories of features:

1. MATCH SIGNALS — direct comparison of user vs scheme constraint.
   Each match signal is:
     1.0  = clear match (or scheme has no constraint → open)
     0.5  = scheme has no constraint (ambiguous — model learns whether
             this matters for this type of scheme)
     0.0  = clear mismatch (hard constraint violated)
   These are the most important features — the model is essentially
   learning a weighted combination of these match signals, which is
   why it handles partial matches and null constraints better than
   a simple AND-of-rules filter.

2. RAW FEATURES — user values and scheme properties in their natural
   form, so the model can learn things like "high-income users need
   lower scores regardless of the specific income limit" or "central
   schemes are more broadly applicable."

User profile schema (dict):
    age             int         — applicant's age in years
    gender          str         — "male" / "female" / "other"
    state           str         — state name, e.g. "Tamil Nadu"
    annual_income   int         — annual family income in INR
    income_source   str         — "farmer" / "labourer" / "salaried" / "self_employed" / "unemployed" / "other"
    caste_category  str         — "General" / "OBC" / "SC" / "ST" / "EWS"
    disability      bool
    is_widow        bool
    education_level str         — canonical value from canonicalize.py, e.g. "class 10" / "graduate"
    has_bank_account bool
    has_aadhar       bool
    land_ownership  float       — acres (0.0 if none)
    has_house       bool
    children_count  int
"""

import math
from typing import Any

import numpy as np

# --- Education level ordering (for ordinal comparison) ---
_EDUCATION_ORDER = {
    "none": 0,
    "class 1": 1, "class 2": 2, "class 3": 3, "class 4": 4, "class 5": 5,
    "class 6": 6, "class 7": 7, "class 8": 8, "class 9": 9,
    "class 10": 10, "class 11": 11, "class 12": 12,
    "diploma": 13,
    "undergraduate": 14,
    "graduate": 15,
    "postgraduate": 16,
    "phd": 17,
}

def _edu_level(v: str) -> int:
    return _EDUCATION_ORDER.get((v or "none").lower().strip(), 15)  # default: graduate-level


# --- Caste hierarchy for partial matching ---
# SC/ST are a subset of OBC in many schemes' spirit — a scheme targeting
# SC/ST should score higher for SC/ST users than for General users even
# if OBC isn't listed. The model learns this from data, but we give it
# an explicit partial-match signal to start from.
_CASTE_ORDER = {"General": 0, "EWS": 1, "OBC": 2, "ST": 3, "SC": 3}

def _caste_partial_score(user_caste: str, scheme_castes: list) -> float:
    """
    1.0 → user caste is in scheme's caste list (full match)
    0.5 → scheme has no caste restriction (open to all)
    0.3 → user caste is SC/ST but scheme only lists OBC (or vice versa — partial)
    0.0 → user is General/EWS but scheme requires SC/ST/OBC
    """
    if not scheme_castes:
        return 0.5  # no constraint
    uc = (user_caste or "General").upper()
    if uc in [c.upper() for c in scheme_castes]:
        return 1.0
    # SC/ST user for OBC scheme — partial benefit
    if uc in ("SC", "ST") and any(c.upper() == "OBC" for c in scheme_castes):
        return 0.3
    if uc == "GENERAL":
        return 0.0
    if uc == "EWS":
        # EWS is its own category — if not listed, no match
        return 0.0 if "EWS" not in [c.upper() for c in scheme_castes] else 1.0
    return 0.0


# --- Income mapping ---
_INCOME_SOURCE_TO_OCCUPATION = {
    "farmer": {"farmer", "agricultural_labourer"},
    "labourer": {"labourer", "agricultural_labourer", "construction"},
    "salaried": set(),
    "self_employed": {"entrepreneur", "self_employed"},
    "unemployed": {"unemployed"},
    "other": set(),
}


def _occupation_match(income_source: str, scheme_occupations: list) -> float:
    if not scheme_occupations:
        return 0.5  # no constraint
    user_set = _INCOME_SOURCE_TO_OCCUPATION.get((income_source or "other").lower(), set())
    scheme_set = {o.lower() for o in scheme_occupations}
    # student is in scheme_occupations — user may be a student too (income_source won't say "student")
    # treat "student" as open (0.5) since we don't have that field in the user profile
    if "student" in scheme_set and len(scheme_set) == 1:
        return 0.5
    if user_set & scheme_set:
        return 1.0
    return 0.0


def _edu_match(user_edu: str, scheme_edu: list) -> float:
    """
    1.0 → user meets at least one of the scheme's education requirements
    0.5 → scheme has no education constraint
    0.3 → user is one level below the minimum listed
    0.0 → user is significantly below
    """
    if not scheme_edu:
        return 0.5
    user_level = _edu_level(user_edu)
    scheme_levels = [_edu_level(e) for e in scheme_edu]
    min_required = min(scheme_levels)
    if user_level >= min_required:
        return 1.0
    gap = min_required - user_level
    if gap == 1:
        return 0.3
    return 0.0


# --- Main feature builder ---

FEATURE_NAMES = [
    # Match signals
    "age_match",          "age_below_margin",    "age_above_margin",
    "gender_match",       "state_match",
    "income_match",       "income_ratio",
    "caste_match",        "disability_match",    "widow_match",
    "occupation_match",   "education_match",
    "aadhar_match",       "bank_match",
    "bpl_match",
    # Scheme constraint density (how strict is this scheme?)
    "n_constraints",      "has_age_constraint",  "has_income_constraint",
    "has_caste_constraint", "has_gender_constraint", "has_state_constraint",
    # Raw user features
    "user_age_norm",      "user_is_female",      "user_is_sc", "user_is_st",
    "user_is_obc",        "user_is_ews",         "user_income_norm",
    "user_has_disability","user_is_widow",       "user_edu_level",
    "user_has_aadhar",    "user_has_bank",
]


def build_feature_vector(user: dict[str, Any], scheme_elig: dict[str, Any]) -> np.ndarray:
    """
    Build the feature vector for one (user, scheme) pair.

    Args:
        user:        user profile dict (see module docstring for fields)
        scheme_elig: eligibility_json from a scheme record

    Returns:
        1D float32 numpy array of length len(FEATURE_NAMES)
    """
    age         = int(user.get("age") or 0)
    gender      = (user.get("gender") or "other").lower()
    state       = (user.get("state") or "").strip()
    income      = int(user.get("annual_income") or 0)
    inc_src     = (user.get("income_source") or "other").lower()
    caste       = (user.get("caste_category") or "General").strip()
    disability  = bool(user.get("disability"))
    is_widow    = bool(user.get("is_widow"))
    edu         = (user.get("education_level") or "none").lower().strip()
    has_aadhar  = bool(user.get("has_aadhar"))
    has_bank    = bool(user.get("has_bank_account"))

    s_age       = scheme_elig.get("age") or {}
    s_min_age   = s_age.get("min")
    s_max_age   = s_age.get("max")
    s_gender    = (scheme_elig.get("gender") or "all").lower()
    s_income    = (scheme_elig.get("income_limit") or {})
    s_inc_cap   = s_income.get("annual_inr")
    s_bpl       = bool(s_income.get("bpl_only"))
    s_castes    = scheme_elig.get("caste") or []
    s_state     = (scheme_elig.get("state") or "all").strip()
    s_occ       = scheme_elig.get("occupation") or []
    s_dis       = bool(scheme_elig.get("disability"))
    s_edu       = scheme_elig.get("education") or []
    s_requires  = scheme_elig.get("requires") or []

    # --- Age match ---
    has_age_c = (s_min_age is not None) or (s_max_age is not None)
    if not has_age_c:
        age_match = 0.5
        age_below = 0.0
        age_above = 0.0
    else:
        lo = s_min_age or 0
        hi = s_max_age or 120
        if lo <= age <= hi:
            age_match = 1.0
            age_below = 0.0
            age_above = 0.0
        elif age < lo:
            age_match = 0.0
            age_below = min((lo - age) / max(lo, 1), 1.0)
            age_above = 0.0
        else:
            age_match = 0.0
            age_below = 0.0
            age_above = min((age - hi) / max(hi, 1), 1.0)

    # --- Gender match ---
    if s_gender == "all":
        gender_match = 0.5
    elif gender == s_gender:
        gender_match = 1.0
    else:
        gender_match = 0.0

    # --- State match ---
    if s_state.lower() in ("all", "central", ""):
        state_match = 0.5
    elif state.lower() == s_state.lower():
        state_match = 1.0
    else:
        state_match = 0.0

    # --- Income match ---
    if s_bpl:
        # BPL schemes: income below ~1L is a rough proxy for BPL
        bpl_match = 1.0 if income <= 100_000 else 0.0
        income_match = bpl_match
        income_ratio = min(income / 100_000, 3.0) if income > 0 else 0.0
    elif s_inc_cap:
        income_match = 1.0 if income <= s_inc_cap else 0.0
        income_ratio = min(income / s_inc_cap, 3.0) if s_inc_cap > 0 else 1.0
        bpl_match = 0.5
    else:
        income_match = 0.5
        income_ratio = 0.5
        bpl_match = 0.5

    # --- Caste match ---
    caste_match = _caste_partial_score(caste, s_castes)
    has_caste_c = 1.0 if s_castes else 0.0

    # --- Disability match ---
    if s_dis:
        disability_match = 1.0 if disability else 0.0
    else:
        disability_match = 0.5

    # --- Widow match ---
    widow_occ = any("widow" in o.lower() for o in s_occ)
    if widow_occ:
        widow_match = 1.0 if is_widow else 0.0
    else:
        widow_match = 0.5

    # --- Occupation match ---
    occupation_match = _occupation_match(inc_src, s_occ)

    # --- Education match ---
    education_match = _edu_match(edu, s_edu)

    # --- Document requirements ---
    needs_aadhar = "aadhar" in s_requires
    needs_bank   = "bank_account" in s_requires
    aadhar_match = (1.0 if has_aadhar else 0.0) if needs_aadhar else 0.5
    bank_match   = (1.0 if has_bank   else 0.0) if needs_bank   else 0.5

    # --- Constraint density ---
    has_inc_c   = 1.0 if (s_inc_cap or s_bpl) else 0.0
    has_gender_c = 1.0 if s_gender != "all" else 0.0
    has_state_c  = 1.0 if s_state.lower() not in ("all", "central", "") else 0.0
    n_constraints = sum([
        float(has_age_c), has_inc_c, has_caste_c,
        has_gender_c, has_state_c,
        float(s_dis), float(bool(s_edu)),
    ])

    # --- Raw user features ---
    user_age_norm    = min(age / 100.0, 1.0)
    user_is_female   = 1.0 if gender == "female" else 0.0
    user_is_sc       = 1.0 if caste.upper() == "SC" else 0.0
    user_is_st       = 1.0 if caste.upper() == "ST" else 0.0
    user_is_obc      = 1.0 if caste.upper() == "OBC" else 0.0
    user_is_ews      = 1.0 if caste.upper() == "EWS" else 0.0
    user_income_norm = min(math.log1p(income) / math.log1p(10_000_000), 1.0)
    user_has_dis     = 1.0 if disability else 0.0
    user_is_widow    = 1.0 if is_widow else 0.0
    user_edu_level   = _edu_level(edu) / 17.0
    user_has_aadhar  = 1.0 if has_aadhar else 0.0
    user_has_bank    = 1.0 if has_bank else 0.0

    return np.array([
        age_match, age_below, age_above,
        gender_match, state_match,
        income_match, income_ratio,
        caste_match, disability_match, widow_match,
        occupation_match, education_match,
        aadhar_match, bank_match,
        bpl_match,
        n_constraints / 7.0, float(has_age_c), has_inc_c,
        has_caste_c, has_gender_c, has_state_c,
        user_age_norm, user_is_female, user_is_sc, user_is_st,
        user_is_obc, user_is_ews, user_income_norm,
        user_has_dis, user_is_widow, user_edu_level,
        user_has_aadhar, user_has_bank,
    ], dtype=np.float32)

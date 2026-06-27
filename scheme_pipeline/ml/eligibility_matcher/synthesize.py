"""
ml/eligibility_matcher/synthesize.py
=======================================
Generates synthetic (user_profile, scheme, label) training triples from
the structured eligibility_json fields in schemes_normalized.json.

WHY SYNTHETIC DATA:
  We have no real user profiles with ground-truth eligibility outcomes.
  Instead, we use the extracted eligibility_json rules to generate labels
  deterministically: a user who satisfies all of a scheme's constraints
  gets label 1.0; a user who violates a hard constraint gets 0.0; a user
  who partially matches gets something in between. The model then learns
  to approximate this scoring function — which sounds circular, but gives
  two things rules can't:
    1. Smooth partial-match scores (not just 0/1)
    2. Handles null constraints (open fields) sensibly via learned weights

LABEL CALCULATION:
  Each constraint contributes a penalty if violated:
    Gender mismatch          → subtract 0.40 (hard)
    State mismatch           → subtract 0.35 (hard)
    Age out of range         → subtract 0.20-0.35 (depends on how far)
    Income over limit        → subtract 0.25-0.35 (depends on how much over)
    Caste mismatch           → subtract 0.30 (hard)
    Disability required/missing → subtract 0.30 (hard)
    Education below required → subtract 0.10-0.20
    Document missing         → subtract 0.05-0.10
  Score = max(0, 1 - sum(penalties))
  
  Hard constraints (gender, state if specific, caste if required) drive
  the score to 0 fast. Soft constraints (income near limit, age near
  boundary) produce gradual score reduction.

STATUS THRESHOLDS:
  ≥ 0.80  → ELIGIBLE
  ≥ 0.55  → LIKELY_ELIGIBLE
  ≥ 0.30  → CHECK_REQUIRED
  < 0.30  → NOT_ELIGIBLE
"""

import json
import random
import math
from pathlib import Path
from typing import Any

from ml.eligibility_matcher.features import build_feature_vector, FEATURE_NAMES

import numpy as np

SEED = 42
DATA_FILE = Path("data/processed/schemes_normalized.json")

# How many (user, scheme) pairs to generate per scheme.
# With ~4789 schemes × 40 pairs each → ~192k training examples.
# Increase this if you want more; each pair takes <1ms to generate.
PAIRS_PER_SCHEME = 40

_STATES = [
    "Gujarat", "Uttarakhand", "Madhya Pradesh", "Tamil Nadu", "Rajasthan",
    "Bihar", "Maharashtra", "Karnataka", "Kerala", "West Bengal",
    "Andhra Pradesh", "Telangana", "Odisha", "Assam", "Punjab",
    "Haryana", "Himachal Pradesh", "Jharkhand", "Chhattisgarh", "Goa",
    "Puducherry", "Sikkim", "Tripura", "Manipur", "Meghalaya",
    "Arunachal Pradesh", "Mizoram", "Nagaland", "Delhi", "Chandigarh",
]
_CASTES = ["General", "OBC", "SC", "ST", "EWS"]
_GENDERS = ["male", "female", "other"]
_INCOME_SOURCES = ["farmer", "labourer", "salaried", "self_employed", "unemployed", "other"]
_EDU_LEVELS = ["none", "class 5", "class 8", "class 10", "class 12",
               "diploma", "graduate", "postgraduate", "phd"]


def _random_user(rng: random.Random, scheme_elig: dict) -> dict:
    """
    Generate a random user profile. Biased toward the scheme's target
    profile ~60% of the time — this makes the dataset cover the
    near-eligible / barely-ineligible boundary well, which is where the
    model needs the most resolution.

    The other 40% is fully random, ensuring we also cover clearly
    ineligible cases so the model doesn't learn "always predict high."
    """
    biased = rng.random() < 0.6

    s_age   = scheme_elig.get("age") or {}
    s_gender = (scheme_elig.get("gender") or "all").lower()
    s_income = scheme_elig.get("income_limit") or {}
    s_cap   = s_income.get("annual_inr")
    s_castes = scheme_elig.get("caste") or []
    s_state  = (scheme_elig.get("state") or "all").strip()
    s_dis   = bool(scheme_elig.get("disability"))

    if biased:
        # Age: sample near the valid range with some overshoot
        lo = s_age.get("min") or 5
        hi = s_age.get("max") or 65
        spread = max(hi - lo, 10)
        age = int(rng.gauss((lo + hi) / 2, spread * 0.6))
        age = max(0, min(100, age))

        # Gender: use scheme target 70% of the time
        if s_gender in ("male", "female") and rng.random() < 0.7:
            gender = s_gender
        else:
            gender = rng.choice(_GENDERS)

        # Income: sample around the cap
        if s_cap:
            income = int(rng.gauss(s_cap * 0.7, s_cap * 0.5))
            income = max(0, income)
        else:
            income = int(rng.expovariate(1 / 300_000))

        # Caste: use scheme caste 60% of the time
        if s_castes and rng.random() < 0.6:
            caste = rng.choice(s_castes)
        else:
            caste = rng.choice(_CASTES)

        # State
        if s_state.lower() not in ("all", "central", "") and rng.random() < 0.65:
            state = s_state
        else:
            state = rng.choice(_STATES)

        disability = s_dis and rng.random() < 0.7

    else:
        # Fully random
        lo = s_age.get("min") or 0
        hi = s_age.get("max") or 80
        age = rng.randint(1, 90)
        gender = rng.choice(_GENDERS)
        income = int(rng.expovariate(1 / 250_000))
        caste = rng.choice(_CASTES)
        state = rng.choice(_STATES)
        disability = rng.random() < 0.08

    return {
        "age": age,
        "gender": gender,
        "state": state,
        "annual_income": income,
        "income_source": rng.choice(_INCOME_SOURCES),
        "caste_category": caste,
        "disability": disability,
        "is_widow": rng.random() < 0.06,
        "education_level": rng.choice(_EDU_LEVELS),
        "has_bank_account": rng.random() < 0.75,
        "has_aadhar": rng.random() < 0.85,
        "land_ownership": round(rng.expovariate(1 / 2), 2) if rng.random() < 0.3 else 0.0,
        "has_house": rng.random() < 0.5,
        "children_count": rng.randint(0, 4),
    }


def _compute_label(user: dict, scheme_elig: dict) -> float:
    """
    Compute a deterministic eligibility score for a (user, scheme) pair
    based on penalty deductions. This IS the ground truth for synthetic
    training — see module docstring for the penalty table.
    """
    penalty = 0.0

    age = user["age"]
    gender = user["gender"].lower()
    state = user["state"]
    income = user["annual_income"]
    caste = user["caste_category"].upper()
    disability = user["disability"]

    s_age    = scheme_elig.get("age") or {}
    s_min    = s_age.get("min")
    s_max    = s_age.get("max")
    s_gender = (scheme_elig.get("gender") or "all").lower()
    s_state  = (scheme_elig.get("state") or "all").strip()
    s_inc    = scheme_elig.get("income_limit") or {}
    s_cap    = s_inc.get("annual_inr")
    s_bpl    = s_inc.get("bpl_only", False)
    s_castes = [c.upper() for c in (scheme_elig.get("caste") or [])]
    s_dis    = bool(scheme_elig.get("disability"))
    s_requires = scheme_elig.get("requires") or []

    # Hard: gender
    if s_gender not in ("all", "other") and gender != s_gender:
        penalty += 0.40

    # Hard: state (specific state mismatch)
    if s_state.lower() not in ("all", "central", ""):
        if state.lower() != s_state.lower():
            penalty += 0.35

    # Soft-to-hard: age
    if s_min is not None and age < s_min:
        shortfall = s_min - age
        penalty += min(0.35, 0.05 * shortfall)
    if s_max is not None and age > s_max:
        excess = age - s_max
        penalty += min(0.35, 0.05 * excess)

    # Soft-to-hard: income
    if s_bpl:
        if income > 100_000:
            penalty += min(0.35, 0.35 * min(income / 100_000 - 1, 2))
    elif s_cap:
        if income > s_cap:
            ratio = income / s_cap
            penalty += min(0.35, 0.25 * min(ratio - 1, 2))

    # Hard: caste
    if s_castes:
        if caste not in s_castes:
            if caste in ("SC", "ST") and "OBC" in s_castes:
                penalty += 0.15  # partial
            else:
                penalty += 0.30

    # Hard: disability required but user doesn't have it
    if s_dis and not disability:
        penalty += 0.30

    # Soft: document requirements
    if "aadhar" in s_requires and not user.get("has_aadhar"):
        penalty += 0.08
    if "bank_account" in s_requires and not user.get("has_bank_account"):
        penalty += 0.05

    return float(max(0.0, 1.0 - penalty))


STATUS_THRESHOLDS = [
    (0.80, "ELIGIBLE"),
    (0.55, "LIKELY_ELIGIBLE"),
    (0.30, "CHECK_REQUIRED"),
    (0.00, "NOT_ELIGIBLE"),
]


def score_to_status(score: float) -> str:
    for threshold, label in STATUS_THRESHOLDS:
        if score >= threshold:
            return label
    return "NOT_ELIGIBLE"


def generate(
    data_file: Path = DATA_FILE,
    pairs_per_scheme: int = PAIRS_PER_SCHEME,
    seed: int = SEED,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns (X, y) where:
      X: float32 array of shape (N, len(FEATURE_NAMES))
      y: float32 array of shape (N,) — scores in [0, 1]
    """
    rng = random.Random(seed)
    records = json.loads(data_file.read_text(encoding="utf-8"))

    X_rows = []
    y_vals = []

    for rec in records:
        elig = rec.get("eligibility_json", {})
        for _ in range(pairs_per_scheme):
            user = _random_user(rng, elig)
            label = _compute_label(user, elig)
            fv = build_feature_vector(user, elig)
            X_rows.append(fv)
            y_vals.append(label)

    X = np.stack(X_rows).astype(np.float32)
    y = np.array(y_vals, dtype=np.float32)
    return X, y


if __name__ == "__main__":
    import time
    t0 = time.time()
    X, y = generate()
    elapsed = time.time() - t0
    print(f"Generated {len(X):,} examples in {elapsed:.1f}s")
    print(f"X shape: {X.shape}, y mean: {y.mean():.3f}, y std: {y.std():.3f}")
    print(f"Status distribution:")
    from collections import Counter
    counts = Counter(score_to_status(s) for s in y)
    total = len(y)
    for status, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {status:<20} {cnt:>8,} ({100*cnt/total:.1f}%)")
    print(f"Feature names ({len(FEATURE_NAMES)}): {FEATURE_NAMES}")

"""
ml/eligibility_matcher/score.py
==================================
Production inference interface for Model 1.

Given a user profile dict, scores every scheme in the database and
returns a ranked list with confidence scores and eligibility status.

Usage:
    from ml.eligibility_matcher.score import EligibilityMatcher

    matcher = EligibilityMatcher()  # loads model + schemes once

    results = matcher.score_user({
        "age": 28,
        "gender": "female",
        "state": "Tamil Nadu",
        "annual_income": 80000,
        "income_source": "farmer",
        "caste_category": "SC",
        "disability": False,
        "is_widow": False,
        "education_level": "class 10",
        "has_bank_account": True,
        "has_aadhar": True,
    })

    for r in results[:10]:
        print(r["score"], r["status"], r["name"])
"""

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import xgboost as xgb

from ml.eligibility_matcher.features import build_feature_vector, FEATURE_NAMES
from ml.eligibility_matcher.synthesize import score_to_status

MODEL_PATH  = Path("ml/eligibility_matcher/model.json")
SCHEMES_PATH = Path("data/processed/schemes_normalized.json")


def _constraint_density(elig: dict) -> int:
    """Count how many eligibility fields are actually constrained (non-null,
    non-'all'). Used as a tiebreaker — a scheme with gender=female AND
    state=Tamil Nadu AND caste=SC is more specific (and more relevant to
    a user who satisfies all three) than a scheme with every field null."""
    n = 0
    age = elig.get("age") or {}
    if age.get("min") or age.get("max"):
        n += 1
    inc = elig.get("income_limit") or {}
    if inc.get("annual_inr") or inc.get("bpl_only"):
        n += 1
    if elig.get("gender", "all") not in ("all", ""):
        n += 1
    if elig.get("caste"):
        n += 1
    if (elig.get("state") or "all").lower() not in ("all", "central", ""):
        n += 1
    if elig.get("disability"):
        n += 1
    if elig.get("education"):
        n += 1
    return n


class EligibilityMatcher:
    """
    Loads the trained XGBoost model and scheme database once at init,
    then scores all schemes for any user profile in a single batch
    forward pass (typically <200ms for 4789 schemes).
    """

    def __init__(
        self,
        model_path: Path = MODEL_PATH,
        schemes_path: Path = SCHEMES_PATH,
    ):
        self.model = xgb.Booster()
        self.model.load_model(str(model_path))
        self.schemes = json.loads(schemes_path.read_text(encoding="utf-8"))
        self._eligibilities = [s.get("eligibility_json", {}) for s in self.schemes]

    def score_user(
        self,
        user: dict[str, Any],
        top_n: int | None = None,
        min_status: str = "CHECK_REQUIRED",
    ) -> list[dict]:
        """
        Score all schemes for a given user profile.

        Args:
            user:       user profile dict — see module docstring for fields.
            top_n:      if set, return only the top N results.
            min_status: filter out results below this status level.
                        "ELIGIBLE" → only definite matches
                        "LIKELY_ELIGIBLE" → definite + probable
                        "CHECK_REQUIRED"  → all non-obvious non-matches (default)
                        "NOT_ELIGIBLE"    → return everything (for debugging)

        Returns:
            List of dicts sorted by score descending, each containing:
              name, ministry, category, state, score, status,
              eligibility_json, application_url, description
        """
        t0 = time.time()

        # Build feature matrix for ALL schemes in a single pass
        fvs = np.stack([
            build_feature_vector(user, elig)
            for elig in self._eligibilities
        ]).astype(np.float32)

        dmat = xgb.DMatrix(fvs, feature_names=FEATURE_NAMES)
        scores = self.model.predict(dmat)

        # Apply status filter threshold
        _status_order = {
            "NOT_ELIGIBLE": 0,
            "CHECK_REQUIRED": 1,
            "LIKELY_ELIGIBLE": 2,
            "ELIGIBLE": 3,
        }
        min_order = _status_order.get(min_status, 1)

        results = []
        for i, (scheme, score) in enumerate(zip(self.schemes, scores)):
            s = float(np.clip(score, 0.0, 1.0))
            status = score_to_status(s)
            if _status_order[status] < min_order:
                continue
            results.append({
                "name":            scheme.get("name", ""),
                "ministry":        scheme.get("ministry", ""),
                "category":        scheme.get("category", ""),
                "subcategory":     scheme.get("subcategory", ""),
                "state":           scheme.get("state", ""),
                "description":     scheme.get("description", "")[:300],
                "application_url": scheme.get("application_url", ""),
                "benefit_type":    scheme.get("benefit_type", ""),
                "benefit_amount":  scheme.get("benefit_amount", ""),
                "score":           round(s, 4),
                "status":          status,
                "eligibility_json": scheme.get("eligibility_json", {}),
            })

        results.sort(key=lambda x: (
            -x["score"],
            # Tiebreaker: prefer schemes that have specific constraints
            # which this user satisfies, over open-to-all schemes that
            # score 1.0 simply because they have no constraints at all.
            # "n_constraints" is already in the feature vector; we proxy
            # it here from the eligibility_json directly.
            -_constraint_density(x["eligibility_json"]),
        ))
        elapsed_ms = (time.time() - t0) * 1000

        if top_n:
            results = results[:top_n]

        # Attach timing metadata to first result for debugging
        if results:
            results[0]["_meta"] = {
                "total_schemes": len(self.schemes),
                "returned": len(results),
                "elapsed_ms": round(elapsed_ms, 1),
            }

        return results


# ── Quick CLI test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    matcher = EligibilityMatcher()

    test_profiles = [
        {
            "label": "SC woman farmer, Tamil Nadu, income 80k, class 10",
            "profile": {
                "age": 28, "gender": "female", "state": "Tamil Nadu",
                "annual_income": 80_000, "income_source": "farmer",
                "caste_category": "SC", "disability": False, "is_widow": False,
                "education_level": "class 10",
                "has_bank_account": True, "has_aadhar": True,
            }
        },
        {
            "label": "Disabled OBC man, Madhya Pradesh, unemployed, income 45k",
            "profile": {
                "age": 35, "gender": "male", "state": "Madhya Pradesh",
                "annual_income": 45_000, "income_source": "unemployed",
                "caste_category": "OBC", "disability": True, "is_widow": False,
                "education_level": "class 8",
                "has_bank_account": True, "has_aadhar": True,
            }
        },
        {
            "label": "General salaried man, Gujarat, income 12L — few targeted schemes",
            "profile": {
                "age": 42, "gender": "male", "state": "Gujarat",
                "annual_income": 1_200_000, "income_source": "salaried",
                "caste_category": "General", "disability": False, "is_widow": False,
                "education_level": "graduate",
                "has_bank_account": True, "has_aadhar": True,
            }
        },
    ]

    for test in test_profiles:
        print("=" * 70)
        print(f"USER: {test['label']}")
        results = matcher.score_user(test["profile"], top_n=5)
        meta = results[0].pop("_meta", {}) if results else {}
        print(f"  {meta.get('returned',0)} results returned in {meta.get('elapsed_ms',0)}ms "
              f"(out of {meta.get('total_schemes',0)} schemes)")
        print()
        for r in results:
            print(f"  [{r['status']:<17}] {r['score']:.3f}  {r['name'][:55]}")
            print(f"           {r['category']} | {r['state']} | {r['benefit_type']}")
        print()

"""
api/main.py
============
FastAPI application for the Scheme Pipeline.

Two endpoints:

  POST /api/match
    Takes a user profile, returns schemes ranked by eligibility score.
    Uses Model 1 (XGBoost eligibility matcher).

  GET /api/schemes
    Browse/filter schemes directly by structured fields — no ML,
    just DB-level filtering. Useful for building filter UIs or
    debugging what's in the database without going through the
    matcher.

Run locally:
    uvicorn api.main:app --reload --port 8000
    python -m uvicorn api.main:app --reload --port 8000

Then open:
    http://localhost:8000/docs    ← interactive Swagger UI (test both endpoints here)
    http://localhost:8000/redoc   ← alternative docs

Example curl:
    curl -X POST http://localhost:8000/api/match \\
      -H "Content-Type: application/json" \\
      -d '{
        "age": 28, "gender": "female", "state": "Tamil Nadu",
        "annual_income": 80000, "income_source": "farmer",
        "caste_category": "SC", "disability": false, "is_widow": false,
        "education_level": "class 10",
        "has_bank_account": true, "has_aadhar": true
      }'
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ml.eligibility_matcher.score import EligibilityMatcher
from ml.semantic_search.search import SemanticSearch

# ── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Sahayak Scheme API",
    description=(
        "Match Indian government welfare schemes to a user profile using "
        "XGBoost eligibility scoring (Model 1) and spaCy NER extraction (Model 2)."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # tighten this in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Load ML model + scheme data once at startup ──────────────────────────────
# These are module-level so they're shared across all requests.
# EligibilityMatcher loads ~4789 schemes + the XGBoost model into memory
# (~50MB total). First request takes ~1s; subsequent requests <200ms.

_matcher: EligibilityMatcher | None = None
_schemes: list[dict] | None = None
_search_engine: SemanticSearch | None = None

ROOT_DIR = Path(__file__).resolve().parents[1]

SCHEMES_PATH = ROOT_DIR / "data" / "processed" / "schemes_normalized.json"
MODEL_PATH   = ROOT_DIR / "ml" / "eligibility_matcher" / "model.json"
EMBED_PATH   = ROOT_DIR / "ml" / "semantic_search" / "scheme_embeddings.npy"


def get_matcher() -> EligibilityMatcher:
    global _matcher
    if _matcher is None:
        _matcher = EligibilityMatcher()
    return _matcher


def get_schemes() -> list[dict]:
    global _schemes
    if _schemes is None:
        _schemes = json.loads(SCHEMES_PATH.read_text(encoding="utf-8"))
    return _schemes


def get_search_engine() -> SemanticSearch:
    global _search_engine
    if _search_engine is None:
        if not EMBED_PATH.exists():
            raise HTTPException(
                status_code=503,
                detail="Embedding index not found. Run `python -m ml.semantic_search.embed` first."
            )
        _search_engine = SemanticSearch()
    return _search_engine


# ── Request / Response models ─────────────────────────────────────────────────

class UserProfile(BaseModel):
    age:             int            = Field(..., ge=0, le=120, example=28)
    gender:          str            = Field(..., example="female",
                                           description="male / female / other")
    state:           str            = Field(..., example="Tamil Nadu")
    annual_income:   int            = Field(..., ge=0, example=80000,
                                           description="Annual family income in INR")
    income_source:   str            = Field("other", example="farmer",
                                           description="farmer / labourer / salaried / self_employed / unemployed / other")
    caste_category:  str            = Field("General", example="SC",
                                           description="General / OBC / SC / ST / EWS")
    disability:      bool           = Field(False, example=False)
    is_widow:        bool           = Field(False, example=False)
    education_level: str            = Field("none", example="class 10",
                                           description="none / class 5 / class 8 / class 10 / class 12 / diploma / graduate / postgraduate / phd")
    has_bank_account: bool          = Field(True, example=True)
    has_aadhar:       bool          = Field(True, example=True)
    land_ownership:   float         = Field(0.0, example=0.0,
                                           description="Land owned in acres")
    has_house:        bool          = Field(False, example=False)
    children_count:   int           = Field(0, ge=0, example=0)


class SchemeResult(BaseModel):
    name:            str
    ministry:        str
    category:        str
    subcategory:     str
    state:           str
    description:     str
    benefit_type:    str
    benefit_amount:  str
    application_url: str
    score:           float = Field(description="Eligibility confidence score 0.0–1.0")
    status:          str   = Field(description="ELIGIBLE / LIKELY_ELIGIBLE / CHECK_REQUIRED / NOT_ELIGIBLE")
    eligibility_json: dict


class MatchResponse(BaseModel):
    total_schemes:  int
    returned:       int
    elapsed_ms:     float
    results:        list[SchemeResult]


class SchemeListResponse(BaseModel):
    total:   int
    page:    int
    per_page: int
    results: list[dict]


# ── Endpoint 1: POST /api/match ───────────────────────────────────────────────

@app.post(
    "/api/match",
    response_model=MatchResponse,
    summary="Match schemes to a user profile",
    description=(
        "Given a user profile, scores all ~4789 schemes using the XGBoost "
        "eligibility model and returns the top matches ranked by confidence score.\n\n"
        "**Status values:**\n"
        "- `ELIGIBLE` — all known criteria satisfied (score ≥ 0.80)\n"
        "- `LIKELY_ELIGIBLE` — most criteria satisfied (score ≥ 0.55)\n"
        "- `CHECK_REQUIRED` — partial match, verify manually (score ≥ 0.30)\n"
        "- `NOT_ELIGIBLE` — hard criteria violated (score < 0.30)"
    ),
)
def match_schemes(
    profile: UserProfile,
    top_n: int = Query(20, ge=1, le=200,
                       description="Maximum number of results to return"),
    min_status: str = Query("LIKELY_ELIGIBLE",
                             description="Minimum status: ELIGIBLE / LIKELY_ELIGIBLE / CHECK_REQUIRED / NOT_ELIGIBLE"),
):
    valid_statuses = {"ELIGIBLE", "LIKELY_ELIGIBLE", "CHECK_REQUIRED", "NOT_ELIGIBLE"}
    if min_status not in valid_statuses:
        raise HTTPException(status_code=400,
                            detail=f"min_status must be one of {sorted(valid_statuses)}")

    matcher = get_matcher()
    t0 = time.time()

    raw_results = matcher.score_user(
        user=profile.model_dump(),
        top_n=top_n,
        min_status=min_status,
    )

    # Strip internal _meta key if present
    meta = raw_results[0].pop("_meta", {}) if raw_results else {}
    elapsed_ms = round((time.time() - t0) * 1000, 1)

    return MatchResponse(
        total_schemes=meta.get("total_schemes", len(matcher.schemes)),
        returned=len(raw_results),
        elapsed_ms=elapsed_ms,
        results=[SchemeResult(**r) for r in raw_results],
    )


# ── Endpoint 2: GET /api/schemes ─────────────────────────────────────────────

@app.get(
    "/api/schemes",
    response_model=SchemeListResponse,
    summary="Browse and filter schemes",
    description=(
        "Browse schemes with structured filters — no ML scoring, "
        "just direct field matching. Useful for exploring what's in "
        "the database or building a filter UI."
    ),
)
def list_schemes(
    state:      Optional[str] = Query(None, description="Filter by state (e.g. 'Tamil Nadu' or 'Central')"),
    gender:     Optional[str] = Query(None, description="Filter by gender: female / male / all"),
    category:   Optional[str] = Query(None, description="Filter by category (partial match)"),
    caste:      Optional[str] = Query(None, description="Filter by caste: SC / ST / OBC / EWS"),
    disability: Optional[bool] = Query(None, description="Filter schemes for people with disability"),
    min_age:    Optional[int] = Query(None, description="Return schemes whose age range includes this age"),
    max_income: Optional[int] = Query(None, description="Return schemes where income limit ≥ this value (in INR)"),
    page:       int = Query(1, ge=1, description="Page number"),
    per_page:   int = Query(20, ge=1, le=100, description="Results per page"),
):
    schemes = get_schemes()
    results = []

    for s in schemes:
        elig = s.get("eligibility_json", {})

        if state:
            s_state = (elig.get("state") or s.get("state") or "").lower()
            if s_state not in ("all", "central", state.lower()):
                continue

        if gender:
            s_gender = (elig.get("gender") or "all").lower()
            if s_gender != "all" and s_gender != gender.lower():
                continue

        if category:
            if category.lower() not in (s.get("category") or "").lower():
                continue

        if caste:
            s_castes = [c.upper() for c in (elig.get("caste") or [])]
            if s_castes and caste.upper() not in s_castes:
                continue

        if disability is not None:
            if bool(elig.get("disability")) != disability:
                continue

        if min_age is not None:
            s_age = elig.get("age") or {}
            lo = s_age.get("min") or 0
            hi = s_age.get("max") or 120
            if not (lo <= min_age <= hi):
                continue

        if max_income is not None:
            s_cap = (elig.get("income_limit") or {}).get("annual_inr")
            if s_cap and s_cap < max_income:
                continue

        results.append({
            "name":            s.get("name", ""),
            "ministry":        s.get("ministry", ""),
            "category":        s.get("category", ""),
            "state":           s.get("state", ""),
            "benefit_type":    s.get("benefit_type", ""),
            "benefit_amount":  s.get("benefit_amount", ""),
            "application_url": s.get("application_url", ""),
            "eligibility_json": elig,
        })

    total = len(results)
    start = (page - 1) * per_page
    end   = start + per_page

    return SchemeListResponse(
        total=total,
        page=page,
        per_page=per_page,
        results=results[start:end],
    )


# ── Endpoint 3: GET /api/search ──────────────────────────────────────────────

@app.get(
    "/api/search",
    summary="Semantic search over schemes",
    description=(
        "Free-form natural language search using sentence embeddings + cosine "
        "similarity. Finds semantically relevant schemes even when the query "
        "uses different words than the scheme text.\n\n"
        "**Example queries:**\n"
        "- `schemes for poor farmers who lost crops in flood`\n"
        "- `financial help for widow women`\n"
        "- `scholarship for SC ST students`\n\n"
        "**Requires:** run `python -m ml.semantic_search.embed` once to build "
        "the embedding index before using this endpoint."
    ),
)
def semantic_search(
    q: str = Query(..., description="Natural language search query", min_length=3),
    top_k: int = Query(5, ge=1, le=50, description="Number of results to return"),
    min_score: float = Query(0.0, ge=0.0, le=1.0,
                              description="Minimum cosine similarity score (0–1)"),
):
    engine = get_search_engine()
    results = engine.query(q, top_k=top_k, min_score=min_score)
    meta = results[0].pop("_meta", {}) if results else {}
    return {
        "query":      q,
        "model":      meta.get("model", ""),
        "elapsed_ms": meta.get("elapsed_ms", 0),
        "returned":   len(results),
        "results":    results,
    }


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "schemes_loaded": _schemes is not None}


# ── Dev runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
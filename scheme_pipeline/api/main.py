"""
api/main.py
============
Python FastAPI — ML inference service.
Called internally by the Java Spring Boot backend, never directly by clients.

Endpoints:
  POST /match             User profile → ranked schemes with scores
  POST /search            Natural language query → semantically relevant schemes
  POST /extract-criteria  Raw scheme text → structured eligibility JSON

Run:
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import numpy as np
import xgboost as xgb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ml.eligibility_matcher.features import build_feature_vector, FEATURE_NAMES
from ml.eligibility_matcher.synthesize import score_to_status
from ml.ner_extractor.extractor import extract_eligibility

# --- App ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: pre-load the sentence-transformer model and embedding index
    # into memory when the Python server starts — not on the first user
    # request. All subsequent /search calls will be fast (~20ms).
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _get_search)
    yield
    # (no shutdown cleanup needed)


app = FastAPI(
    title="Sahayak ML Service",
    description="Internal ML inference service. Called by the Java backend.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# --- Lazy-loaded globals (loaded once, reused across requests) ---

_schemes:     list[dict] | None = None
_eligibilities: list[dict] | None = None
_booster:     xgb.Booster | None = None
_search_engine = None           # SemanticSearch, loaded only if embed index exists

SCHEMES_PATH = Path("data/processed/schemes_normalized.json")
MODEL_PATH   = Path("ml/eligibility_matcher/model.json")
EMBED_PATH   = Path("ml/semantic_search/scheme_embeddings.npy")


def _get_schemes() -> list[dict]:
    global _schemes, _eligibilities
    if _schemes is None:
        _schemes = json.loads(SCHEMES_PATH.read_text(encoding="utf-8"))
        _eligibilities = [s.get("eligibility_json", {}) for s in _schemes]
    return _schemes


def _get_booster() -> xgb.Booster:
    global _booster
    if _booster is None:
        booster = xgb.Booster()
        booster.load_model(str(MODEL_PATH))
        _booster = booster
    return _booster


def _get_search():
    global _search_engine
    if _search_engine is None:
        if not EMBED_PATH.exists():
            raise HTTPException(
                status_code=503,
                detail="Embedding index not found. Run `python -m ml.semantic_search.embed` first."
            )
        from ml.semantic_search.search import SemanticSearch
        _search_engine = SemanticSearch()
    return _search_engine


# --- Helpers ---

def _constraint_density(elig: dict) -> int:
    n = 0
    age = elig.get("age") or {}
    if age.get("min") or age.get("max"): n += 1
    inc = elig.get("income_limit") or {}
    if inc.get("annual_inr") or inc.get("bpl_only"): n += 1
    if elig.get("gender", "all") not in ("all", ""): n += 1
    if elig.get("caste"): n += 1
    if (elig.get("state") or "all").lower() not in ("all", "central", ""): n += 1
    if elig.get("disability"): n += 1
    if elig.get("education"): n += 1
    return n


def _matched_criteria(user: dict, elig: dict) -> dict:
    """
    Returns which eligibility fields the user matches, partially matches,
    or fails — gives Java side enough info to display "Why this scheme?"
    explanations without re-implementing matching logic.

    Values: true = matches, false = doesn't match, null = no constraint
    """
    def age_match():
        age = user.get("age") or 0
        s = elig.get("age") or {}
        lo, hi = s.get("min"), s.get("max")
        if lo is None and hi is None: return None
        return bool((lo is None or age >= lo) and (hi is None or age <= hi))

    def income_match():
        inc = user.get("annual_income") or 0
        s = elig.get("income_limit") or {}
        if s.get("bpl_only"): return inc <= 100_000
        cap = s.get("annual_inr")
        if cap is None: return None
        return inc <= cap

    def gender_match():
        g = elig.get("gender", "all")
        if g == "all": return None
        return user.get("gender", "").lower() == g.lower()

    def caste_match():
        castes = [c.upper() for c in (elig.get("caste") or [])]
        if not castes: return None
        return user.get("caste_category", "").upper() in castes

    def state_match():
        s = (elig.get("state") or "all").lower()
        if s in ("all", "central", ""): return None
        return user.get("state", "").lower() == s

    def disability_match():
        if not elig.get("disability"): return None
        return bool(user.get("disability"))

    return {
        "age":        age_match(),
        "income":     income_match(),
        "gender":     gender_match(),
        "caste":      caste_match(),
        "state":      state_match(),
        "disability": disability_match(),
    }


# --- Request / Response models ---

class UserProfileInput(BaseModel):
    age:              int    = Field(..., ge=0, le=120, example=28)
    gender:           str    = Field(..., example="female")
    state:            str    = Field(..., example="Tamil Nadu")
    annual_income:    int    = Field(..., ge=0, example=80000)
    income_source:    str    = Field("other", example="farmer")
    caste_category:   str    = Field("General", example="SC")
    disability:       bool   = Field(False)
    is_widow:         bool   = Field(False)
    education_level:  str    = Field("none", example="class 10")
    has_bank_account: bool   = Field(True)
    has_aadhar:       bool   = Field(True)
    land_ownership:   float  = Field(0.0)
    has_house:        bool   = Field(False)
    children_count:   int    = Field(0, ge=0)


class MatchRequest(BaseModel):
    user:       UserProfileInput
    top_n:      int   = Field(20, ge=1, le=200)
    min_status: str   = Field("LIKELY_ELIGIBLE")


class MatchedScheme(BaseModel):
    scheme_id:        str
    score:            float
    status:           str
    matched_criteria: dict
    name:             str
    ministry:         str
    category:         str
    state:            str
    benefit_type:     str
    benefit_amount:   str
    application_url:  str
    description:      str


class MatchResponse(BaseModel):
    total_schemes: int
    returned:      int
    elapsed_ms:    float
    results:       list[MatchedScheme]


class SearchRequest(BaseModel):
    query:    str  = Field(..., min_length=3, example="schemes for poor farmers who lost crops in flood")
    #language: str  = Field("en", example="en",
    #                      description="Query language code: en / hi / ta / te / bn / ...\n"
    #                                  "Note: default model (all-MiniLM-L6-v2) is English-only.\n"
    #                                  "Switch to LaBSE in embed.py + search.py for multilingual support.")
    #For Multilingual Model
    language: str  = Field("en", example="en",
                          description="Query language code: en / hi / ta / te / bn / ...\n"
                                      "Search runs on LaBSE, a cross-lingual embedding model, "
                                      "so queries in Hindi/Tamil/Telugu/Kannada/etc. are matched "
                                      "directly with no separate translation step.")
    top_k:    int  = Field(5, ge=1, le=50)
    state:    str | None = Field(None, description="Filter results to this state only. Central schemes always included.")


class SearchResult(BaseModel):
    scheme_id:       str
    relevance_score: float
    name:            str
    category:        str
    state:           str
    snippet:         str   # short excerpt from description, for display


class SearchResponse(BaseModel):
    query:      str
    language:   str
    model:      str
    elapsed_ms: float
    returned:   int
    results:    list[SearchResult]


class ExtractCriteriaRequest(BaseModel):
    text:       str = Field(..., min_length=10,
                            description="Raw scheme eligibility text",
                            example="The applicant must be female, aged between 18 and 60 years, "
                                    "belonging to SC/ST/OBC category, with annual family income "
                                    "below Rs 1,00,000. Must have a valid Aadhar card.")
    state_hint: str = Field("any", description="Scheme's state, if known")


# --- POST /match ---

@app.post("/match", response_model=MatchResponse,
          summary="Score all schemes for a user profile")
def match(req: MatchRequest):
    _status_order = {
        "NOT_ELIGIBLE": 0, "CHECK_REQUIRED": 1,
        "LIKELY_ELIGIBLE": 2, "ELIGIBLE": 3,
    }
    min_order = _status_order.get(req.min_status, 2)

    schemes = _get_schemes()
    booster = _get_booster()
    user    = req.user.model_dump()
    t0      = time.time()

    fvs = np.stack([
        build_feature_vector(user, elig)
        for elig in _eligibilities
    ]).astype(np.float32)

    dmat   = xgb.DMatrix(fvs, feature_names=FEATURE_NAMES)
    scores = booster.predict(dmat)

    results = []
    density_by_scheme_id: dict[str, int] = {}
    for i, (scheme, raw_score) in enumerate(zip(schemes, scores)):
        score  = float(np.clip(raw_score, 0.0, 1.0))
        status = score_to_status(score)
        if _status_order[status] < min_order:
            continue
        scheme_id = scheme.get("slug") or scheme.get("source_id") or scheme.get("name", "")
        elig = _eligibilities[i]
        density_by_scheme_id[scheme_id] = _constraint_density(elig)
        results.append(MatchedScheme(
            scheme_id        = scheme_id,
            score            = round(score, 4),
            status           = status,
            matched_criteria = _matched_criteria(user, elig),
            name             = scheme.get("name", ""),
            ministry         = scheme.get("ministry", ""),
            category         = scheme.get("category", ""),
            state            = scheme.get("state", ""),
            benefit_type     = scheme.get("benefit_type", ""),
            benefit_amount   = scheme.get("benefit_amount", ""),
            application_url  = scheme.get("application_url", ""),
            description      = (scheme.get("description") or "")[:300],
        ))

    results.sort(key=lambda x: (-x.score, -density_by_scheme_id.get(x.scheme_id, 0)))
    results = results[:req.top_n]

    return MatchResponse(
        total_schemes = len(schemes),
        returned      = len(results),
        elapsed_ms    = round((time.time() - t0) * 1000, 1),
        results       = results,
    )


# --- POST /search ---

@app.post("/search", response_model=SearchResponse,
          summary="Semantic search over schemes")
def search(req: SearchRequest):
    if req.language != "en":
        # Non-English queries: warn but still try (results will be poor
        # until embed.py is re-run with MODEL_NAME="LaBSE")
        pass

    engine = _get_search()
    t0 = time.time()
    raw = engine.query(req.query, top_k=req.top_k)
    meta = raw[0].pop("_meta", {}) if raw else {}

    results = []
    for r in raw:
        # Generate a short snippet: first sentence of description that
        # contains at least one query word (rough but fast, no extra deps)
        desc = r.get("description", "")
        query_words = set(req.query.lower().split())
        snippet = ""
        for sentence in desc.replace(". ", ".|").split("|"):
            if any(w in sentence.lower() for w in query_words):
                snippet = sentence.strip()[:200]
                break
        if not snippet:
            snippet = desc[:200]

        results.append(SearchResult(
            scheme_id       = r.get("name", ""),   # replaced by real slug once embed index has it
            relevance_score = r["score"],
            name            = r["name"],
            category        = r["category"],
            state           = r["state"],
            snippet         = snippet,
        ))

    return SearchResponse(
        query      = req.query,
        language   = req.language,
        #For MultoLanguage Model
        #model      = meta.get("model", "LaBSE"),
        model      = meta.get("model", "all-MiniLM-L6-v2"),
        elapsed_ms = round((time.time() - t0) * 1000, 1),
        returned   = len(results),
        results    = results,
    )


# --- POST /extract-criteria ---

@app.post("/extract-criteria",
          summary="Extract structured eligibility JSON from raw scheme text")
def extract_criteria(req: ExtractCriteriaRequest):
    """
    Used by Java's POST /api/admin/schemes/parse-url — Java fetches the
    URL's text content, sends it here, gets back structured eligibility_json
    to store in the DB without manual data entry.
    """
    t0     = time.time()
    result = extract_eligibility(req.text, state_hint=req.state_hint)
    return {
        "eligibility_json": result,
        "elapsed_ms":       round((time.time() - t0) * 1000, 1),
        "input_length":     len(req.text),
    }


# --- Health ---

@app.get("/health", include_in_schema=False)
def health():
    return {
        "status":          "ok",
        "schemes_loaded":  _schemes is not None,
        "model_loaded":    _booster is not None,
        "embed_index":     EMBED_PATH.exists(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
"""
ml/semantic_search/embed.py
=============================
Builds the scheme embedding index used by semantic search.

Encodes each scheme as a single text string combining its name,
category, description, and key eligibility fields — then saves the
resulting matrix as a .npy file alongside a slug lookup list.

Run once (or after any update to schemes_normalized.json):
    python -m ml.semantic_search.embed

Output:
    ml/semantic_search/scheme_embeddings.npy   ← float32 (N, 384)
    ml/semantic_search/scheme_slugs.json       ← list of N slugs (index → slug)

Runtime: ~60s for 4789 schemes on CPU. Embeddings are ~7MB on disk.
The index is loaded once at API startup and kept in memory (~28MB).

Swapping models:
    Change MODEL_NAME to "LaBSE" for multilingual support (Hindi/Tamil/etc.)
    Everything else is identical — LaBSE outputs 768-dim vectors instead of
    384-dim, which is handled automatically at search time.
"""
import os
import json
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

os.environ["TRANSFORMERS_OFFLINE"] = "1" 
#for multilingual model
MODEL_NAME    = "LaBSE"
#MODEL_NAME    = "all-MiniLM-L6-v2"
MODEL_CACHE_DIR = Path("ml/semantic_search/model_cache")
SCHEMES_PATH  = Path("data/processed/schemes_normalized.json")
EMBED_OUT     = Path("ml/semantic_search/scheme_embeddings.npy")
SLUGS_OUT     = Path("ml/semantic_search/scheme_slugs.json")
BATCH_SIZE    = 128


def _scheme_to_text(scheme: dict) -> str:
    """
    Concatenate the fields that best represent what a scheme is about.
    Order matters — sentence transformers weight earlier tokens more.
    We put name first (most discriminative), then category and state
    for filtering context, then description, then key eligibility fields
    as a human-readable sentence.
    """
    parts = []

    name = scheme.get("name") or ""
    if name:
        parts.append(name)

    cat = scheme.get("category") or ""
    subcat = scheme.get("subcategory") or ""
    state = scheme.get("state") or ""
    if cat:
        parts.append(f"{cat}{' - ' + subcat if subcat else ''} ({state})")

    desc = (scheme.get("description") or "")[:400]
    if desc:
        parts.append(desc)

    # Eligibility summary as natural language — gives the model signal on
    # who the scheme targets without requiring it to parse JSON.
    elig = scheme.get("eligibility_json") or {}
    elig_parts = []

    gender = elig.get("gender", "all")
    if gender != "all":
        elig_parts.append(f"For {gender}s")

    age = elig.get("age") or {}
    if age.get("min") and age.get("max"):
        elig_parts.append(f"aged {age['min']} to {age['max']}")
    elif age.get("min"):
        elig_parts.append(f"aged above {age['min']}")
    elif age.get("max"):
        elig_parts.append(f"aged below {age['max']}")

    castes = elig.get("caste") or []
    if castes:
        elig_parts.append(f"belonging to {'/'.join(castes)}")

    inc = elig.get("income_limit") or {}
    if inc.get("bpl_only"):
        elig_parts.append("below poverty line families")
    elif inc.get("annual_inr"):
        elig_parts.append(f"with income below Rs {inc['annual_inr']:,}")

    occs = elig.get("occupation") or []
    if occs:
        elig_parts.append(f"occupation: {', '.join(occs)}")

    if elig.get("disability"):
        elig_parts.append("for persons with disability")

    if elig_parts:
        parts.append("Eligibility: " + "; ".join(elig_parts) + ".")

    return " | ".join(parts)


def build_index(
    schemes_path: Path = SCHEMES_PATH,
    embed_out: Path = EMBED_OUT,
    slugs_out: Path = SLUGS_OUT,
    model_name: str = MODEL_NAME,
    batch_size: int = BATCH_SIZE,
):
    print(f"Loading schemes from {schemes_path}...")
    schemes = json.loads(schemes_path.read_text(encoding="utf-8"))
    print(f"  {len(schemes)} schemes loaded")

    print(f"Loading model: {model_name}")
    MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    model = SentenceTransformer(model_name, cache_folder=str(MODEL_CACHE_DIR))
    texts = [_scheme_to_text(s) for s in schemes]
    slugs = [s.get("slug") or s.get("source_id") or s.get("name", "") for s in schemes]

    print(f"Encoding {len(texts)} scheme texts (batch_size={batch_size})...")
    t0 = time.time()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,   # L2-normalise → dot product == cosine similarity
        convert_to_numpy=True,
    )
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s  shape={embeddings.shape}  dtype={embeddings.dtype}")

    embed_out.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(embed_out), embeddings.astype(np.float32))
    slugs_out.write_text(json.dumps(slugs, ensure_ascii=False), encoding="utf-8")

    print(f"Saved:")
    print(f"  {embed_out}  ({embed_out.stat().st_size / 1e6:.1f} MB)")
    print(f"  {slugs_out}")
    return embeddings, slugs


if __name__ == "__main__":
    build_index()

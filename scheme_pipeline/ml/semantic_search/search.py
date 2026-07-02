"""
ml/semantic_search/search.py
==============================
Semantic search over scheme embeddings using cosine similarity.

Loads the pre-built embedding index (ml/semantic_search/scheme_embeddings.npy)
once at startup, then answers queries in <20ms by:
  1. Encoding the user's query with the same sentence-transformer model
  2. Computing dot product against all scheme embeddings (= cosine similarity
     since embeddings are L2-normalised at index build time)
  3. Returning the top-k schemes by score

Usage:
    from ml.semantic_search.search import SemanticSearch

    search = SemanticSearch()   # load once at API startup

    # For multilingual support, change MODEL_NAME in embed.py + search.py to "LaBSE" and re-run embed.py
    #results = search.query("मैं किसान हूं, 2 एकड़ जमीन, सालाना 80,000 कमाता हूं")
    results = search.query("schemes for poor farmers who lost crops in flood")
    for r in results:
        print(r["score"], r["name"])

Swapping to LaBSE (multilingual, Hindi support):
    search = SemanticSearch(model_name="LaBSE")
    # Make sure embed.py was also run with MODEL_NAME="LaBSE" first.
"""

import json
import time
from pathlib import Path
from typing import Any

import numpy as np

#For multilingual model 
#MODEL_NAME   = "LaBSE"
MODEL_NAME   = "all-MiniLM-L6-v2"
EMBED_PATH   = Path("ml/semantic_search/scheme_embeddings.npy")
SLUGS_PATH   = Path("ml/semantic_search/scheme_slugs.json")
SCHEMES_PATH = Path("data/processed/schemes_normalized.json")


class SemanticSearch:
    """
    Loads the embedding index and scheme metadata once at init, then answers
    queries in a single matrix multiply. Typical query latency: 5–20ms
    (LaBSE encoding of the query itself adds a few ms more than MiniLM did,
    since it's a larger model — still well under 100ms on CPU for one query).
    """

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        embed_path: Path = EMBED_PATH,
        slugs_path: Path = SLUGS_PATH,
        schemes_path: Path = SCHEMES_PATH,
    ):
        if not embed_path.exists():
            raise FileNotFoundError(
                f"{embed_path} not found — run `python -m ml.semantic_search.embed` first."
            )

        # Lazy import so the module can be imported without torch if needed
        from sentence_transformers import SentenceTransformer

        print(f"Loading semantic search model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.model_name = model_name

        print(f"Loading embedding index from {embed_path}...")
        self.embeddings = np.load(str(embed_path))          # (N, dim) float32
        self.slugs = json.loads(slugs_path.read_text(encoding="utf-8"))

        # Build slug → scheme lookup for result hydration
        schemes = json.loads(schemes_path.read_text(encoding="utf-8"))
        self._scheme_by_slug = {
            (s.get("slug") or s.get("source_id") or s.get("name", "")): s
            for s in schemes
        }

        print(f"  Index: {self.embeddings.shape[0]} schemes × {self.embeddings.shape[1]} dims")

    def query(
        self,
        text: str,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """
        Semantic search over all schemes. `text` may be in any language
        LaBSE supports (English, Hindi, Tamil, Telugu, Kannada, etc.) —
        no translation is applied or needed.

        Args:
            text:      free-form natural language query, (any supported language)->not for all-MiniLM-L6-v2
            top_k:     number of results to return
            min_score: minimum cosine similarity threshold (0–1)

        Returns:
            List of dicts sorted by similarity score descending, each with:
              name, ministry, category, state, description,
              benefit_type, benefit_amount, application_url,
              score (cosine similarity 0–1), eligibility_json
        """
        t0 = time.time()

        # Encode query with same normalisation as index
        query_vec = self.model.encode(
            [text],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0]                                              # (dim,)

        # Cosine similarity = dot product (embeddings already L2-normalised)
        scores = self.embeddings @ query_vec              # (N,)

        # Top-k by score
        top_indices = np.argsort(scores)[::-1][:top_k * 3]   # over-fetch then filter
        elapsed_ms = (time.time() - t0) * 1000

        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score < min_score:
                continue
            slug = self.slugs[idx]
            scheme = self._scheme_by_slug.get(slug, {})
            results.append({
                "name":            scheme.get("name", slug),
                "ministry":        scheme.get("ministry", ""),
                "category":        scheme.get("category", ""),
                "subcategory":     scheme.get("subcategory", ""),
                "state":           scheme.get("state", ""),
                "description":     (scheme.get("description") or "")[:400],
                "benefit_type":    scheme.get("benefit_type", ""),
                "benefit_amount":  scheme.get("benefit_amount", ""),
                "application_url": scheme.get("application_url", ""),
                "eligibility_json": scheme.get("eligibility_json", {}),
                "score":           round(score, 4),
            })
            if len(results) >= top_k:
                break

        if results:
            results[0]["_meta"] = {
                "model":      self.model_name,
                "query":      text,
                "elapsed_ms": round(elapsed_ms, 1),
                "index_size": len(self.slugs),
            }

        return results


# ── Quick CLI test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    search = SemanticSearch()
    queries = [
        "schemes for poor farmers who lost crops in flood",
        #"मैं किसान हूं, 2 एकड़ जमीन, सालाना 80,000 कमाता हूं",
        "financial help for widow women",
        "scholarship for SC ST students",
        "disability pension scheme",
        "housing scheme for below poverty line families",
    ]
    for q in queries:
        print(f"\n{'─'*65}")
        print(f"QUERY: {q}")
        results = search.query(q, top_k=5)
        meta = results[0].pop("_meta", {}) if results else {}
        print(f"  {meta.get('elapsed_ms', 0):.0f}ms")
        for r in results:
            print(f"  {r['score']:.3f}  {r['name'][:60]}")
            print(f"         {r['category']} | {r['state']}")

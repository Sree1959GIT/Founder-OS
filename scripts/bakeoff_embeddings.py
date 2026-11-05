"""Embedding comparison: retrieval quality on labelled queries over the sample vault, latency and VRAM.

    python scripts/bakeoff_embeddings.py
    python scripts/bakeoff_embeddings.py --models nomic-embed-text,embeddinggemma,mxbai-embed-large

EmbeddingGemma: pull it first with `docker exec ollama ollama pull embeddinggemma`. Each model gets its correct task
prefixes (see `engine/embeddings.task_prefixes`). Uses a private copy of the sample vault. Changes no default.
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger

from app.engine.embeddings import OllamaEmbedder
from app.evals.decision_bakeoff import table
from app.evals.embedding_bakeoff import HEADERS, load_queries, loaded_vram_gb, recommend, score_embedder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", default="nomic-embed-text,embeddinggemma")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    logger.remove()
    queries = load_queries()
    scores = []
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        score = score_embedder(OllamaEmbedder(args.ollama_url, model, timeout_s=300.0), queries)
        score.vram_gb = loaded_vram_gb(args.ollama_url, model)
        scores.append(score)
        print(f"... {model}: {'failed, ' + score.error if score.error else 'done'}", flush=True)
    print()
    print(f"EMBEDDING BAKE-OFF on {len(queries)} labelled queries over the sample vault")
    print(table(HEADERS, [row for s in scores for row in s.rows()]))
    print("READING:", recommend(scores, args.models.split(",")[0].strip()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

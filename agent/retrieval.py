"""Hybrid retrieval: BM25 (exact words) + dense embeddings (meaning), fused with RRF.

Why both: "markup in Singapore" needs the literal word 'markup' (BM25 is good at that);
"I don't pay in full" needs to land on 'revolve rate' (only embeddings get that).

Why RRF and not adding scores: BM25 scores are unbounded (0..~10) and cosine is -1..1,
so a weighted sum is dominated by whichever scale is bigger. RRF only uses ranks:
score(chunk) = sum over retrievers of 1 / (k + rank). k=60 is the value from the original
RRF paper; it damps the gap between rank 1 and rank 2 so one retriever can't dominate.

Everything is in memory: 16 chunks embed in well under a second. No vector DB at this size.
"""
import re
from dataclasses import dataclass

import numpy as np
from fastembed import TextEmbedding
from rank_bm25 import BM25Okapi

from agent.corpus import Chunk, load_corpus

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
RRF_K = 60


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower())


@dataclass
class Hit:
    chunk: Chunk
    rrf_score: float
    bm25_rank: int
    dense_rank: int
    bm25_score: float
    cosine: float


class HybridRetriever:
    def __init__(self, chunks: list[Chunk] | None = None):
        self.chunks = chunks if chunks is not None else load_corpus()
        texts = [c.for_search() for c in self.chunks]
        self.bm25 = BM25Okapi([tokenize(t) for t in texts])
        self.embedder = TextEmbedding(EMBED_MODEL)
        # bge vectors come back L2-normalised, so a dot product is cosine similarity.
        self.vectors = np.array(list(self.embedder.passage_embed(texts)))

    def search(self, query: str, top_k: int = 5) -> list[Hit]:
        bm25_scores = self.bm25.get_scores(tokenize(query))
        cosines = self.vectors @ next(iter(self.embedder.query_embed(query)))

        bm25_rank = _ranks(bm25_scores)
        dense_rank = _ranks(cosines)
        hits = [
            Hit(
                chunk=c,
                rrf_score=1 / (RRF_K + bm25_rank[i]) + 1 / (RRF_K + dense_rank[i]),
                bm25_rank=bm25_rank[i],
                dense_rank=dense_rank[i],
                bm25_score=float(bm25_scores[i]),
                cosine=float(cosines[i]),
            )
            for i, c in enumerate(self.chunks)
        ]
        return sorted(hits, key=lambda h: h.rrf_score, reverse=True)[:top_k]


def _ranks(scores: np.ndarray) -> list[int]:
    """1-based rank of each position, highest score = rank 1."""
    order = np.argsort(-scores)
    ranks = np.empty(len(scores), dtype=int)
    ranks[order] = np.arange(1, len(scores) + 1)
    return ranks.tolist()

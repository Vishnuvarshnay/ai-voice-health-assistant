"""In-memory FAISS index over hospital service utterances."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List

import faiss
import numpy as np

from app.core.logging import logger
from app.services.embedding_service import embedding_service


@dataclass
class IndexedUtterance:
    service_id: int
    service_code: str
    service_name: str
    utterance: str


class FaissIndex:
    """
    Inner-product index over L2-normalized BGE-M3 embeddings, so IP == cosine.
    Each hospital service contributes multiple example utterances; we return
    the best-matching service across all its utterances.
    """

    def __init__(self) -> None:
        self._index: faiss.IndexFlatIP | None = None
        self._entries: List[IndexedUtterance] = []
        self._lock = asyncio.Lock()

    @property
    def size(self) -> int:
        return len(self._entries)

    async def build(self, entries: List[IndexedUtterance]) -> None:
        async with self._lock:
            if not entries:
                self._index = None
                self._entries = []
                logger.warning("faiss.build.empty")
                return

            vecs = await embedding_service.encode([e.utterance for e in entries])
            dim = vecs.shape[1]
            index = faiss.IndexFlatIP(dim)
            index.add(vecs)
            self._index = index
            self._entries = entries
            logger.info("faiss.built", entries=len(entries), dim=dim)

    async def search(self, query: str, top_k: int = 5) -> List[dict]:
        if self._index is None or not self._entries:
            return []

        qvec = await embedding_service.encode([query])
        k = min(top_k, len(self._entries))
        scores, indices = self._index.search(qvec, k)

        # Aggregate best score per service.
        best: dict[int, dict] = {}
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            e = self._entries[int(idx)]
            sc = float(score)
            existing = best.get(e.service_id)
            if existing is None or sc > existing["semantic_score"]:
                best[e.service_id] = {
                    "service_id": e.service_id,
                    "service_code": e.service_code,
                    "service_name": e.service_name,
                    "matched_utterance": e.utterance,
                    "semantic_score": sc,
                }

        return sorted(best.values(), key=lambda x: x["semantic_score"], reverse=True)


faiss_index = FaissIndex()

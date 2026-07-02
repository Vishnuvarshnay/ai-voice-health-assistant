"""BGE-M3 embedding wrapper (multilingual)."""
from __future__ import annotations

import asyncio
from typing import Iterable

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.core.logging import logger


class EmbeddingService:
    """
    Wraps `sentence-transformers/BAAI/bge-m3` (multilingual, 1024-d, dense).
    Loaded once at process start; encode() runs in a thread executor so it
    doesn't block the asyncio loop.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self._model: SentenceTransformer | None = None
        self._lock = asyncio.Lock()

    async def load(self) -> None:
        if self._model is not None:
            return
        async with self._lock:
            if self._model is not None:
                return
            logger.info("embedding.loading", model=self.model_name)
            loop = asyncio.get_running_loop()
            self._model = await loop.run_in_executor(
                None, lambda: SentenceTransformer(self.model_name)
            )
            logger.info(
                "embedding.loaded",
                model=self.model_name,
                dim=self._model.get_sentence_embedding_dimension(),
            )

    @property
    def dim(self) -> int:
        assert self._model is not None, "EmbeddingService not loaded"
        return self._model.get_sentence_embedding_dimension()

    async def encode(self, texts: Iterable[str]) -> np.ndarray:
        assert self._model is not None, "EmbeddingService not loaded"
        loop = asyncio.get_running_loop()
        vecs = await loop.run_in_executor(
            None,
            lambda: self._model.encode(
                list(texts),
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            ),
        )
        return vecs.astype("float32")


embedding_service = EmbeddingService()

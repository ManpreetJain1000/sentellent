from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable

from app.core.config import Settings


class EmbeddingService:
    """Deterministic local embedding provider for Phase 1 semantic retrieval."""

    def __init__(self, settings: Settings) -> None:
        self.dimensions = settings.pgvector_embedding_dimensions
        self.model_name = settings.embedding_model_name

    def embed_text(self, text: str) -> list[float]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        vector = [0.0] * self.dimensions
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for index in range(self.dimensions):
                byte_value = digest[index % len(digest)]
                vector[index] += ((byte_value / 255.0) * 2.0) - 1.0

        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_many(self, texts: Iterable[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

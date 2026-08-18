import asyncio
from functools import lru_cache
from typing import Protocol

import voyageai

from app.config import get_settings


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class VoyageEmbeddingProvider:
    """EmbeddingProvider backed by Voyage AI (Anthropic's recommended embeddings partner --
    Anthropic itself has no embeddings endpoint)."""

    def __init__(self, api_key: str, model: str = "voyage-3") -> None:
        self._client = voyageai.Client(api_key=api_key)
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        def _embed_sync() -> list[list[float]]:
            result = self._client.embed(texts, model=self._model, input_type="document")
            return [[float(x) for x in embedding] for embedding in result.embeddings]

        return await asyncio.to_thread(_embed_sync)


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.EMBEDDING_PROVIDER == "voyage":
        return VoyageEmbeddingProvider(
            api_key=settings.VOYAGE_API_KEY, model=settings.EMBEDDING_MODEL
        )
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {settings.EMBEDDING_PROVIDER!r}")

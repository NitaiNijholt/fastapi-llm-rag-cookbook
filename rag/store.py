"""ChromaDB persistence and semantic search."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

from rag.chunking import chunk_text
from rag.config import (
    CHROMA_HOST,
    CHROMA_PATH,
    CHROMA_PORT,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    TOP_K,
)

logger = logging.getLogger(__name__)

# Retries only for remote Chroma (Docker); embedded local DB connects immediately.
_REMOTE_RETRIES = 10
_REMOTE_DELAY_SEC = 3


def _create_chroma_client() -> chromadb.ClientAPI:
    """Use HttpClient against the chroma container, else local PersistentClient."""
    if CHROMA_HOST:
        return chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    return chromadb.PersistentClient(path=str(CHROMA_PATH))


class RagStore:
    """Thin wrapper around a Chroma collection (embedded or remote)."""

    def __init__(self) -> None:
        """Connect to Chroma and ensure the documents collection exists."""
        embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL,
        )
        retries = _REMOTE_RETRIES if CHROMA_HOST else 1
        delay = _REMOTE_DELAY_SEC if CHROMA_HOST else 0
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                self._client = _create_chroma_client()
                self._collection = self._client.get_or_create_collection(
                    name=COLLECTION_NAME,
                    embedding_function=embedding_fn,
                )
                if CHROMA_HOST:
                    mode = f"http://{CHROMA_HOST}:{CHROMA_PORT}"
                else:
                    mode = str(CHROMA_PATH)
                logger.info("Chroma connected (%s)", mode)
                return
            except Exception as exc:
                last_error = exc
                if retries > 1:
                    logger.warning(
                        "Chroma connect attempt %s/%s failed: %s",
                        attempt,
                        retries,
                        exc,
                    )
                    time.sleep(delay)
        msg = f"Could not connect to Chroma after {retries} attempts"
        raise RuntimeError(msg) from last_error

    @property
    def chroma_mode(self) -> str:
        """Return ``http`` or ``embedded`` for health reporting."""
        return "http" if CHROMA_HOST else "embedded"

    @property
    def document_count(self) -> int:
        """Number of indexed chunks currently stored."""
        return self._collection.count()

    def ingest_text(
        self,
        text: str,
        *,
        source: str = "upload",
    ) -> int:
        """Chunk, embed, and store one document.

        Returns:
            Count of chunks written.

        """
        chunks = chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        if not chunks:
            return 0

        ids: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            chunk_id = hashlib.sha1(f"{source}:{index}:{chunk}".encode()).hexdigest()
            ids.append(chunk_id)
            metadatas.append({"source": source, "chunk_index": index})

        # Chroma embeds ``documents`` via the collection embedding function.
        self._collection.upsert(documents=chunks, metadatas=metadatas, ids=ids)
        return len(chunks)

    def retrieve(self, question: str, top_k: int = TOP_K) -> list[str]:
        """Return the most relevant chunk texts for a user question.

        Args:
            question: Natural-language query.
            top_k: Number of chunks to retrieve.

        Returns:
            Chunk strings ordered by similarity (best first).

        """
        if self._collection.count() == 0:
            return []

        results = self._collection.query(query_texts=[question], n_results=top_k)
        documents = results.get("documents") or []
        if not documents or not documents[0]:
            return []
        return list(documents[0])

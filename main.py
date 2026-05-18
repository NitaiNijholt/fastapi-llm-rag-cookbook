"""FastAPI service: local instruct LLM generation and ChromaDB-backed RAG."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from transformers import pipeline

from rag import generation as rag_generation
from rag.config import GENERATION_MODEL, TOP_K
from rag.store import RagStore

APP_DESCRIPTION = (
    "Local instruct-model text generation plus retrieval-augmented Q&A with ChromaDB. "
)


class InputText(BaseModel):
    """Request body for POST /generate."""

    text: str = Field(
        ..., min_length=1, description="Seed prompt for the local instruct model."
    )


class IngestRequest(BaseModel):
    """Request body for POST /rag/ingest."""

    text: str = Field(..., min_length=1, description="Raw document text to index.")
    source: str = Field(default="api", description="Label stored in chunk metadata.")


class AskRequest(BaseModel):
    """Request body for POST /rag/ask."""

    question: str = Field(..., min_length=1, description="User question.")
    top_k: int = Field(default=TOP_K, ge=1, le=10, description="Chunks to retrieve.")


def load_text_generator():
    """Load the shared Hugging Face pipeline once during app startup."""
    return pipeline(
        "text-generation",
        model=GENERATION_MODEL,
        device="cpu",
        dtype="auto",
    )


def get_rag_store(request: Request) -> RagStore:
    """Return the app-scoped RAG store."""
    return request.app.state.rag_store


def get_text_generator(request: Request):
    """Return the app-scoped text-generation pipeline."""
    return request.app.state.text_generator


def create_app(*, load_runtime: bool = True) -> FastAPI:
    """Create the FastAPI app.

    Tests can disable runtime loading to avoid model downloads and Chroma setup.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if load_runtime:
            app.state.text_generator = load_text_generator()
            app.state.rag_store = RagStore()
        yield

    app = FastAPI(
        title="FastAPI LLM & RAG Cookbook",
        description=APP_DESCRIPTION,
        lifespan=lifespan,
    )

    @app.get("/health")
    def health(request: Request) -> dict[str, str | int]:
        """Report API status, Chroma mode, indexed chunk count, and generation model."""
        rag_store = get_rag_store(request)
        return {
            "status": "ok",
            "chroma_mode": rag_store.chroma_mode,
            "indexed_chunks": rag_store.document_count,
            "generation_model": GENERATION_MODEL,
        }

    @app.post("/generate")
    def generate_text(request: Request, payload: InputText) -> dict[str, str]:
        """Complete the given prompt with the local instruct model."""
        text_generator = get_text_generator(request)
        outputs = text_generator(payload.text, **rag_generation.generation_kwargs())
        return {"generated_text": outputs[0]["generated_text"]}

    @app.post("/rag/ingest")
    def rag_ingest(request: Request, payload: IngestRequest) -> dict[str, int | str]:
        """Chunk, embed, and store document text in ChromaDB."""
        rag_store = get_rag_store(request)
        chunk_count = rag_store.ingest_text(payload.text, source=payload.source)
        if chunk_count == 0:
            raise HTTPException(
                status_code=400,
                detail="No text to ingest after cleaning.",
            )
        return {
            "source": payload.source,
            "chunks_added": chunk_count,
            "total_chunks": rag_store.document_count,
        }

    @app.post("/rag/ask")
    def rag_ask(request: Request, payload: AskRequest) -> dict[str, str | list[str]]:
        """Retrieve relevant chunks, then answer using that context."""
        rag_store = get_rag_store(request)
        text_generator = get_text_generator(request)
        sources = rag_store.retrieve(payload.question, top_k=payload.top_k)
        answer = rag_generation.generate_answer(
            text_generator,
            payload.question,
            sources,
        )
        return {
            "question": payload.question,
            "answer": answer,
            "sources": sources,
        }

    return app


app = create_app()

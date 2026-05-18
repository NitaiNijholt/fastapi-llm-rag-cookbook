"""Tests for FastAPI route wiring with mocked runtime dependencies."""

from fastapi.testclient import TestClient

from main import create_app


class FakeStore:
    """RAG store fake with deterministic ingest and retrieval behavior."""

    chroma_mode = "embedded"

    def __init__(self) -> None:
        """Initialize collection count."""
        self.document_count = 2
        self.ingested: tuple[str, str] | None = None
        self.retrieved: tuple[str, int] | None = None

    def ingest_text(self, text: str, *, source: str) -> int:
        """Capture ingested text and source."""
        self.ingested = (text, source)
        self.document_count += 1
        return 1

    def retrieve(self, question: str, *, top_k: int) -> list[str]:
        """Capture retrieval args and return one source chunk."""
        self.retrieved = (question, top_k)
        return ["ChromaDB stores embeddings for semantic search."]


class FakeTokenizer:
    """Tokenizer fake for route tests."""

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
    ) -> str:
        """Return a deterministic prompt."""
        return "prompt"


class FakeGenerator:
    """Text-generation fake returning deterministic text."""

    def __init__(self) -> None:
        """Initialize fake tokenizer."""
        self.tokenizer = FakeTokenizer()

    def __call__(self, prompt: str, **kwargs) -> list[dict[str, str]]:
        """Return generated text for any prompt."""
        return [{"generated_text": "generated answer"}]


def build_client() -> tuple[TestClient, FakeStore]:
    """Create a TestClient with mocked app state."""
    app = create_app(load_runtime=False)
    store = FakeStore()
    app.state.rag_store = store
    app.state.text_generator = FakeGenerator()
    return TestClient(app), store


def test_health_reports_runtime_state() -> None:
    """Health endpoint reads state from the injected store."""
    client, _store = build_client()

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["chroma_mode"] == "embedded"
    assert payload["indexed_chunks"] == 2


def test_generate_uses_injected_generator() -> None:
    """Generate endpoint uses the app-scoped text generator."""
    client, _store = build_client()

    response = client.post("/generate", json={"text": "Once upon a time,"})

    assert response.status_code == 200
    assert response.json() == {"generated_text": "generated answer"}


def test_rag_ingest_uses_injected_store() -> None:
    """Ingest endpoint delegates to the app-scoped store."""
    client, store = build_client()

    response = client.post(
        "/rag/ingest",
        json={"text": "A useful document.", "source": "test"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "source": "test",
        "chunks_added": 1,
        "total_chunks": 3,
    }
    assert store.ingested == ("A useful document.", "test")


def test_rag_ask_uses_retrieval_and_generator() -> None:
    """Ask endpoint retrieves sources and returns generated answer."""
    client, store = build_client()

    response = client.post(
        "/rag/ask",
        json={"question": "What is ChromaDB used for?", "top_k": 1},
    )

    assert response.status_code == 200
    assert response.json() == {
        "question": "What is ChromaDB used for?",
        "answer": "generated answer",
        "sources": ["ChromaDB stores embeddings for semantic search."],
    }
    assert store.retrieved == ("What is ChromaDB used for?", 1)

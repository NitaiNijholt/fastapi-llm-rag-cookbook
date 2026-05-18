"""Tests for RAG prompt construction and generation settings."""

from rag import generation


class FakeTokenizer:
    """Tokenizer fake capturing chat-template input."""

    def __init__(self) -> None:
        """Initialize captured messages."""
        self.messages: list[dict[str, str]] | None = None

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
    ) -> str:
        """Return a deterministic prompt while capturing arguments."""
        self.messages = messages
        assert tokenize is False
        assert add_generation_prompt is True
        return "rendered prompt"


class FakeGenerator:
    """Text-generation pipeline fake."""

    def __init__(self) -> None:
        """Initialize tokenizer and captured call args."""
        self.tokenizer = FakeTokenizer()
        self.prompt: str | None = None
        self.kwargs: dict | None = None

    def __call__(self, prompt: str, **kwargs) -> list[dict[str, str]]:
        """Capture prompt and kwargs, then return a generated answer."""
        self.prompt = prompt
        self.kwargs = kwargs
        return [{"generated_text": "  grounded answer  "}]


def test_build_rag_messages_includes_context_and_question() -> None:
    """RAG messages include grounding instructions, context, and question."""
    messages = generation.build_rag_messages("What is ChromaDB?", ["chunk one"])

    assert messages[0]["role"] == "system"
    assert "Answer only from the context" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "- chunk one" in messages[1]["content"]
    assert "Question: What is ChromaDB?" in messages[1]["content"]


def test_generation_kwargs_use_completion_budget() -> None:
    """Generation settings use max_new_tokens and omit full prompt text."""
    kwargs = generation.generation_kwargs()

    assert "max_new_tokens" in kwargs
    assert "max_length" not in kwargs
    assert kwargs["return_full_text"] is False
    assert kwargs["num_return_sequences"] == 1


def test_generate_answer_uses_explicit_generator() -> None:
    """Answer generation receives the pipeline explicitly and strips output."""
    fake_generator = FakeGenerator()

    answer = generation.generate_answer(
        fake_generator,
        "What is ChromaDB?",
        ["ChromaDB stores embeddings."],
    )

    assert answer == "grounded answer"
    assert fake_generator.prompt == "rendered prompt"
    assert fake_generator.kwargs == generation.generation_kwargs()
    assert fake_generator.tokenizer.messages is not None


def test_generate_answer_without_context_short_circuits() -> None:
    """Empty retrieval result avoids model calls."""
    fake_generator = FakeGenerator()

    answer = generation.generate_answer(fake_generator, "Question?", [])

    assert answer == "No documents indexed yet. Ingest text before asking questions."
    assert fake_generator.prompt is None

"""Build prompts and run local instruct model for RAG answers."""

from __future__ import annotations

from rag.config import (
    GENERATION_TEMPERATURE,
    MAX_NEW_TOKENS,
    REPETITION_PENALTY,
)


def generation_kwargs() -> dict:
    """Shared sampling settings for /generate and /rag/ask."""
    return {
        "max_new_tokens": MAX_NEW_TOKENS,
        "do_sample": True,
        "temperature": GENERATION_TEMPERATURE,
        "repetition_penalty": REPETITION_PENALTY,
        "return_full_text": False,
        "num_return_sequences": 1,
    }


def build_rag_messages(
    question: str,
    context_chunks: list[str],
) -> list[dict[str, str]]:
    """Format retrieved chunks and the user question as chat messages."""
    context = "\n\n".join(f"- {chunk}" for chunk in context_chunks)
    return [
        {
            "role": "system",
            "content": (
                "Answer only from the context. "
                "If the answer is not in the context, say you cannot find it."
            ),
        },
        {
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion: {question}",
        },
    ]


def generate_answer(text_generator, question: str, context_chunks: list[str]) -> str:
    """Generate an answer with the instruct model using retrieved context.

    Args:
        text_generator: Shared Hugging Face text-generation pipeline.
        question: User question.
        context_chunks: Text snippets from Chroma retrieval.

    Returns:
        Model completion text.

    """
    if not context_chunks:
        return "No documents indexed yet. Ingest text before asking questions."

    tokenizer = text_generator.tokenizer
    messages = build_rag_messages(question, context_chunks)
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    outputs = text_generator(prompt, **generation_kwargs())
    return outputs[0]["generated_text"].strip()

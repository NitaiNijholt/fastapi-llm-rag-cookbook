"""Tests for text chunking."""

from rag.chunking import chunk_text


def test_chunk_text_returns_empty_for_blank_input() -> None:
    """Blank or whitespace-only input yields no chunks."""
    assert chunk_text(" \n\t ") == []


def test_chunk_text_normalizes_whitespace() -> None:
    """Runs of whitespace are collapsed before chunking."""
    assert chunk_text("alpha\n\n beta\tgamma", chunk_size=100, overlap=10) == [
        "alpha beta gamma"
    ]


def test_chunk_text_uses_overlap_between_chunks() -> None:
    """Chunk starts move back by the configured overlap."""
    assert chunk_text("abcdefghij", chunk_size=4, overlap=1) == [
        "abcd",
        "defg",
        "ghij",
    ]

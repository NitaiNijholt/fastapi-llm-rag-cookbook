"""Split long documents into overlapping chunks for vector indexing."""


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[str]:
    """Split text into fixed-size chunks with character overlap.

    Args:
        text: Full document body.
        chunk_size: Target maximum characters per chunk.
        overlap: Characters repeated at chunk boundaries for continuity.

    Returns:
        Non-empty chunk strings.

    """
    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = start + chunk_size
        chunks.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = end - overlap

    return chunks

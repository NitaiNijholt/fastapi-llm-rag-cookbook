#!/usr/bin/env python3
"""Ingest .txt files from a directory into the local ChromaDB store."""

from __future__ import annotations

import argparse
from pathlib import Path

from rag.store import RagStore


def ingest_directory(directory: Path) -> int:
    """Load every ``.txt`` file in ``directory`` into Chroma.

    Returns:
        Total chunks indexed.

    """
    store = RagStore()
    total_chunks = 0
    txt_files = sorted(directory.glob("**/*.txt"))
    if not txt_files:
        print(f"No .txt files found under {directory}")
        return 0

    for path in txt_files:
        text = path.read_text(encoding="utf-8")
        count = store.ingest_text(text, source=str(path.relative_to(directory)))
        total_chunks += count
        print(f"  {path.name}: {count} chunks")

    total = store.document_count
    print(f"Done. {total_chunks} chunks indexed ({total} in collection).")
    return total_chunks


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Ingest .txt files into ChromaDB.")
    parser.add_argument(
        "directory",
        type=Path,
        nargs="?",
        default=Path("data/sample_docs"),
        help="Folder with .txt files (default: data/sample_docs)",
    )
    args = parser.parse_args()
    if not args.directory.is_dir():
        raise SystemExit(f"Directory not found: {args.directory}")
    ingest_directory(args.directory)


if __name__ == "__main__":
    main()

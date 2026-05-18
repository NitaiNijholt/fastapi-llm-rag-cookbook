"""Shared RAG configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Optional .env (see .env.example). Compose sets CHROMA_HOST only in the api container.
load_dotenv()

# Local sentence-transformers model (CPU-friendly, 384-dim vectors).
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Empty CHROMA_HOST => embedded Chroma in ./chroma_db/ (no Docker required).
CHROMA_HOST = os.getenv("CHROMA_HOST", "").strip()
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_PATH = Path(__file__).resolve().parent.parent / "chroma_db"
COLLECTION_NAME = "documents"

# Text splitting defaults (aligned with common cookbook tutorials).
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 3

# Local instruct model for /rag/ask and /generate (CPU-friendly).
GENERATION_MODEL = os.getenv(
    "GENERATION_MODEL", "HuggingFaceTB/SmolLM2-360M-Instruct"
)
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "128"))
GENERATION_TEMPERATURE = float(os.getenv("GENERATION_TEMPERATURE", "0.3"))
REPETITION_PENALTY = float(os.getenv("REPETITION_PENALTY", "1.1"))

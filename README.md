# FastAPI LLM & RAG Cookbook

Minimal FastAPI app: **local instruct LLM** plus **RAG** with ChromaDB and local embeddings.

Works **with or without Docker**:

| Mode | Chroma | Command |
|------|--------|---------|
| **Local** (default) | Embedded DB in `./chroma_db/` | `uv run python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000` |
| **Docker** | Separate `chroma` container | `docker compose up --build -d` |

This is an unauthenticated local demo. Do not expose it directly to the public
Internet without adding authentication, rate limits, and a reverse proxy.


Stack: FastAPI, ChromaDB, Pydantic, Transformers, `sentence-transformers/all-MiniLM-L6-v2`, `HuggingFaceTB/SmolLM2-360M-Instruct` for answers (chat template + context grounding).

---

## Requirements

Tested with:

- [uv](https://docs.astral.sh/uv/) `0.8.3`
- Python 3.11+
- `curl` for the command-line API examples
- Docker Engine/Desktop `28.3.0` with Docker Compose `v2.38.1` for optional Docker mode

## Local run (no Docker)

```bash
git clone https://github.com/NitaiNijholt/fastapi-llm-rag-cookbook.git
cd fastapi-llm-rag-cookbook
uv sync                    # installs packages using uv
unset CHROMA_HOST          # important if you used Docker before
uv run python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

First start downloads SmolLM2-360M-Instruct (~700MB) and the embedding model (~90MB).

Wait for startup to finish:

```text
INFO:     Application startup complete.
```

In another terminal, from working directory `fastapi-llm-rag-cookbook`:

### 1. Health check

Wait until the server is up (first start may take a few minutes while models load) then:

```bash
curl http://127.0.0.1:8000/health
# expect: "status": "ok", "chroma_mode": "embedded", "generation_model": "HuggingFaceTB/SmolLM2-360M-Instruct"
```

### 2. Plain generation (no RAG)

Test the instruct model directly — no Chroma, no retrieval:

```bash
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"text": "Once upon a time,"}'
```

### 3. RAG — ingest then ask

Index sample docs:

```bash
uv run python -m scripts.ingest_docs data/sample_docs
```

Test retrieval + grounded answer:

```bash
curl -X POST http://127.0.0.1:8000/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is ChromaDB used for?"}'
```

Optional `.env` from `.env.example` — keep `CHROMA_HOST` empty for local mode. Override `GENERATION_MODEL` to swap the instruct LLM without code changes.

---

## Docker run (optional)

Docker Compose starts two containers: `api` for FastAPI and `chroma` for ChromaDB. The API uses
`CHROMA_HOST=chroma` to reach Chroma on network `rag-net`. Compose binds both services to
`127.0.0.1` by default.

```bash
cd fastapi-llm-rag-cookbook
docker compose up --build -d
curl http://localhost:8000/health   # "chroma_mode": "http"
docker compose -f docker-compose.yml -f docker-compose.ingest.yml run --rm ingest
# or: docker compose exec api python -m scripts.ingest_docs data/sample_docs
```

| Service | URL |
|---------|-----|
| FastAPI | http://localhost:8000 |
| Chroma HTTP | http://localhost:8001 |

Volumes: `chroma_data` (Chroma DB at `/data` in the container), `huggingface_cache` (model weights).

Stop: `docker compose down`

---

## API reference (both modes)

Interactive docs: http://127.0.0.1:8000/docs

Endpoint overview:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/docs` | Interactive FastAPI docs |
| GET | `/health` | Status, `chroma_mode`, chunk count, `generation_model` |
| POST | `/generate` | Instruct-model completion (no retrieval) |
| POST | `/rag/ingest` | Chunk, embed, store |
| POST | `/rag/ask` | Retrieve + answer |

## Testing

### Unit tests

Fast checks for chunking, prompt construction, and FastAPI route wiring. No model
download or Chroma server required.

```bash
uv run ruff check .
uv run pytest
```

### README regression test

Runs the documented local flow end to end and writes logs.

```bash
uv run bash tests/readme_retest.sh
# logs: logs/readme_retest_<timestamp>.log
```

### Oracle Linux 9 integration test

Full Docker + ingest + RAG + host `pytest` inside an OL9 environment (dev: WSL +
Docker Desktop; deploy: `RUN_ON_HOST_OL9=1` on the server).

```bash
./scripts/ol9-integration-test.sh
# logs/ol9_integration_<timestamp>.log
```

---

## Project layout

```
fastapi-llm-rag-cookbook/
  main.py                   # FastAPI routes
  .env.example              # copy to .env (optional)
  rag/
    config.py               # CHROMA_HOST, chunk sizes
    store.py                # PersistentClient OR HttpClient
    chunking.py
    generation.py
  scripts/ingest_docs.py
  scripts/ol9-integration-test.sh
  scripts/ol9-run-tests-inner.sh
  data/sample_docs/         # example .txt files
  tests/                    # unit tests + README regression test
  chroma_db/                # local vectors (gitignored, created on first ingest)
  logs/                     # retest output (gitignored)
  docker-compose.yml
  docker-compose.ingest.yml
  Dockerfile
```

## References

| Part | Article |
|------|---------|
| LLM serving | [FastAPI Cookbook for LLMs and Embedding Models](https://medium.com/@krishnaaryaveer/fast-api-cookbook-for-llms-and-embedding-model-1862f0ec58e4) |
| RAG + ChromaDB | [Building a RAG Pipeline with Hugging Face, ChromaDB, and Railway](https://medium.com/@dammak.bader/building-a-rag-pipeline-with-hugging-face-chromadb-and-railway-ad8dcfc25a18) |


"""
LangGraph Agent Configuration
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    # Try to load .env from project root
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()  # Try to load from current directory
except ImportError:
    print("[Warning] python-dotenv not installed. Using default values or system environment variables.")


def _get_env_bool(key: str, default: bool) -> bool:
    """Get boolean value from environment variable"""
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def _get_env_float(key: str, default: float) -> float:
    """Get float value from environment variable"""
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def _get_env_int(key: str, default: int) -> int:
    """Get integer value from environment variable"""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


@dataclass
class AgentConfig:
    # Ollama LLM
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    ollama_temperature: float = _get_env_float("OLLAMA_TEMPERATURE", 0.1)

    # PostgreSQL
    pg_dsn: str = os.getenv("PG_DSN", "postgresql://postgres:root@localhost:5432/ragdb")

    # Elasticsearch
    es_url: str = os.getenv("ES_URL", "http://localhost:9200")
    es_user: Optional[str] = os.getenv("ES_USER", "elastic")
    es_password: Optional[str] = os.getenv("ES_PASSWORD")

    # Qdrant
    qdrant_path: str = os.getenv("QDRANT_PATH", "./qdrant_storage")
    qdrant_collection_findings: str = os.getenv("QDRANT_COLLECTION_FINDINGS", "findings_vectors")
    qdrant_collection_chunks: str = os.getenv("QDRANT_COLLECTION_CHUNKS", "chunks_vectors")

    # Retrieval parameters
    findings_top_k_es: int = _get_env_int("FINDINGS_TOP_K_ES", 150)
    findings_top_k_vec: int = _get_env_int("FINDINGS_TOP_K_VEC", 150)
    findings_rrf_k: int = _get_env_int("FINDINGS_RRF_K", 60)
    findings_final_top_n: int = _get_env_int("FINDINGS_FINAL_TOP_N", 30)

    chunks_top_k_es: int = _get_env_int("CHUNKS_TOP_K_ES", 300)
    chunks_top_k_vec: int = _get_env_int("CHUNKS_TOP_K_VEC", 300)
    chunks_mmr_lambda: float = _get_env_float("CHUNKS_MMR_LAMBDA", 0.65)

    qdrant_ef_search: int = _get_env_int("QDRANT_EF_SEARCH", 96)
    qdrant_score_threshold: float = _get_env_float("QDRANT_SCORE_THRESHOLD", 0.35)

    # Scoring weights
    alpha_bm25: float = _get_env_float("ALPHA_BM25", 0.5)
    beta_vector: float = _get_env_float("BETA_VECTOR", 0.4)
    gamma_field: float = _get_env_float("GAMMA_FIELD", 0.1)

    # Block ranking
    block_top_k_chunks: int = _get_env_int("BLOCK_TOP_K_CHUNKS", 3)
    block_intersection_min: int = _get_env_int("BLOCK_INTERSECTION_MIN", 2)
    block_final_top_n: int = _get_env_int("BLOCK_FINAL_TOP_N", 3)
    max_blocks_per_doc: int = _get_env_int("MAX_BLOCKS_PER_DOC", 2)

    # Section blending (default: 5:5)
    weight_section_착안: float = _get_env_float("WEIGHT_SECTION_CHAKAN", 0.5)
    weight_section_기법: float = _get_env_float("WEIGHT_SECTION_GIHUB", 0.5)

    # Context packing
    context_token_budget: int = _get_env_int("CONTEXT_TOKEN_BUDGET", 4000)
    context_chunks_per_block: int = _get_env_int("CONTEXT_CHUNKS_PER_BLOCK", 3)
    context_merge_adjacent: bool = _get_env_bool("CONTEXT_MERGE_ADJACENT", True)

    # Timeout
    response_timeout: float = _get_env_float("RESPONSE_TIMEOUT", 2.5)


config = AgentConfig()

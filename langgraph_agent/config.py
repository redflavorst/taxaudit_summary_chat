"""
LangGraph Agent Configuration
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentConfig:
    # Ollama LLM
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_temperature: float = 0.1
    
    # PostgreSQL
    pg_dsn: str = "postgresql://postgres:root@localhost:5432/ragdb"
    
    # Elasticsearch
    es_url: str = "http://localhost:9200"
    es_user: Optional[str] = "elastic"
    es_password: Optional[str] = "_Qei5gzpBQYNBAtg6Q8R"
    
    # Qdrant
    qdrant_path: str = "./qdrant_storage"
    qdrant_collection_findings: str = "findings_vectors"
    qdrant_collection_chunks: str = "chunks_vectors"
    
    # Retrieval parameters
    findings_top_k_es: int = 150
    findings_top_k_vec: int = 150
    findings_rrf_k: int = 60
    findings_final_top_n: int = 30
    
    chunks_top_k_es: int = 300
    chunks_top_k_vec: int = 300
    chunks_mmr_lambda: float = 0.65
    
    qdrant_ef_search: int = 96
    qdrant_score_threshold: float = 0.35
    
    # Scoring weights
    alpha_bm25: float = 0.5
    beta_vector: float = 0.4
    gamma_field: float = 0.1
    
    # Block ranking
    block_top_k_chunks: int = 3
    block_intersection_min: int = 2
    block_final_top_n: int = 3
    max_blocks_per_doc: int = 2
    
    # Section blending (default: 5:5)
    weight_section_착안: float = 0.5
    weight_section_기법: float = 0.5
    
    # Context packing
    context_token_budget: int = 4000
    context_chunks_per_block: int = 3
    context_merge_adjacent: bool = True
    
    # Timeout
    response_timeout: float = 2.5


config = AgentConfig()

from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class Settings:
    # PostgreSQL connection info
    PG_DSN: str = os.getenv("PG_DSN", "postgresql://postgres:root@localhost:5432/ragdb")

    # Elasticsearch connection info
    ES_URL: str = os.getenv("ES_URL", "http://localhost:9200")
    ES_USER: Optional[str] = os.getenv("ES_USER", "elastic")
    ES_PASSWORD: Optional[str] = os.getenv("ES_PASSWORD", "_Qei5gzpBQYNBAtg6Q8R")
    ES_API_KEY_ID: Optional[str] = os.getenv("ES_API_KEY_ID")
    ES_API_KEY_SECRET: Optional[str] = os.getenv("ES_API_KEY_SECRET")
    ES_VERIFY_CERTS: bool = os.getenv("ES_VERIFY_CERTS", "true").lower() == "true"
    ES_CA_CERTS: Optional[str] = os.getenv("ES_CA_CERTS")

    QDRANT_URL: str = os.getenv("QDRANT_URL", "path:./qdrant_storage")
    QDRANT_API_KEY: Optional[str] = os.getenv("QDRANT_API_KEY")
    USE_QDRANT: bool = os.getenv("USE_QDRANT", "true").lower() == "true"
    
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-m3")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))
    NORMALIZE_L2: bool = os.getenv("NORMALIZE_L2", "true").lower() == "true"
    UPSERT_BATCH: int = int(os.getenv("UPSERT_BATCH", "256"))
    EXTRACTION_VERSION: str = os.getenv("EXTRACTION_VERSION", "v0.5.0")


# .env 파일 로드
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

settings = Settings()

from dataclasses import dataclass
from typing import Optional


@dataclass
class Settings:
    # PostgreSQL connection info
    PG_DSN: str = "postgresql://postgres:root@localhost:5432/ragdb"

    # Elasticsearch connection info
    ES_URL: str = "http://localhost:9200"
    ES_USER: Optional[str] = "elastic"
    ES_PASSWORD: Optional[str] = "_Qei5gzpBQYNBAtg6Q8R"
    ES_API_KEY_ID: Optional[str] = None
    ES_API_KEY_SECRET: Optional[str] = None
    ES_VERIFY_CERTS: bool = True
    ES_CA_CERTS: Optional[str] = None

    QDRANT_URL: str = "path:./qdrant_storage"
    QDRANT_API_KEY: Optional[str] = None
    USE_QDRANT: bool = True
    
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-m3"
    EMBEDDING_DIM: int = 1024
    NORMALIZE_L2: bool = True
    UPSERT_BATCH: int = 256
    EXTRACTION_VERSION: str = "v0.5.0"


settings = Settings()

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    VectorParams, 
    Distance, 
    OptimizersConfigDiff,
    CollectionInfo
)
from typing import Optional, List
from config import settings

COLLECTION_FINDINGS = "findings_vectors"
COLLECTION_CHUNKS = "chunks_vectors"
COLLECTION_LAWS = "law_references_vectors"

def get_qdrant_client() -> QdrantClient:
    if settings.QDRANT_URL == ":memory:":
        print("Using in-memory Qdrant (no server needed)")
        return QdrantClient(":memory:")
    
    if settings.QDRANT_URL.startswith("path:"):
        path = settings.QDRANT_URL.replace("path:", "")
        print(f"Using local Qdrant storage: {path}")
        return QdrantClient(path=path)
    
    kwargs = {"url": settings.QDRANT_URL}
    if settings.QDRANT_API_KEY:
        kwargs["api_key"] = settings.QDRANT_API_KEY
    
    return QdrantClient(**kwargs)

def ensure_collection(client: QdrantClient, collection_name: str, vector_size: int = None):
    vector_size = vector_size or settings.EMBEDDING_DIM
    
    try:
        existing = client.get_collection(collection_name)
        print(f"OK: collection exists: {collection_name}")
        return
    except Exception:
        pass
    
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=vector_size,
            distance=Distance.COSINE
        )
    )
    
    client.update_collection(
        collection_name=collection_name,
        optimizer_config=OptimizersConfigDiff(
            indexing_threshold=20000
        )
    )
    
    print(f"OK: collection created: {collection_name}")

def setup_collections():
    client = get_qdrant_client()
    
    ensure_collection(client, COLLECTION_FINDINGS)
    ensure_collection(client, COLLECTION_CHUNKS)
    ensure_collection(client, COLLECTION_LAWS)
    
    return client

if __name__ == "__main__":
    setup_collections()
    print("OK: Qdrant collections ready")

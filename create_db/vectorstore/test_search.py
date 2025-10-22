import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from vectorstore.qdrant_client import get_qdrant_client, COLLECTION_CHUNKS
from vectorstore.embedder import Embedder

def test_search(query: str, limit: int = 5):
    qc = get_qdrant_client()
    emb = Embedder()
    
    print(f"\nQuery: {query}")
    print("-" * 60)
    
    query_vector = emb.encode([query])[0]
    
    results = qc.search(
        collection_name=COLLECTION_CHUNKS,
        query_vector=query_vector.tolist(),
        limit=limit,
        with_payload=True
    )
    
    for i, result in enumerate(results, 1):
        print(f"\n[{i}] Score: {result.score:.4f}")
        print(f"Chunk ID: {result.payload['chunk_id']}")
        print(f"Section: {result.payload['section']}")
        print(f"Code: {result.payload.get('code', 'N/A')}")
        print(f"Item: {result.payload.get('item_norm', 'N/A')}")

if __name__ == "__main__":
    test_search("작업진행률 조정", limit=3)
    test_search("보증수수료 손금", limit=3)

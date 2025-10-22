"""
모든 데이터 삭제 스크립트
- Elasticsearch 인덱스 삭제 (findings, chunks, law_references)
- Qdrant 컬렉션 삭제 (findings_vectors, chunks_vectors, law_references_vectors)
- PostgreSQL은 수동으로 삭제 (DROP DATABASE ragdb)
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

from elasticsearch import Elasticsearch
from config import settings
from vectorstore.qdrant_client import get_qdrant_client, COLLECTION_FINDINGS, COLLECTION_CHUNKS, COLLECTION_LAWS


def clear_elasticsearch():
    """Elasticsearch 인덱스 삭제"""
    print("\n" + "="*70)
    print("Clearing Elasticsearch indices...")
    print("="*70)
    
    try:
        es_kwargs = {}
        if settings.ES_USER and settings.ES_PASSWORD:
            es_kwargs["basic_auth"] = (settings.ES_USER, settings.ES_PASSWORD)
        if settings.ES_VERIFY_CERTS is not None:
            es_kwargs["verify_certs"] = settings.ES_VERIFY_CERTS
        if settings.ES_CA_CERTS:
            es_kwargs["ca_certs"] = settings.ES_CA_CERTS
        
        es = Elasticsearch(settings.ES_URL, **es_kwargs)
        
        # 삭제할 인덱스 목록
        indices_to_delete = ["findings", "chunks", "law_references"]
        
        for index_name in indices_to_delete:
            if es.indices.exists(index=index_name):
                es.indices.delete(index=index_name)
                print(f"  ✓ Deleted index: {index_name}")
            else:
                print(f"  - Index not found: {index_name}")
        
        print("\nElasticsearch indices cleared successfully!")
        
    except Exception as e:
        print(f"  ✗ Elasticsearch error: {type(e).__name__}: {e}")
        print("  (ES may not be running or accessible)")


def clear_qdrant():
    """Qdrant 컬렉션 삭제"""
    print("\n" + "="*70)
    print("Clearing Qdrant collections...")
    print("="*70)
    
    try:
        qc = get_qdrant_client()
        
        # 삭제할 컬렉션 목록
        collections_to_delete = [COLLECTION_FINDINGS, COLLECTION_CHUNKS, COLLECTION_LAWS]
        
        for collection_name in collections_to_delete:
            try:
                qc.delete_collection(collection_name)
                print(f"  ✓ Deleted collection: {collection_name}")
            except Exception as e:
                print(f"  - Collection not found or already deleted: {collection_name}")
        
        print("\nQdrant collections cleared successfully!")
        
    except Exception as e:
        print(f"  ✗ Qdrant error: {type(e).__name__}: {e}")


def clear_qdrant_storage_files():
    """Qdrant 로컬 스토리지 파일 삭제"""
    import shutil
    from pathlib import Path
    
    print("\n" + "="*70)
    print("Clearing Qdrant storage files...")
    print("="*70)
    
    # qdrant_storage 폴더 확인
    storage_paths = [
        Path(__file__).parent / "qdrant_storage",
        Path(__file__).parent.parent / "qdrant_storage"
    ]
    
    for storage_path in storage_paths:
        if storage_path.exists():
            try:
                shutil.rmtree(storage_path)
                print(f"  ✓ Deleted: {storage_path}")
                
                # 빈 폴더 재생성
                storage_path.mkdir(parents=True, exist_ok=True)
                print(f"  ✓ Recreated empty: {storage_path}")
            except Exception as e:
                print(f"  ✗ Error deleting {storage_path}: {e}")
        else:
            print(f"  - Not found: {storage_path}")


def main():
    print("\n" + "="*70)
    print("CLEAR ALL DATA (Elasticsearch + Qdrant)")
    print("="*70)
    print("\nThis will delete:")
    print("  - Elasticsearch indices: findings, chunks, law_references")
    print("  - Qdrant collections: findings_vectors, chunks_vectors, law_references_vectors")
    print("  - Qdrant storage files (if using local storage)")
    print("\nPostgreSQL database is NOT deleted. Run manually if needed:")
    print("  psql -U postgres -c 'DROP DATABASE IF EXISTS ragdb;'")
    
    confirm = input("\nContinue? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("\nCancelled.")
        return
    
    # 1. Elasticsearch 삭제
    clear_elasticsearch()
    
    # 2. Qdrant 삭제
    clear_qdrant()
    
    # 3. Qdrant 스토리지 파일 삭제 (로컬 모드인 경우)
    if settings.QDRANT_URL.startswith("path:"):
        clear_qdrant_storage_files()
    
    print("\n" + "="*70)
    print("ALL DATA CLEARED!")
    print("="*70)
    print("\nNext steps:")
    print("  1. (Optional) Drop PostgreSQL: psql -U postgres -c 'DROP DATABASE IF EXISTS ragdb;'")
    print("  2. Recreate database: python create_database.py")
    print("  3. Run pipeline: python ../pipeline_full.py")


if __name__ == "__main__":
    main()

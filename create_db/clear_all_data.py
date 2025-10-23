"""
전체 데이터 삭제 스크립트
- PostgreSQL: 모든 테이블 데이터 삭제 (TRUNCATE)
- Elasticsearch: 모든 인덱스 삭제
- Qdrant: 모든 컬렉션 및 로컬 스토리지 삭제
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

import psycopg2
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


def clear_postgresql():
    """PostgreSQL 모든 테이블 데이터 삭제 (TRUNCATE)"""
    print("\n" + "="*70)
    print("Clearing PostgreSQL tables...")
    print("="*70)
    
    try:
        conn = psycopg2.connect(settings.PG_DSN)
        conn.set_client_encoding('UTF8')
        cur = conn.cursor()
        
        tables = ["law_references", "chunks", "row_finding_map", "findings", "table_rows", "documents"]
        
        for table in tables:
            try:
                cur.execute(f"TRUNCATE TABLE {table} CASCADE")
                print(f"  ✓ Cleared table: {table}")
            except Exception as e:
                print(f"  - Table not found or error: {table} ({e})")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print("\nPostgreSQL tables cleared successfully!")
        
    except Exception as e:
        print(f"  ✗ PostgreSQL error: {type(e).__name__}: {e}")
        print("  (Database may not exist or not accessible)")


def main():
    print("\n" + "="*70)
    print("전체 데이터 삭제 (PostgreSQL + Elasticsearch + Qdrant)")
    print("="*70)
    print("\n삭제될 데이터:")
    print("  - PostgreSQL: documents, findings, chunks, law_references 등 모든 테이블")
    print("  - Elasticsearch: findings, chunks, law_references 인덱스")
    print("  - Qdrant: findings_vectors, chunks_vectors, law_references_vectors 컬렉션")
    print("  - Qdrant 로컬 스토리지 파일 (사용 중인 경우)")
    
    confirm = input("\n계속하시겠습니까? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("\n취소되었습니다.")
        return
    
    # 1. PostgreSQL 삭제
    clear_postgresql()
    
    # 2. Elasticsearch 삭제
    clear_elasticsearch()
    
    # 3. Qdrant 삭제
    clear_qdrant()
    
    # 4. Qdrant 스토리지 파일 삭제 (로컬 모드인 경우)
    if hasattr(settings, 'QDRANT_PATH'):
        clear_qdrant_storage_files()
    
    print("\n" + "="*70)
    print("✅ 모든 데이터가 삭제되었습니다!")
    print("="*70)
    print("\n다음 단계:")
    print("  1. 데이터 재인제스트: python run_ingest.py")


if __name__ == "__main__":
    main()

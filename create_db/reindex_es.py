"""
PostgreSQL에서 데이터를 읽어 Elasticsearch에 재인덱싱
"""
import sys
import psycopg2
from elasticsearch import Elasticsearch
from config import settings
from es_indexer import index_findings, index_chunks

def main():
    # PostgreSQL 연결
    print("📦 PostgreSQL에서 데이터 로딩 중...")
    conn = psycopg2.connect(settings.PG_DSN)
    cur = conn.cursor()
    
    # findings 로딩
    cur.execute("SELECT * FROM findings ORDER BY doc_id, finding_order")
    findings_rows = cur.fetchall()
    findings_cols = [desc[0] for desc in cur.description]
    findings = [dict(zip(findings_cols, row)) for row in findings_rows]
    print(f"  ✓ findings: {len(findings)}개")
    
    # chunks 로딩
    cur.execute("SELECT * FROM chunks ORDER BY doc_id, finding_id, section_order, chunk_order")
    chunks_rows = cur.fetchall()
    chunks_cols = [desc[0] for desc in cur.description]
    chunks = [dict(zip(chunks_cols, row)) for row in chunks_rows]
    print(f"  ✓ chunks: {len(chunks)}개")
    
    # doc_metadata 로딩
    cur.execute("SELECT * FROM doc_metadata")
    meta_rows = cur.fetchall()
    meta_cols = [desc[0] for desc in cur.description]
    doc_meta_by_docid = {row[0]: dict(zip(meta_cols, row)) for row in meta_rows}
    print(f"  ✓ doc_metadata: {len(doc_meta_by_docid)}개")
    
    cur.close()
    conn.close()
    
    # Elasticsearch 연결
    print("\n🔍 Elasticsearch 인덱싱 중...")
    es_kwargs = {"hosts": [settings.ES_URL]}
    if settings.ES_USER and settings.ES_PASSWORD:
        es_kwargs["basic_auth"] = (settings.ES_USER, settings.ES_PASSWORD)
    
    es = Elasticsearch(**es_kwargs)
    
    # 인덱싱
    index_findings(es, "findings", findings, doc_meta_by_docid)
    index_chunks(es, "chunks", chunks, doc_meta_by_docid)
    
    # 확인
    findings_count = es.count(index="findings")["count"]
    chunks_count = es.count(index="chunks")["count"]
    
    print(f"\n✅ 인덱싱 완료!")
    print(f"  - findings: {findings_count}개")
    print(f"  - chunks: {chunks_count}개")

if __name__ == "__main__":
    main()

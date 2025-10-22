from elasticsearch import Elasticsearch, helpers
from datetime import datetime
from typing import List, Dict


def index_findings(es: Elasticsearch, index: str, findings, doc_meta_by_docid, row_finding_maps=None):
    """
    findings를 ES에 인덱싱
    
    Args:
        es: Elasticsearch 클라이언트
        index: 인덱스 이름
        findings: finding 딕셔너리 리스트
        doc_meta_by_docid: 문서 메타데이터 딕셔너리
        row_finding_maps: row-finding 매핑 리스트 (optional)
    """
    actions = []
    
    # row_finding_maps에서 finding별 연결 정보 추출
    finding_to_rows = {}
    finding_to_codes_from_rows = {}
    if row_finding_maps:
        for m in row_finding_maps:
            fid = m["finding_id"]
            rid = m["row_id"]
            if fid not in finding_to_rows:
                finding_to_rows[fid] = []
            finding_to_rows[fid].append(rid)
    
    for idx, f in enumerate(findings, 1):
        meta = doc_meta_by_docid.get(f["doc_id"], {})
        overview_keywords = meta.get("overview_keywords_norm") or []
        
        # row_ids 가져오기
        row_ids = finding_to_rows.get(f["finding_id"], f.get("row_ids", []))
        
        # codes_from_rows 추출 (연결된 row들의 코드)
        codes_from_rows = list(set(
            code for code in [f.get("code")] if code
        ))
        
        # item_detail에서 개행 처리 (ES는 일반 JSON 문자열만 허용)
        item_detail = f.get("item_detail") or ""
        if item_detail:
            # 이미 개행이 있다면 그대로, 없다면 변환 불필요
            item_detail = item_detail.strip()
        
        # reason_kw_norm이 문자열이면 배열로 변환
        reason_kw_norm = f.get("reason_kw_norm", [])
        if isinstance(reason_kw_norm, str):
            reason_kw_norm = [kw.strip() for kw in reason_kw_norm.split(",") if kw.strip()]
        
        src = {
            "finding_id": f["finding_id"],
            "doc_id": f["doc_id"],
            "doc_title": meta.get("doc_title") or f["doc_id"],
            "finding_order": idx,
            
            # 지적사항 내용
            "item": f.get("item"),
            "item_norm": f.get("item_norm"),
            "item_detail": item_detail,
            
            # 코드
            "code": f.get("code"),
            "codes_from_rows": codes_from_rows,
            "code_mismatch": f.get("code_mismatch", False),
            
            # 키워드
            "reason_kw_norm": reason_kw_norm,
            "overview_keywords": " ".join(overview_keywords) if overview_keywords else "",
            
            # 분류
            "industry_sub": meta.get("industry_sub"),
            "domain_tags": meta.get("domain_tags", []),
            "actions": meta.get("actions", []),
            "entities": meta.get("entities", []),
            
            # 섹션
            "sections_present": f.get("sections_present", []),
            "section_spans": f.get("section_spans", []),
            
            # 범위
            "start_line": f.get("start_line"),
            "end_line": f.get("end_line"),
            "start_page": f.get("start_page"),
            "end_page": f.get("end_page"),
            
            # 연결
            "row_ids": row_ids,
            "chunk_count": f.get("chunk_count", 0),
            
            # 메타
            "created_at": datetime.utcnow().isoformat() + "Z",
            "extraction_version": "v0.4.0"
        }
        actions.append({"_index": index, "_id": f["finding_id"], "_source": src})
    
    if actions:
        helpers.bulk(es, actions)
        print(f"OK: {len(actions)} findings indexed")


def index_chunks(es: Elasticsearch, index: str, chunks):
    """
    chunks를 ES에 인덱싱
    
    Args:
        es: Elasticsearch 클라이언트
        index: 인덱스 이름
        chunks: chunk 딕셔너리 리스트
    """
    actions = []
    for c in chunks:
        start_line = c.get("start_line")
        end_line = c.get("end_line")
        line_range = None
        if isinstance(start_line, int) and isinstance(end_line, int):
            line_range = {"gte": start_line, "lte": end_line}
        
        text = c.get("text") or ""
        text_norm = c.get("text_norm") or text
        text_raw = c.get("text_raw") or text

        src = {
            "chunk_id": c["chunk_id"],
            "finding_id": c["finding_id"],
            "doc_id": c["doc_id"],
            "section": c.get("section"),
            "section_order": c.get("section_order"),
            "chunk_order": c.get("chunk_order"),
            "code": c.get("code"),
            "item": c.get("item"),
            "item_norm": c.get("item_norm"),
            "page": c.get("page"),
            "start_line": start_line,
            "end_line": end_line,
            "line_range": line_range,
            "text": text.strip() if text else "",
            "text_norm": text_norm.strip() if text_norm else "",
            "text_raw": text_raw.strip() if text_raw else "",
            "meta_line": c.get("meta_line"),
            "extraction_version": c.get("extraction_version", "v0.4.0"),
            "created_at": c.get("created_at"),
        }
        actions.append({"_index": index, "_id": c["chunk_id"], "_source": src})
    
    if actions:
        helpers.bulk(es, actions)
        print(f"OK: {len(actions)} chunks indexed")


def index_laws(es: Elasticsearch, index: str, law_refs: List[Dict]):
    """
    law_references를 ES에 인덱싱
    
    Args:
        es: Elasticsearch 클라이언트
        index: 인덱스 이름 (law_references)
        law_refs: law_reference 딕셔너리 리스트
    """
    from es_mappings import LAW_REFERENCES_MAPPING, create_index_if_not_exists
    
    # 인덱스 생성 (없으면)
    create_index_if_not_exists(es, index, LAW_REFERENCES_MAPPING)
    
    actions = []
    for law in law_refs:
        src = {
            "law_id": law["law_id"],
            "finding_id": law.get("finding_id"),
            "doc_id": law["doc_id"],
            "law_type": law.get("law_type"),
            "law_name": law.get("law_name"),
            "law_content": law.get("law_content"),
            "page": law.get("page"),
            "line_number": law.get("line_number"),
            "law_order": law.get("law_order"),
            "extraction_version": law.get("extraction_version", "v0.5.0"),
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        actions.append({"_index": index, "_id": law["law_id"], "_source": src})
    
    if actions:
        helpers.bulk(es, actions)
        print(f"OK: {len(actions)} law_references indexed")


def main():
    """PostgreSQL에서 데이터를 읽어 Elasticsearch에 재인덱싱"""
    import psycopg2
    from config import settings
    
    # PostgreSQL 연결
    print("📦 PostgreSQL에서 데이터 로딩 중...")
    conn = psycopg2.connect(settings.PG_DSN)
    conn.set_client_encoding('UTF8')
    cur = conn.cursor()
    
    # findings 로딩
    cur.execute("SELECT * FROM findings ORDER BY doc_id, finding_id")
    findings_rows = cur.fetchall()
    findings_cols = [desc[0] for desc in cur.description]
    findings = [dict(zip(findings_cols, row)) for row in findings_rows]
    print(f"  ✓ findings: {len(findings)}개")
    
    # chunks 로딩
    cur.execute("SELECT * FROM chunks ORDER BY doc_id, finding_id, chunk_id")
    chunks_rows = cur.fetchall()
    chunks_cols = [desc[0] for desc in cur.description]
    chunks = [dict(zip(chunks_cols, row)) for row in chunks_rows]
    print(f"  ✓ chunks: {len(chunks)}개")
    
    # documents 로딩
    cur.execute("SELECT * FROM documents")
    meta_rows = cur.fetchall()
    meta_cols = [desc[0] for desc in cur.description]
    doc_meta_by_docid = {row[0]: dict(zip(meta_cols, row)) for row in meta_rows}
    print(f"  ✓ documents: {len(doc_meta_by_docid)}개")
    
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
    index_chunks(es, "chunks", chunks)
    
    # 확인
    findings_count = es.count(index="findings")["count"]
    chunks_count = es.count(index="chunks")["count"]
    
    print(f"\n✅ 인덱싱 완료!")
    print(f"  - findings: {findings_count}개")
    print(f"  - chunks: {chunks_count}개")


if __name__ == "__main__":
    main()

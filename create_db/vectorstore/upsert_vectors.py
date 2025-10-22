import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from elasticsearch import Elasticsearch
from qdrant_client.http.models import PointStruct
from typing import Dict, List
from tqdm import tqdm
from config import settings
from vectorstore.embedder import Embedder
from vectorstore.qdrant_client import (
    get_qdrant_client, 
    setup_collections, 
    COLLECTION_FINDINGS, 
    COLLECTION_CHUNKS,
    COLLECTION_LAWS
)
from vectorstore.utils import text_hash, clean_none, string_to_uuid

def get_es_client() -> Elasticsearch:
    es_kwargs = {}
    if settings.ES_USER and settings.ES_PASSWORD:
        es_kwargs["basic_auth"] = (settings.ES_USER, settings.ES_PASSWORD)
    if settings.ES_VERIFY_CERTS is not None:
        es_kwargs["verify_certs"] = settings.ES_VERIFY_CERTS
    if settings.ES_CA_CERTS:
        es_kwargs["ca_certs"] = settings.ES_CA_CERTS
    
    return Elasticsearch(settings.ES_URL, **es_kwargs)

def scan_es_index(es: Elasticsearch, index_name: str, batch_size: int = 500):
    body = {
        "query": {"match_all": {}},
        "_source": True,
        "size": batch_size
    }
    
    resp = es.search(index=index_name, body=body, scroll="5m")
    scroll_id = resp.get("_scroll_id")
    
    hits = resp["hits"]["hits"]
    for hit in hits:
        yield hit["_source"]
    
    while True:
        resp = es.scroll(scroll_id=scroll_id, scroll="5m")
        hits = resp["hits"]["hits"]
        if not hits:
            break
        for hit in hits:
            yield hit["_source"]

def finding_text_for_embedding(src: Dict) -> str:
    parts = []
    
    if src.get("item_detail"):
        parts.append(str(src["item_detail"]))
    
    rk = src.get("reason_kw_norm") or []
    if rk and len(rk) > 0:
        parts.append("핵심키워드: " + ", ".join(rk[:6]))
    
    return "\n".join(parts).strip()

def chunk_text_for_embedding(src: Dict) -> str:
    return (src.get("text_norm") or src.get("text") or "").strip()

def law_text_for_embedding(src: Dict) -> str:
    """법령 임베딩용 텍스트 생성"""
    parts = []
    
    law_type = src.get("law_type")
    if law_type:
        parts.append(f"법령유형: {law_type}")
    
    law_name = src.get("law_name")
    if law_name:
        parts.append(f"법령명: {law_name}")
    
    law_content = src.get("law_content")
    if law_content:
        parts.append(f"내용: {law_content}")
    
    return "\n".join(parts).strip()

def build_finding_point(src: Dict, vector, version: str) -> PointStruct:
    fid = src["finding_id"]
    uuid_id = string_to_uuid(fid)
    
    payload = clean_none({
        "finding_id": fid,
        "doc_id": src.get("doc_id"),
        "code": src.get("code"),
        "item": src.get("item"),
        "item_norm": src.get("item_norm"),
        "industry_sub": src.get("industry_sub"),
        "domain_tags": src.get("domain_tags"),
        "actions": src.get("actions"),
        "chunk_count": src.get("chunk_count"),
        "extraction_version": version,
        "text_hash": text_hash(finding_text_for_embedding(src))
    })
    
    return PointStruct(id=uuid_id, vector=vector.tolist(), payload=payload)

def build_chunk_point(src: Dict, vector, version: str) -> PointStruct:
    cid = src["chunk_id"]
    uuid_id = string_to_uuid(cid)
    
    payload = clean_none({
        "chunk_id": cid,
        "finding_id": src.get("finding_id"),
        "doc_id": src.get("doc_id"),
        "section": src.get("section"),
        "section_order": src.get("section_order"),
        "chunk_order": src.get("chunk_order"),
        "code": src.get("code"),
        "item": src.get("item"),
        "item_norm": src.get("item_norm"),
        "page": src.get("page"),
        "extraction_version": version,
        "text_hash": text_hash(chunk_text_for_embedding(src))
    })
    
    return PointStruct(id=uuid_id, vector=vector.tolist(), payload=payload)

def build_law_point(src: Dict, vector, version: str) -> PointStruct:
    """법령 벡터 포인트 생성"""
    law_id = src["law_id"]
    uuid_id = string_to_uuid(law_id)
    
    payload = clean_none({
        "law_id": law_id,
        "finding_id": src.get("finding_id"),
        "doc_id": src.get("doc_id"),
        "law_type": src.get("law_type"),
        "law_name": src.get("law_name"),
        "page": src.get("page"),
        "law_order": src.get("law_order"),
        "extraction_version": version,
        "text_hash": text_hash(law_text_for_embedding(src))
    })
    
    return PointStruct(id=uuid_id, vector=vector.tolist(), payload=payload)

def upsert_findings(es: Elasticsearch, qc, emb: Embedder, batch_size: int = None):
    batch_size = batch_size or settings.UPSERT_BATCH
    
    batch_texts, batch_srcs = [], []
    total = 0
    
    print(f"Upserting findings to {COLLECTION_FINDINGS}...")
    
    for src in tqdm(scan_es_index(es, "findings"), desc="findings"):
        txt = finding_text_for_embedding(src)
        if not txt:
            continue
        
        batch_texts.append(txt)
        batch_srcs.append(src)
        
        if len(batch_texts) >= batch_size:
            vectors = emb.encode(batch_texts, show_progress=False)
            points = [
                build_finding_point(s, vectors[i], settings.EXTRACTION_VERSION)
                for i, s in enumerate(batch_srcs)
            ]
            qc.upsert(collection_name=COLLECTION_FINDINGS, points=points)
            total += len(points)
            batch_texts, batch_srcs = [], []
    
    if batch_texts:
        vectors = emb.encode(batch_texts, show_progress=False)
        points = [
            build_finding_point(s, vectors[i], settings.EXTRACTION_VERSION)
            for i, s in enumerate(batch_srcs)
        ]
        qc.upsert(collection_name=COLLECTION_FINDINGS, points=points)
        total += len(points)
    
    print(f"OK: {total} findings upserted")

def upsert_chunks(es: Elasticsearch, qc, emb: Embedder, batch_size: int = None):
    batch_size = batch_size or settings.UPSERT_BATCH
    
    batch_texts, batch_srcs = [], []
    total = 0
    
    print(f"Upserting chunks to {COLLECTION_CHUNKS}...")
    
    for src in tqdm(scan_es_index(es, "chunks"), desc="chunks"):
        txt = chunk_text_for_embedding(src)
        if not txt:
            continue
        
        batch_texts.append(txt)
        batch_srcs.append(src)
        
        if len(batch_texts) >= batch_size:
            vectors = emb.encode(batch_texts, show_progress=False)
            points = [
                build_chunk_point(s, vectors[i], settings.EXTRACTION_VERSION)
                for i, s in enumerate(batch_srcs)
            ]
            qc.upsert(collection_name=COLLECTION_CHUNKS, points=points)
            total += len(points)
            batch_texts, batch_srcs = [], []
    
    if batch_texts:
        vectors = emb.encode(batch_texts, show_progress=False)
        points = [
            build_chunk_point(s, vectors[i], settings.EXTRACTION_VERSION)
            for i, s in enumerate(batch_srcs)
        ]
        qc.upsert(collection_name=COLLECTION_CHUNKS, points=points)
        total += len(points)
    
    print(f"OK: {total} chunks upserted")

def upsert_laws(es: Elasticsearch, qc, emb: Embedder, batch_size: int = None):
    """법령을 Qdrant에 업서트"""
    batch_size = batch_size or settings.UPSERT_BATCH
    
    batch_texts, batch_srcs = [], []
    total = 0
    
    print(f"Upserting laws to {COLLECTION_LAWS}...")
    
    for src in tqdm(scan_es_index(es, "law_references"), desc="law_references"):
        txt = law_text_for_embedding(src)
        if not txt:
            continue
        
        batch_texts.append(txt)
        batch_srcs.append(src)
        
        if len(batch_texts) >= batch_size:
            vectors = emb.encode(batch_texts, show_progress=False)
            points = [
                build_law_point(s, vectors[i], settings.EXTRACTION_VERSION)
                for i, s in enumerate(batch_srcs)
            ]
            qc.upsert(collection_name=COLLECTION_LAWS, points=points)
            total += len(points)
            batch_texts, batch_srcs = [], []
    
    if batch_texts:
        vectors = emb.encode(batch_texts, show_progress=False)
        points = [
            build_law_point(s, vectors[i], settings.EXTRACTION_VERSION)
            for i, s in enumerate(batch_srcs)
        ]
        qc.upsert(collection_name=COLLECTION_LAWS, points=points)
        total += len(points)
    
    print(f"OK: {total} laws upserted")

def run_all():
    print("Setting up Qdrant collections...")
    qc = setup_collections()
    
    print("Connecting to Elasticsearch...")
    es = get_es_client()
    
    print("Loading embedding model...")
    emb = Embedder()
    
    upsert_findings(es, qc, emb)
    upsert_chunks(es, qc, emb)
    upsert_laws(es, qc, emb)
    
    print("OK: Vectorstore upsert completed")

if __name__ == "__main__":
    run_all()

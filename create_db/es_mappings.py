"""
Elasticsearch 인덱스 매핑 정의
- findings 인덱스: 지적사항 메타데이터
- chunks 인덱스: 지적사항 청크 (벡터 검색용)
"""

FINDINGS_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "korean_analyzer": {
                    "type": "custom",
                    "tokenizer": "nori_tokenizer",
                    "filter": ["lowercase", "nori_readingform"]
                }
            },
            "normalizer": {
                "lowercase_normalizer": {
                    "type": "custom",
                    "filter": ["lowercase"]
                }
            }
        }
    },
    "mappings": {
        "properties": {
            # 식별자
            "finding_id": {"type": "keyword"},
            "doc_id": {"type": "keyword"},
            "doc_title": {"type": "keyword"},
            "finding_order": {"type": "integer"},
            
            # 지적사항 내용 (한국어 분석)
            "item": {
                "type": "text",
                "analyzer": "korean_analyzer",
                "fields": {
                    "keyword": {"type": "keyword"}
                }
            },
            "item_norm": {
                "type": "text",
                "analyzer": "korean_analyzer",
                "fields": {
                    "keyword": {"type": "keyword"}
                }
            },
            "item_detail": {
                "type": "text",
                "analyzer": "korean_analyzer"
            },
            
            # 코드
            "code": {"type": "keyword"},
            "codes_from_rows": {"type": "keyword"},
            "code_mismatch": {"type": "boolean"},
            
            # 키워드 & 정규화 필드 (한국어 분석)
            "reason_kw_norm": {
                "type": "text",
                "analyzer": "korean_analyzer"
            },
            "overview_keywords": {
                "type": "text",
                "analyzer": "korean_analyzer"
            },
            
            # 조사대상개요 (인적사항)
            "entity_type": {"type": "keyword"},
            "industry_name": {
                "type": "text",
                "analyzer": "korean_analyzer",
                "fields": {"keyword": {"type": "keyword"}}
            },
            "industry_code": {"type": "keyword"},
            "audit_type": {"type": "keyword"},
            "revenue_bracket": {"type": "keyword"},
            "audit_office": {"type": "keyword"},
            "overview_content": {
                "type": "text",
                "analyzer": "korean_analyzer"
            },
            
            # 섹션 정보 (nested for precise querying)
            "sections_present": {"type": "keyword"},
            "section_spans": {
                "type": "nested",
                "properties": {
                    "name": {"type": "keyword"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"}
                }
            },
            
            # 범위 정보
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
            "start_page": {"type": "integer"},
            "end_page": {"type": "integer"},
            
            # 연결 정보
            "row_ids": {"type": "keyword"},
            "chunk_count": {"type": "integer"},
            
            # 메타
            "created_at": {"type": "date"},
            "extraction_version": {"type": "keyword"}
        }
    }
}

CHUNKS_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "korean_analyzer": {
                    "type": "custom",
                    "tokenizer": "nori_tokenizer",
                    "filter": ["lowercase", "nori_readingform"]
                }
            }
        }
    },
    "mappings": {
        "properties": {
            # 식별자
            "chunk_id": {"type": "keyword"},
            "finding_id": {"type": "keyword"},
            "doc_id": {"type": "keyword"},
            
            # 섹션 & 순서
            "section": {"type": "keyword"},
            "section_order": {"type": "integer"},
            "chunk_order": {"type": "integer"},
            
            # 내용 (한국어 분석)
            "code": {"type": "keyword"},
            "item": {
                "type": "text",
                "analyzer": "korean_analyzer",
                "fields": {
                    "keyword": {"type": "keyword"}
                }
            },
            "item_norm": {
                "type": "keyword"
            },
            "text": {
                "type": "text",
                "analyzer": "korean_analyzer"
            },
            "text_norm": {
                "type": "text",
                "analyzer": "korean_analyzer"
            },
            "text_raw": {
                "type": "keyword",
                "ignore_above": 32766
            },
            "meta_line": {"type": "text"},
            
            # 페이지 & 라인
            "page": {"type": "integer"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
            "line_range": {
                "type": "integer_range"
            },
            
            # 메타
            "extraction_version": {"type": "keyword"},
            "created_at": {"type": "date"},
            
            # 벡터 필드 (나중에 추가 가능)
            # "embedding": {
            #     "type": "dense_vector",
            #     "dims": 1024,
            #     "index": true,
            #     "similarity": "cosine"
            # }
        }
    }
}


def create_index_if_not_exists(es, index_name: str, mapping: dict):
    if not es.indices.exists(index=index_name):
        es.indices.create(index=index_name, body=mapping)
        print(f"OK: index created: {index_name}")
    else:
        print(f"OK: index already exists: {index_name}")


LAW_REFERENCES_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "korean_analyzer": {
                    "type": "custom",
                    "tokenizer": "nori_tokenizer",
                    "filter": ["lowercase", "nori_readingform"]
                }
            }
        }
    },
    "mappings": {
        "properties": {
            "law_id": {"type": "keyword"},
            "finding_id": {"type": "keyword"},
            "doc_id": {"type": "keyword"},
            "law_type": {"type": "keyword"},
            "law_name": {
                "type": "text",
                "analyzer": "korean_analyzer",
                "fields": {
                    "keyword": {"type": "keyword"}
                }
            },
            "law_content": {
                "type": "text",
                "analyzer": "korean_analyzer"
            },
            "page": {"type": "integer"},
            "line_number": {"type": "integer"},
            "law_order": {"type": "integer"},
            "extraction_version": {"type": "keyword"},
            "created_at": {"type": "date"}
        }
    }
}


def delete_and_recreate_index(es, index_name: str, mapping: dict):
    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
        print(f"OK: index deleted: {index_name}")
    
    es.indices.create(index=index_name, body=mapping)
    print(f"OK: index recreated: {index_name}")

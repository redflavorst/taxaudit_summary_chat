# Vectorstore Module

## 개요

Elasticsearch에 저장된 `findings`와 `chunks` 데이터를 임베딩하여 Qdrant에 업서트하는 모듈입니다.

## 구조

```
vectorstore/
├── __init__.py
├── utils.py            # 유틸리티 함수 (L2 정규화, 해시 등)
├── embedder.py         # SentenceTransformer 래퍼
├── qdrant_client.py    # Qdrant 클라이언트 및 컬렉션 설정
├── upsert_vectors.py   # ES → Qdrant 업서트 로직
└── README.md
```

## 설정

`create_db/config.py`에서 설정:

```python
# Qdrant 모드 선택 (3가지 방법)
# 1. 로컬 파일 저장 (권장, 서버 불필요)
QDRANT_URL: str = "path:./qdrant_storage"

# 2. 메모리 모드 (테스트용, 재시작 시 삭제)
# QDRANT_URL: str = ":memory:"

# 3. Qdrant 서버 (Docker/실행파일)
# QDRANT_URL: str = "http://localhost:6333"

QDRANT_API_KEY: Optional[str] = None
USE_QDRANT: bool = False  # True로 변경하면 run_ingest.py에서 자동 실행

EMBEDDING_MODEL_NAME: str = "BAAI/bge-m3"
EMBEDDING_DIM: int = 1024
NORMALIZE_L2: bool = True
UPSERT_BATCH: int = 256
```

## 사용법

### 1. 독립 실행

```bash
cd create_db
python -m vectorstore.upsert_vectors
```

### 2. run_ingest.py와 통합

`config.py`에서 `USE_QDRANT = True` 설정 후:

```bash
python create_db/run_ingest.py
```

## 컬렉션

- **findings_vectors**: finding 문서의 임베딩
  - 임베딩 입력: `item_detail + reason_kw_norm`
  - payload: finding_id, code, actions, industry_sub 등

- **chunks_vectors**: chunk 문서의 임베딩
  - 임베딩 입력: `text_norm`
  - payload: chunk_id, finding_id, section, code 등

## 검색 예시

```python
from qdrant_client import QdrantClient

qc = QdrantClient("http://localhost:6333")

# 벡터 검색
results = qc.search(
    collection_name="chunks_vectors",
    query_vector=embedding_vector,
    limit=10,
    query_filter={
        "must": [
            {"key": "code", "match": {"value": "10201"}}
        ]
    }
)
```

## 주의사항

1. **모델 다운로드**: 첫 실행 시 BAAI/bge-m3 모델 다운로드 (~2GB)
2. **메모리**: 배치 크기에 따라 2-4GB RAM 필요
3. **Qdrant**: 사전에 Qdrant 서버 실행 필요

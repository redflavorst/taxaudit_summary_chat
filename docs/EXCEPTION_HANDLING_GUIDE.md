# 예외 처리 개선 가이드

## 기존 문제점

### 1. 광범위한 예외 처리 ❌
```python
# 기존 코드 (expand_query.py:134)
try:
    response = requests.post(...)
except Exception as e:
    print(f"[ExpandQuery] LLM 확장 실패: {e}")
```

**문제점:**
- 모든 예외를 동일하게 처리하여 구체적인 원인 파악 불가
- 네트워크 오류, JSON 파싱 오류, 타임아웃 등 구분 불가
- 로깅이 부족하여 디버깅 어려움

---

## 개선 방안

### 1. expand_query.py 예외 처리 개선

```python
# langgraph_agent/nodes/expand_query.py
import logging
import requests
import json
from typing import Dict

logger = logging.getLogger(__name__)

def expand_query_with_llm(query: str, slots: Dict, ollama_url: str, model: str) -> Dict:
    """LLM을 사용하여 쿼리 확장"""

    try:
        response = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            },
            timeout=20
        )
        response.raise_for_status()  # HTTP 오류 발생 시 예외 발생

    except requests.Timeout:
        logger.error(f"LLM 요청 타임아웃 (20초): {ollama_url}")
        return _fallback_expansion(slots)

    except requests.ConnectionError as e:
        logger.error(f"LLM 서버 연결 실패: {ollama_url} - {e}")
        return _fallback_expansion(slots)

    except requests.HTTPError as e:
        logger.error(f"LLM HTTP 오류 (status: {e.response.status_code}): {e}")
        return _fallback_expansion(slots)

    except requests.RequestException as e:
        logger.error(f"LLM 요청 실패: {e}", exc_info=True)
        return _fallback_expansion(slots)

    # JSON 파싱
    try:
        result = response.json()
        expansion = json.loads(result.get("response", "{}"))

        # 필수 필드 검증
        if not isinstance(expansion, dict):
            logger.warning(f"LLM 응답이 dict가 아님: {type(expansion)}")
            return _fallback_expansion(slots)

        # 기본값 설정
        expansion.setdefault("must_have", slots.get("domain_tags", [])[:1])
        expansion.setdefault("should_have", slots.get("domain_tags", [])[1:])
        expansion.setdefault("related_terms", [])
        expansion.setdefault("boost_weights", {})

        logger.info(f"LLM 쿼리 확장 성공: must={expansion['must_have']}")
        return expansion

    except json.JSONDecodeError as e:
        logger.error(f"LLM 응답 JSON 파싱 실패: {e}")
        logger.debug(f"원본 응답: {response.text[:200]}")
        return _fallback_expansion(slots)

    except KeyError as e:
        logger.error(f"LLM 응답 필드 누락: {e}")
        return _fallback_expansion(slots)

    except Exception as e:
        logger.exception(f"예상치 못한 오류: {e}")
        return _fallback_expansion(slots)


def _fallback_expansion(slots: Dict) -> Dict:
    """LLM 실패 시 폴백 전략"""
    domain_tags = slots.get("domain_tags", [])
    logger.info(f"폴백 확장 사용: domain_tags={domain_tags}")

    return {
        "must_have": domain_tags[:1] if domain_tags else [],
        "should_have": domain_tags[1:],
        "related_terms": [],
        "boost_weights": {}
    }
```

---

### 2. retrieval.py 예외 처리 개선

```python
# langgraph_agent/retrieval.py
import logging
from elasticsearch import Elasticsearch, ElasticsearchException
from elasticsearch.exceptions import (
    ConnectionError as ESConnectionError,
    NotFoundError as ESNotFoundError,
    RequestError as ESRequestError
)
from qdrant_client.http.exceptions import (
    UnexpectedResponse as QdrantError,
    ResponseHandlingException as QdrantResponseError
)

logger = logging.getLogger(__name__)


class HybridRetriever:
    def __init__(self):
        try:
            self.es = Elasticsearch(
                config.es_url,
                basic_auth=(config.es_user, config.es_password) if config.es_user else None,
                request_timeout=30,
                max_retries=3,
                retry_on_timeout=True
            )
            # Elasticsearch 연결 테스트
            if not self.es.ping():
                raise ESConnectionError("Elasticsearch 핑 실패")
            logger.info(f"Elasticsearch 연결 성공: {config.es_url}")

        except ESConnectionError as e:
            logger.error(f"Elasticsearch 연결 실패: {config.es_url} - {e}")
            raise

        try:
            self.qdrant = QdrantClient(path=config.qdrant_path)
            # Qdrant 연결 테스트
            collections = self.qdrant.get_collections()
            logger.info(f"Qdrant 연결 성공: {len(collections.collections)}개 컬렉션")

        except QdrantError as e:
            logger.error(f"Qdrant 연결 실패: {config.qdrant_path} - {e}")
            raise

        try:
            self.embedder = get_embedder()
            logger.info("임베더 초기화 성공")
        except Exception as e:
            logger.error(f"임베더 초기화 실패: {e}", exc_info=True)
            raise


    def _find_docs_by_keyword(self, keyword: str, top_n: int = 50) -> List[tuple]:
        """키워드로 문서 ID 검색"""

        es_query = {
            "bool": {
                "should": [
                    {"match": {"item": {"query": keyword, "boost": 2.0}}},
                    {"match": {"reason_kw_norm": {"query": keyword, "boost": 1.5}}},
                    {"match": {"item_detail": {"query": keyword, "boost": 1.0}}}
                ]
            }
        }

        try:
            results = self.es.search(
                index="findings",
                body={"query": es_query, "size": top_n, "_source": ["doc_id"]},
                request_timeout=10
            )["hits"]["hits"]

            doc_scores = {}
            for hit in results:
                doc_id = hit["_source"].get("doc_id")
                if doc_id:
                    doc_scores[doc_id] = max(doc_scores.get(doc_id, 0), hit["_score"])

            sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
            logger.debug(f"키워드 '{keyword}' 검색 결과: {len(sorted_docs)}개 문서")
            return sorted_docs

        except ESConnectionError as e:
            logger.error(f"ES 연결 오류 (keyword: {keyword}): {e}")
            return []

        except ESNotFoundError:
            logger.warning(f"인덱스 'findings'를 찾을 수 없음")
            return []

        except ESRequestError as e:
            logger.error(f"ES 쿼리 오류 (keyword: {keyword}): {e}")
            logger.debug(f"쿼리: {es_query}")
            return []

        except ElasticsearchException as e:
            logger.error(f"ES 오류 (keyword: {keyword}): {e}", exc_info=True)
            return []

        except Exception as e:
            logger.exception(f"예상치 못한 오류 (keyword: {keyword}): {e}")
            return []


    def retrieve_findings(self, query: str, ...) -> tuple:
        """Findings 하이브리드 검색"""

        try:
            # Elasticsearch 검색
            es_results = self.es.search(
                index="findings",
                body={"query": es_query, "size": config.findings_top_k_es}
            )["hits"]["hits"]

            logger.info(f"ES 검색 완료: {len(es_results)}개 결과")

        except ElasticsearchException as e:
            logger.error(f"ES 검색 실패: {e}")
            es_results = []

        try:
            # Qdrant 벡터 검색
            query_vec = self.embedder.embed_query(query)

            vec_results = self.qdrant.search(
                collection_name=config.qdrant_collection_findings,
                query_vector=query_vec,
                limit=config.findings_top_k_vec,
                search_params=SearchParams(exact=False, hnsw_ef=config.qdrant_ef_search),
                score_threshold=vector_threshold
            )

            logger.info(f"Qdrant 검색 완료: {len(vec_results)}개 결과")

        except QdrantError as e:
            logger.error(f"Qdrant 검색 실패: {e}")
            vec_results = []
        except Exception as e:
            logger.exception(f"벡터 검색 중 예상치 못한 오류: {e}")
            vec_results = []

        # ES와 Qdrant 결과 융합
        if not es_results and not vec_results:
            logger.warning(f"검색 결과 없음: query={query}")
            return [], None, None

        merged = self._rrf_merge(es_results, vec_results, k=config.findings_rrf_k)[:top_n]
        logger.info(f"RRF 융합 완료: {len(merged)}개 결과")

        # ... 나머지 로직

        return findings, target_doc_ids, keyword_freq
```

---

### 3. run_ingest.py 예외 처리 개선

```python
# create_db/run_ingest.py
import logging
from elasticsearch import Elasticsearch, ElasticsearchException
import psycopg2
from psycopg2 import OperationalError, DatabaseError

logger = logging.getLogger(__name__)


def make_pg_conn():
    """PostgreSQL 연결 생성 (재시도 포함)"""
    max_retries = 3
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            connect_kwargs = _parse_pg_dsn(settings.PG_DSN)
            _ensure_database_exists(connect_kwargs)

            existing_options = connect_kwargs.get("options", "").strip()
            ingest_options = "-c client_encoding=UTF8 -c application_name=taxaudit_ingest"
            connect_kwargs["options"] = f"{existing_options} {ingest_options}".strip()

            conn = psycopg2.connect(**connect_kwargs)
            logger.info(f"PostgreSQL 연결 성공 (시도 {attempt + 1}/{max_retries})")
            return conn

        except OperationalError as e:
            logger.warning(f"PG 연결 실패 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info(f"{retry_delay}초 후 재시도...")
                time.sleep(retry_delay)
                retry_delay *= 2  # 지수 백오프
            else:
                logger.error(f"PG 연결 최대 재시도 초과")
                raise

        except DatabaseError as e:
            logger.error(f"PG 데이터베이스 오류: {e}")
            raise

        except Exception as e:
            logger.exception(f"PG 연결 중 예상치 못한 오류: {e}")
            raise


def main(md_paths):
    """메인 ETL 파이프라인"""

    # DB 연결 (context manager 사용)
    try:
        conn = make_pg_conn()
    except Exception as e:
        logger.error(f"DB 연결 실패로 종료: {e}")
        return

    try:
        # Elasticsearch 연결
        try:
            es_kwargs = {}
            if settings.ES_USER and settings.ES_PASSWORD:
                es_kwargs["basic_auth"] = (settings.ES_USER, settings.ES_PASSWORD)

            es = Elasticsearch(settings.ES_URL, **es_kwargs)
            if not es.ping():
                raise ElasticsearchException("ES 핑 실패")
            logger.info("Elasticsearch 연결 성공")

        except ElasticsearchException as e:
            logger.warning(f"ES 연결 실패, 인덱싱 스킵: {e}")
            es = None

        # 파일 처리
        for mp in md_paths:
            try:
                logger.info(f"처리 시작: {mp}")

                # Markdown 로드
                try:
                    md = load_markdown(mp)
                    doc_id = parse_doc_id(md)
                    logger.info(f"문서 ID: {doc_id}")
                except FileNotFoundError as e:
                    logger.error(f"파일 없음: {mp}")
                    continue
                except ValueError as e:
                    logger.error(f"doc_id 파싱 실패: {mp} - {e}")
                    continue

                # 파싱
                try:
                    rows = parse_table_rows(md, doc_id)
                    findings = parse_findings(md, doc_id)
                    law_refs = parse_law_references(md, json_path, doc_id)
                    logger.info(f"파싱 완료: rows={len(rows)}, findings={len(findings)}, laws={len(law_refs)}")
                except Exception as e:
                    logger.error(f"파싱 오류: {mp} - {e}", exc_info=True)
                    continue

                # 청킹
                try:
                    all_chunks = []
                    for f in findings:
                        chunks = make_chunks_for_finding(f, md_content=md)
                        all_chunks.extend(chunks)
                    logger.info(f"청킹 완료: {len(all_chunks)}개 청크")
                except Exception as e:
                    logger.error(f"청킹 오류: {mp} - {e}", exc_info=True)
                    continue

                # PostgreSQL 저장
                try:
                    upsert_many(conn, "documents", [{"doc_id": doc_id, ...}], "doc_id")
                    upsert_many(conn, "table_rows", rows, "row_id")
                    upsert_many(conn, "findings", findings, "finding_id")
                    upsert_many(conn, "chunks", all_chunks, "chunk_id")
                    upsert_many(conn, "law_references", law_refs, "law_id")
                    conn.commit()
                    logger.info(f"PostgreSQL 저장 완료")
                except DatabaseError as e:
                    logger.error(f"PG 저장 오류: {mp} - {e}")
                    conn.rollback()
                    continue

                # Elasticsearch 인덱싱
                if es:
                    try:
                        index_findings(es, "findings", findings_for_index, ...)
                        index_chunks(es, "chunks", all_chunks)
                        index_laws(es, "law_references", law_refs)
                        logger.info(f"ES 인덱싱 완료")
                    except ElasticsearchException as e:
                        logger.error(f"ES 인덱싱 오류: {mp} - {e}")
                        # 계속 진행 (ES 실패해도 PG는 성공)

                logger.info(f"처리 완료: {mp}")

            except Exception as e:
                logger.exception(f"파일 처리 중 예상치 못한 오류: {mp} - {e}")
                continue

        # Qdrant 벡터 저장
        if settings.USE_QDRANT:
            try:
                from vectorstore.upsert_vectors import run_all as upsert_vectorstore
                logger.info("Qdrant 업서트 시작...")
                upsert_vectorstore()
                logger.info("Qdrant 업서트 완료")
            except QdrantError as e:
                logger.error(f"Qdrant 업서트 실패: {e}")
            except Exception as e:
                logger.exception(f"Qdrant 업서트 중 예상치 못한 오류: {e}")

    finally:
        # 리소스 정리
        try:
            if conn:
                conn.close()
                logger.info("PostgreSQL 연결 종료")
        except Exception as e:
            logger.error(f"PG 연결 종료 실패: {e}")

        try:
            if es:
                es.close()
                logger.info("Elasticsearch 연결 종료")
        except Exception as e:
            logger.error(f"ES 연결 종료 실패: {e}")
```

---

## 예외 처리 원칙

### 1. 구체적인 예외 타입 사용
- ❌ `except Exception`
- ✅ `except ConnectionError`, `except ValueError`

### 2. 로깅 레벨 적절히 사용
- `logger.debug()`: 개발 디버깅 정보
- `logger.info()`: 일반 정보 (성공 메시지)
- `logger.warning()`: 경고 (복구 가능한 오류)
- `logger.error()`: 오류 (기능 실패)
- `logger.exception()`: 예외 (스택 트레이스 포함)

### 3. 재시도 전략
- 네트워크 오류: 지수 백오프로 재시도
- 타임아웃: 짧은 간격으로 재시도
- 영구적 오류: 즉시 실패

### 4. Fallback 전략
- LLM 실패 → 도메인 태그 사용
- ES 실패 → Qdrant만 사용
- 전체 실패 → 빈 결과 반환 (크래시 방지)

### 5. 리소스 정리
- `try-finally`로 연결 종료 보장
- Context manager 사용 (`with` 문)
- 예외 발생 시에도 정리 수행

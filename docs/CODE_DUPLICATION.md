# 코드 중복 제거 가이드

## 문제 4: 하이브리드 검색 로직 중복

### 현재 문제점

`retrieval.py`에서 **거의 동일한 하이브리드 검색 패턴**이 두 곳에 반복됩니다:

1. **`retrieve_findings()`** (157-370줄) - Findings 검색
2. **`retrieve_chunks_by_section()`** (372-482줄) - Chunks 검색

두 메서드 모두:
- Elasticsearch BM25 검색
- Qdrant 벡터 검색
- RRF 융합
- 결과 매핑

동일한 패턴을 수행하지만 **213줄의 코드가 중복**됩니다.

---

## 중복 코드 분석

### retrieve_findings() 구조

```python
def retrieve_findings(self, query: str, filters, expansion, top_n) -> tuple:
    # 1. 교집합 문서 필터링 (키워드 기반)
    target_doc_ids = None
    if expansion and expansion.get("must_have"):
        # ... 키워드별 문서 검색
        # ... 교집합/합집합 계산

    # 2. ES 쿼리 구성
    es_query = {"bool": {...}}
    if target_doc_ids:
        must_clauses.append({"terms": {"doc_id": target_doc_ids}})

    # 3. ES 검색
    es_results = self.es.search(
        index="findings",
        body={"query": es_query, "size": config.findings_top_k_es}
    )["hits"]["hits"]

    # 4. Qdrant 벡터 검색
    query_vec = self.embedder.embed_query(query)
    vec_results = self.qdrant.search(
        collection_name=config.qdrant_collection_findings,
        query_vector=query_vec,
        ...
    )

    # 5. RRF 융합
    merged = self._rrf_merge(es_results, vec_results, k=60)[:top_n]

    # 6. FindingHit 객체로 매핑
    findings = []
    for hit in merged:
        findings.append(FindingHit(...))

    return findings, target_doc_ids, keyword_freq
```

### retrieve_chunks_by_section() 구조

```python
def retrieve_chunks_by_section(self, query: str, section, finding_ids, filters, top_n) -> List:
    # 1. ES 쿼리 구성 (섹션 필터 추가)
    must_clauses = [
        {"multi_match": {"query": query, "fields": ["text^2", "text_norm", "item"]}},
        {"term": {"section": section}},
        {"terms": {"finding_id": finding_ids}}
    ]

    # 2. ES 검색
    es_results = self.es.search(
        index="chunks",
        body={"query": {"bool": {"must": must_clauses}}, "size": config.chunks_top_k_es}
    )["hits"]["hits"]

    # 3. Qdrant 벡터 검색
    query_vec = self.embedder.embed_query(query)
    vec_results = self.qdrant.search(
        collection_name=config.qdrant_collection_chunks,
        query_vector=query_vec,
        ...
    )

    # 4. RRF 융합
    merged = self._rrf_merge(es_results, vec_results, k=60)[:top_n]

    # 5. ChunkHit 객체로 매핑 + ES에서 text 가져오기
    chunks = []
    for hit in merged:
        # ... ES fallback 로직
        chunks.append(ChunkHit(...))

    return chunks
```

### 중복 패턴 정리

| 단계 | retrieve_findings | retrieve_chunks_by_section | 중복 여부 |
|------|-------------------|----------------------------|-----------|
| 1. 쿼리 구성 | ✅ | ✅ | ✅ 동일 |
| 2. ES 검색 | ✅ | ✅ | ✅ 동일 |
| 3. Qdrant 검색 | ✅ | ✅ | ✅ 동일 |
| 4. RRF 융합 | ✅ | ✅ | ✅ 동일 |
| 5. 결과 매핑 | FindingHit | ChunkHit | ❌ 차이 |

**결론:** 90% 이상의 로직이 동일하며, 5% 차이(결과 매핑)만 존재합니다.

---

## 해결 방법: 공통 하이브리드 검색 메서드 추출

### 리팩토링 전략

1. **공통 로직 추출**: `_hybrid_search()` 메서드 생성
2. **차이점 파라미터화**: 인덱스명, 컬렉션명, 매핑 함수
3. **재사용**: `retrieve_findings()`와 `retrieve_chunks_by_section()`에서 호출

---

## 리팩토링 코드

### 1단계: 공통 하이브리드 검색 메서드

```python
from typing import List, Dict, Any, Optional, Callable, TypeVar
from dataclasses import dataclass

T = TypeVar('T')  # FindingHit 또는 ChunkHit


@dataclass
class HybridSearchConfig:
    """하이브리드 검색 설정"""
    es_index: str
    qdrant_collection: str
    es_top_k: int
    vec_top_k: int
    rrf_k: int = 60
    score_threshold: float = 0.35


class HybridRetriever:
    def __init__(self):
        self.es = Elasticsearch(...)
        self.qdrant = QdrantClient(...)
        self.embedder = get_embedder()

    def _hybrid_search(
        self,
        query: str,
        es_query: Dict[str, Any],
        search_config: HybridSearchConfig,
        qdrant_filter: Optional[Filter] = None,
        result_mapper: Optional[Callable[[Dict], T]] = None,
        use_vector: bool = True,
        top_n: int = 100
    ) -> List[T]:
        """
        공통 하이브리드 검색 로직

        Args:
            query: 검색 쿼리
            es_query: Elasticsearch 쿼리 (bool 쿼리)
            search_config: 검색 설정 (인덱스, 컬렉션, top_k 등)
            qdrant_filter: Qdrant 필터 (선택)
            result_mapper: 결과 매핑 함수 (Dict → FindingHit/ChunkHit)
            use_vector: 벡터 검색 사용 여부
            top_n: 최종 반환 개수

        Returns:
            매핑된 결과 리스트 (FindingHit 또는 ChunkHit)
        """

        # 1. Elasticsearch 검색
        logger.debug(f"ES 검색 시작: index={search_config.es_index}, top_k={search_config.es_top_k}")

        try:
            es_results = self.es.search(
                index=search_config.es_index,
                body={
                    "query": es_query,
                    "size": search_config.es_top_k,
                    "_source": True
                }
            )["hits"]["hits"]

            logger.info(f"ES 검색 완료: {len(es_results)}개 결과")

        except ElasticsearchException as e:
            logger.error(f"ES 검색 실패: {e}")
            es_results = []

        # 2. Qdrant 벡터 검색 (옵션)
        vec_results = []
        if use_vector:
            logger.debug(f"Qdrant 검색 시작: collection={search_config.qdrant_collection}")

            try:
                query_vec = self._get_query_embedding_cached(query)

                vec_results = self.qdrant.search(
                    collection_name=search_config.qdrant_collection,
                    query_vector=query_vec,
                    query_filter=qdrant_filter,
                    limit=search_config.vec_top_k,
                    search_params=SearchParams(
                        exact=False,
                        hnsw_ef=config.qdrant_ef_search
                    ),
                    score_threshold=search_config.score_threshold
                )

                logger.info(f"Qdrant 검색 완료: {len(vec_results)}개 결과")

            except QdrantError as e:
                logger.error(f"Qdrant 검색 실패: {e}")
                vec_results = []

        # 3. RRF 융합
        if vec_results:
            merged = self._rrf_merge(es_results, vec_results, k=search_config.rrf_k)[:top_n]
            logger.info(f"RRF 융합 완료: ES {len(es_results)} + Qdrant {len(vec_results)} → {len(merged)}")
        else:
            # 벡터 검색 없음 또는 실패 → ES 결과만 사용
            merged = es_results[:top_n]
            logger.info(f"BM25만 사용: {len(merged)}개 결과")

        # 4. 결과 매핑 (FindingHit 또는 ChunkHit)
        if result_mapper:
            return [result_mapper(hit) for hit in merged]
        else:
            # 매퍼 없으면 원본 반환
            return merged
```

---

### 2단계: retrieve_findings() 리팩토링

```python
def retrieve_findings(
    self,
    query: str,
    filters: Optional[Dict[str, Any]] = None,
    expansion: Optional[Dict[str, Any]] = None,
    top_n: int = 30
) -> tuple[List[FindingHit], Optional[List[str]], Optional[Dict[str, int]]]:
    """
    Findings 하이브리드 검색 (리팩토링 버전)

    반환값:
        (findings, target_doc_ids, keyword_freq)
    """

    # 1. 교집합 문서 필터링 (기존 로직 유지)
    target_doc_ids = None
    keyword_freq = None

    if expansion and expansion.get("must_have"):
        # ... 교집합/합집합 로직 (동일)
        target_doc_ids, keyword_freq = self._filter_docs_by_keywords(expansion["must_have"])

    # 2. ES 쿼리 구성
    es_query = self._build_findings_query(query, expansion, filters, target_doc_ids)

    # 3. Qdrant 필터 구성
    qdrant_filter = self._build_qdrant_filter(filters)

    # 4. 검색 설정
    search_config = HybridSearchConfig(
        es_index="findings",
        qdrant_collection=config.qdrant_collection_findings,
        es_top_k=config.findings_top_k_es,
        vec_top_k=config.findings_top_k_vec,
        rrf_k=config.findings_rrf_k,
        score_threshold=0.65 if len(expansion.get("must_have", [])) >= 2 else 0.35
    )

    # 5. 결과 매핑 함수
    def map_to_finding_hit(hit: Dict) -> FindingHit:
        source = hit.get("_source", {})
        if not source and "vec_hit" in hit:
            source = hit["vec_hit"].payload

        score = hit.get("rrf_score", hit.get("_score", 0.0))

        return FindingHit(
            finding_id=source.get("finding_id", hit["_id"]),
            doc_id=source.get("doc_id", ""),
            item=source.get("item"),
            item_detail=source.get("item_detail"),
            code=source.get("code"),
            score_combined=score
        )

    # ✅ 공통 하이브리드 검색 메서드 호출
    use_vector = len(expansion.get("must_have", [])) >= 2 if expansion else True

    findings = self._hybrid_search(
        query=query,
        es_query=es_query,
        search_config=search_config,
        qdrant_filter=qdrant_filter,
        result_mapper=map_to_finding_hit,
        use_vector=use_vector,
        top_n=top_n
    )

    # 스코어 필터링 (교집합일 때만)
    if target_doc_ids and findings:
        score_threshold = findings[0].score_combined * 0.5
        findings = [f for f in findings if f.score_combined >= score_threshold][:top_n]

    return findings, target_doc_ids, keyword_freq


def _build_findings_query(
    self,
    query: str,
    expansion: Optional[Dict],
    filters: Optional[Dict],
    target_doc_ids: Optional[List[str]]
) -> Dict:
    """Findings ES 쿼리 구성 (헬퍼 메서드)"""

    should_clauses = []
    must_clauses = []

    # 쿼리 확장 적용
    if expansion and expansion.get("must_have"):
        must_keywords = expansion["must_have"]
        should_keywords = expansion.get("should_have", []) + expansion.get("related_terms", [])
        boost_weights = expansion.get("boost_weights", {})

        for kw in must_keywords:
            boost = boost_weights.get(kw, 3.0)
            should_clauses.append({
                "multi_match": {
                    "query": kw,
                    "fields": [f"item^{boost}", f"reason_kw_norm^{boost*0.8}"]
                }
            })

        for kw in should_keywords:
            boost = boost_weights.get(kw, 1.5)
            should_clauses.append({
                "multi_match": {
                    "query": kw,
                    "fields": [f"item^{boost}", f"reason_kw_norm^{boost*0.8}"]
                }
            })

    else:
        # 기본 쿼리
        must_clauses.append({
            "multi_match": {"query": query, "fields": ["item^2", "reason_kw_norm", "item_detail"]}
        })

    # 문서 필터
    if target_doc_ids:
        must_clauses.append({"terms": {"doc_id": target_doc_ids}})

    # 메타 필터
    if filters:
        if filters.get("code"):
            must_clauses.append({"terms": {"code": filters["code"]}})
        if filters.get("industry_sub"):
            must_clauses.append({"terms": {"industry_sub": filters["industry_sub"]}})

    # 최종 쿼리 구성
    es_query = {"bool": {}}
    if must_clauses:
        es_query["bool"]["must"] = must_clauses
    if should_clauses:
        es_query["bool"]["should"] = should_clauses
        if not target_doc_ids:
            es_query["bool"]["minimum_should_match"] = 1

    return es_query
```

---

### 3단계: retrieve_chunks_by_section() 리팩토링

```python
def retrieve_chunks_by_section(
    self,
    query: str,
    section: str,
    finding_ids: List[str],
    filters: Optional[Dict[str, Any]] = None,
    top_n: int = 300
) -> List[ChunkHit]:
    """
    Chunks 섹션별 하이브리드 검색 (리팩토링 버전)
    """

    # 1. ES 쿼리 구성
    must_clauses = [
        {"multi_match": {"query": query, "fields": ["text^2", "text_norm", "item"]}},
        {"term": {"section": section}},
        {"terms": {"finding_id": finding_ids}}
    ]

    if filters:
        if filters.get("code"):
            must_clauses.append({"terms": {"code": filters["code"]}})
        if filters.get("doc_id"):
            must_clauses.append({"terms": {"doc_id": filters["doc_id"]}})

    es_query = {"bool": {"must": must_clauses}}

    # 2. Qdrant 필터 구성
    qdrant_filter = Filter(
        must=[FieldCondition(key="section", match=MatchValue(value=section))],
        should=[FieldCondition(key="finding_id", match=MatchValue(value=fid)) for fid in finding_ids]
    )

    # 3. 검색 설정
    search_config = HybridSearchConfig(
        es_index="chunks",
        qdrant_collection=config.qdrant_collection_chunks,
        es_top_k=config.chunks_top_k_es,
        vec_top_k=config.chunks_top_k_vec,
        rrf_k=60,
        score_threshold=config.qdrant_score_threshold
    )

    # 4. 결과 매핑 함수
    def map_to_chunk_hit(hit: Dict) -> ChunkHit:
        source = hit.get("_source", {})
        from_qdrant = False

        if not source and "vec_hit" in hit:
            source = hit["vec_hit"].payload
            from_qdrant = True

        # Qdrant payload에 text 없으면 ES에서 가져오기
        text_content = source.get("text", "")
        if from_qdrant and (not text_content or len(text_content) < 10):
            chunk_id = source.get("chunk_id", hit.get("_id"))
            text_content = self._fetch_text_from_es(chunk_id)
            source["text"] = text_content

        return ChunkHit(
            chunk_id=source.get("chunk_id", hit["_id"]),
            finding_id=source.get("finding_id", ""),
            doc_id=source.get("doc_id", ""),
            section=source.get("section", section),
            section_order=source.get("section_order", 0),
            chunk_order=source.get("chunk_order", 0),
            code=source.get("code"),
            item=source.get("item"),
            item_norm=source.get("item_norm"),
            page=source.get("page"),
            start_line=source.get("start_line"),
            end_line=source.get("end_line"),
            text=text_content,
            text_norm=source.get("text_norm"),
            score_combined=hit.get("rrf_score", 0.0)
        )

    # ✅ 공통 하이브리드 검색 메서드 호출
    chunks = self._hybrid_search(
        query=query,
        es_query=es_query,
        search_config=search_config,
        qdrant_filter=qdrant_filter,
        result_mapper=map_to_chunk_hit,
        use_vector=True,
        top_n=top_n
    )

    return chunks


def _fetch_text_from_es(self, chunk_id: str) -> str:
    """ES에서 청크 텍스트 가져오기 (헬퍼 메서드)"""
    try:
        es_doc = self.es.get(index="chunks", id=chunk_id, _source=["text"])
        return es_doc["_source"].get("text", "")
    except ESNotFoundError:
        logger.warning(f"청크 {chunk_id}를 ES에서 찾을 수 없음")
        return ""
    except ElasticsearchException as e:
        logger.error(f"ES에서 텍스트 가져오기 실패: {chunk_id} - {e}")
        return ""
```

---

## 리팩토링 효과

### 코드 라인 수 비교

| 항목 | 기존 | 리팩토링 후 | 감소율 |
|------|------|-------------|--------|
| **retrieve_findings()** | 213줄 | 80줄 | **62% 감소** |
| **retrieve_chunks_by_section()** | 110줄 | 55줄 | **50% 감소** |
| **공통 메서드 (_hybrid_search)** | 0줄 | 100줄 | 신규 |
| **헬퍼 메서드** | 0줄 | 60줄 | 신규 |
| **총계** | 323줄 | **295줄** | **9% 감소** |

### 유지보수성 개선

| 측면 | 기존 | 리팩토링 후 |
|------|------|-------------|
| **버그 수정** | 2곳 수정 | **1곳만 수정** ✅ |
| **기능 추가** | 2곳 추가 | **1곳만 추가** ✅ |
| **테스트** | 2개 테스트 | **1개 테스트** ✅ |
| **가독성** | 중복으로 혼란 | **명확한 역할** ✅ |

---

## 추가 리팩토링 기회

### 1. 필터 구성 로직 공통화

```python
class FilterBuilder:
    """ES/Qdrant 필터 빌더"""

    @staticmethod
    def build_es_filters(filters: Optional[Dict]) -> List[Dict]:
        """ES 필터 생성"""
        clauses = []
        if not filters:
            return clauses

        if filters.get("code"):
            clauses.append({"terms": {"code": filters["code"]}})
        if filters.get("doc_id"):
            clauses.append({"terms": {"doc_id": filters["doc_id"]}})
        if filters.get("industry_sub"):
            clauses.append({"terms": {"industry_sub": filters["industry_sub"]}})

        return clauses

    @staticmethod
    def build_qdrant_filter(filters: Optional[Dict]) -> Optional[Filter]:
        """Qdrant 필터 생성"""
        if not filters:
            return None

        conditions = []
        if filters.get("code"):
            for code in filters["code"]:
                conditions.append(FieldCondition(key="code", match=MatchValue(value=code)))

        if filters.get("doc_id"):
            for doc_id in filters["doc_id"]:
                conditions.append(FieldCondition(key="doc_id", match=MatchValue(value=doc_id)))

        return Filter(should=conditions) if conditions else None
```

### 2. 결과 매핑 클래스 패턴

```python
from abc import ABC, abstractmethod

class ResultMapper(ABC):
    """결과 매핑 추상 클래스"""

    @abstractmethod
    def map(self, hit: Dict) -> Any:
        """결과를 데이터 클래스로 매핑"""
        pass


class FindingMapper(ResultMapper):
    """FindingHit 매퍼"""

    def map(self, hit: Dict) -> FindingHit:
        source = self._extract_source(hit)
        score = hit.get("rrf_score", hit.get("_score", 0.0))

        return FindingHit(
            finding_id=source.get("finding_id", hit["_id"]),
            doc_id=source.get("doc_id", ""),
            item=source.get("item"),
            item_detail=source.get("item_detail"),
            code=source.get("code"),
            score_combined=score
        )

    @staticmethod
    def _extract_source(hit: Dict) -> Dict:
        """ES 또는 Qdrant 소스 추출"""
        source = hit.get("_source", {})
        if not source and "vec_hit" in hit:
            source = hit["vec_hit"].payload
        return source


class ChunkMapper(ResultMapper):
    """ChunkHit 매퍼"""

    def __init__(self, es_client: Elasticsearch):
        self.es = es_client

    def map(self, hit: Dict) -> ChunkHit:
        source = self._extract_source(hit)

        # Text fallback 로직
        text_content = self._get_text_with_fallback(hit, source)

        return ChunkHit(
            chunk_id=source.get("chunk_id", hit["_id"]),
            finding_id=source.get("finding_id", ""),
            # ... 필드 매핑
            text=text_content,
            score_combined=hit.get("rrf_score", 0.0)
        )

    def _get_text_with_fallback(self, hit: Dict, source: Dict) -> str:
        """Qdrant에 text 없으면 ES에서 가져오기"""
        text = source.get("text", "")
        if text and len(text) >= 10:
            return text

        # ES fallback
        chunk_id = source.get("chunk_id", hit.get("_id"))
        try:
            es_doc = self.es.get(index="chunks", id=chunk_id, _source=["text"])
            return es_doc["_source"].get("text", "")
        except Exception:
            return ""
```

---

## 최종 아키텍처

```
HybridRetriever
├── _hybrid_search()           # 공통 하이브리드 검색
│   ├── ES 검색
│   ├── Qdrant 검색
│   ├── RRF 융합
│   └── 결과 매핑
│
├── retrieve_findings()        # Findings 검색
│   ├── _filter_docs_by_keywords()
│   ├── _build_findings_query()
│   └── _hybrid_search() 호출 ✅
│
├── retrieve_chunks_by_section()  # Chunks 검색
│   ├── _build_chunks_query()
│   └── _hybrid_search() 호출 ✅
│
└── 헬퍼 메서드
    ├── FilterBuilder
    ├── FindingMapper
    └── ChunkMapper
```

---

## 구현 우선순위

### 🔴 High Priority (즉시 적용)
1. **_hybrid_search() 메서드 추출** - 핵심 중복 제거

### 🟡 Medium Priority (1주 내)
2. **쿼리 빌더 메서드 분리** - 가독성 향상
3. **필터 빌더 클래스** - 필터 로직 통합

### 🟢 Low Priority (장기)
4. **결과 매퍼 클래스 패턴** - OOP 설계 개선
5. **전략 패턴 적용** - 다양한 검색 전략 지원

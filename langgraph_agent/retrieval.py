"""
Hybrid Retrieval: Elasticsearch + Qdrant with RRF/MMR
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "create_db"))

from typing import List, Dict, Any, Optional
from elasticsearch import Elasticsearch
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, SearchParams

from create_db.vectorstore.embedder import get_embedder
from .config import config
from .state import FindingHit, ChunkHit


class HybridRetriever:
    def __init__(self):
        self.es = Elasticsearch(
            config.es_url,
            basic_auth=(config.es_user, config.es_password) if config.es_user else None
        )
        self.qdrant = QdrantClient(path=config.qdrant_path)
        self.embedder = get_embedder()
    
    def _find_docs_by_keyword(self, keyword: str, top_n: int = 50) -> List[tuple]:
        """
        키워드로 문서 ID 검색 (빠른 문서 레벨 필터링용)
        
        Returns:
            List[(doc_id, score)]
        """
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
                body={
                    "query": es_query,
                    "size": top_n,
                    "_source": ["doc_id"]
                }
            )["hits"]["hits"]
            
            doc_scores = {}
            for hit in results:
                doc_id = hit["_source"].get("doc_id")
                if doc_id:
                    score = hit["_score"]
                    doc_scores[doc_id] = max(doc_scores.get(doc_id, 0), score)
            
            return sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
        
        except Exception as e:
            print(f"[_find_docs_by_keyword] 검색 실패 ({keyword}): {e}")
            return []
    
    def _rrf_merge(self, es_results: List[Dict], vec_results: List[Dict], k: int = 60) -> List[Dict]:
        """Reciprocal Rank Fusion"""
        scores = {}
        for rank, hit in enumerate(es_results, 1):
            doc_id = hit["_id"]
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank)
        
        for rank, hit in enumerate(vec_results, 1):
            doc_id = str(hit.id)
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank)
        
        merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        es_map = {h["_id"]: h for h in es_results}
        vec_map = {str(h.id): h for h in vec_results}
        
        results = []
        for doc_id, score in merged:
            if doc_id in es_map:
                results.append({**es_map[doc_id], "rrf_score": score})
            elif doc_id in vec_map:
                results.append({"_id": doc_id, "rrf_score": score, "vec_hit": vec_map[doc_id]})
        
        return results
    
    def _calculate_keyword_frequency(self, doc_ids: List[str], keywords: List[str]) -> Dict[str, int]:
        """
        문서들에서 각 키워드의 총 출현 빈도 계산 (ES termvectors API 사용)
        
        Returns:
            {keyword: total_count}
        """
        keyword_freq = {kw: 0 for kw in keywords}
        
        for doc_id in doc_ids[:5]:  # 최대 5개 문서만 분석 (성능)
            for kw in keywords:
                try:
                    # ES에서 해당 문서의 text 필드에서 키워드 빈도 조회
                    result = self.es.search(
                        index="findings",
                        body={
                            "query": {
                                "bool": {
                                    "must": [
                                        {"term": {"doc_id": doc_id}},
                                        {"match": {"text": kw}}
                                    ]
                                }
                            },
                            "size": 0,
                            "aggs": {
                                "keyword_count": {
                                    "sum": {
                                        "script": {
                                            "source": "return params._source.text.split(params.keyword).length - 1",
                                            "params": {"keyword": kw}
                                        }
                                    }
                                }
                            }
                        }
                    )
                    
                    # 간단한 방법: match된 hits 수로 근사
                    count = result['hits']['total']['value']
                    keyword_freq[kw] += count
                    
                except Exception as e:
                    # 실패 시 간단한 count 방법 사용
                    try:
                        count_result = self.es.count(
                            index="findings",
                            body={
                                "query": {
                                    "bool": {
                                        "must": [
                                            {"term": {"doc_id": doc_id}},
                                            {"match": {"text": kw}}
                                        ]
                                    }
                                }
                            }
                        )
                        keyword_freq[kw] += count_result.get('count', 0)
                    except:
                        pass
        
        return keyword_freq
    
    def retrieve_findings(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        expansion: Optional[Dict[str, Any]] = None,
        top_n: int = 30
    ) -> tuple[List[FindingHit], Optional[List[str]], Optional[Dict[str, int]]]:
        """
        Findings 하이브리드 검색 (ES + Qdrant) with 교집합 기반 문서 필터링
        
        Args:
            expansion: LLM 쿼리 확장 결과 (must_have, should_have, related_terms, boost_weights)
        
        Returns:
            (findings, target_doc_ids, keyword_freq)
        
        Strategy:
            1. must_have 키워드별로 문서 검색
            2. 교집합 문서 우선 (모든 키워드 포함)
            3. 교집합 없으면 합집합으로 폴백 (OR)
            4. 교집합 문서에서 키워드 빈도 계산
            5. 필터링된 문서들 내에서 상세 검색
        """
        # Step 1: must_have + should_have 키워드로 문서 필터링
        target_doc_ids = None
        keyword_freq = None
        
        if expansion and expansion.get("must_have"):
            must_keywords = expansion["must_have"]
            
            # must_have 키워드만 문서 필터링에 사용 (should_have는 제외)
            search_keywords = must_keywords[:3]  # 상위 3개만
            
            if len(search_keywords) >= 1:  # 키워드 1개 이상이면 문서 필터링
                print(f"[RetrieveFindings] 키워드별 문서 검색 시작: {search_keywords}")
                
                keyword_docs = {}
                for kw in search_keywords:
                    docs = self._find_docs_by_keyword(kw, top_n=50)
                    keyword_docs[kw] = set([doc_id for doc_id, _ in docs])
                    print(f"  - '{kw}': {len(keyword_docs[kw])}개 문서")
                
                # 교집합/합집합 계산
                if keyword_docs:
                    if len(search_keywords) >= 2:
                        # 키워드 2개 이상: 교집합 우선
                        intersection = set.intersection(*keyword_docs.values())
                        print(f"[RetrieveFindings] 교집합 문서: {len(intersection)}개")
                        
                        if intersection:
                            target_doc_ids = list(intersection)
                            
                            # 교집합 문서에서 키워드 빈도 계산
                            print(f"[RetrieveFindings] 키워드 빈도 계산 중...")
                            keyword_freq = self._calculate_keyword_frequency(target_doc_ids, must_keywords)
                            print(f"[RetrieveFindings] 키워드 빈도: {keyword_freq}")
                        else:
                            # 폴백: 합집합 (OR)
                            union = set.union(*keyword_docs.values())
                            print(f"[RetrieveFindings] 교집합 없음 → 합집합으로 폴백: {len(union)}개")
                            target_doc_ids = list(union)[:30]
                    else:
                        # 키워드 1개: 해당 키워드 포함 문서만
                        target_doc_ids = list(keyword_docs[search_keywords[0]])
                        print(f"[RetrieveFindings] 단일 키워드 문서: {len(target_doc_ids)}개")
        
        # Step 2: 상세 검색 쿼리 구성
        should_clauses_for_ranking = None
        
        if expansion and expansion.get("must_have"):
            must_keywords = expansion["must_have"]
            should_keywords = expansion.get("should_have", []) + expansion.get("related_terms", [])
            boost_weights = expansion.get("boost_weights", {})
            
            # must_have를 should로 변경 (OR 검색, boost로 우선순위 조정)
            should_clauses = []
            for kw in must_keywords:
                boost = boost_weights.get(kw, 3.0)
                should_clauses.append({
                    "multi_match": {
                        "query": kw,
                        "fields": [f"item^{boost}", f"reason_kw_norm^{boost*0.8}", f"item_detail^{boost*0.5}"]
                    }
                })
            
            for kw in should_keywords:
                boost = boost_weights.get(kw, 1.5)
                should_clauses.append({
                    "multi_match": {
                        "query": kw,
                        "fields": [f"item^{boost}", f"reason_kw_norm^{boost*0.8}", f"item_detail^{boost*0.5}"]
                    }
                })
            
            must_clauses = []
        else:
            must_clauses = [{"multi_match": {"query": query, "fields": ["item^2", "reason_kw_norm", "item_detail"]}}]
            should_clauses = []
        
        # 문서 필터 추가 (교집합/합집합 결과)
        if target_doc_ids:
            if not must_clauses:
                must_clauses = []
            must_clauses.append({"terms": {"doc_id": target_doc_ids}})
            print(f"[RetrieveFindings] 문서 필터 적용: {len(target_doc_ids)}개 문서로 제한")
            
            # 문서 필터가 있을 때도 should 유지 (랭킹용)
            should_clauses_for_ranking = should_clauses if should_clauses else None
        
        # 기타 필터
        if filters:
            if not must_clauses:
                must_clauses = []
            if filters.get("code"):
                must_clauses.append({"terms": {"code": filters["code"]}})
            if filters.get("industry_sub"):
                must_clauses.append({"terms": {"industry_sub": filters["industry_sub"]}})
            if filters.get("domain_tags"):
                must_clauses.append({"terms": {"domain_tags": filters["domain_tags"]}})
        
        # ES 쿼리 구성
        es_query = {"bool": {}}
        if must_clauses:
            es_query["bool"]["must"] = must_clauses
        
        # should 조건 처리
        if should_clauses_for_ranking:
            # 문서 필터 있음: should는 랭킹용만
            es_query["bool"]["should"] = should_clauses_for_ranking
        elif should_clauses:
            # 문서 필터 없음: should가 매칭 조건
            es_query["bool"]["should"] = should_clauses
            es_query["bool"]["minimum_should_match"] = 1
        
        print(f"[DEBUG] ES Query: {es_query}")
        
        es_results = self.es.search(
            index="findings",
            body={
                "query": es_query,
                "size": config.findings_top_k_es
            }
        )["hits"]["hits"]
        
        print(f"[DEBUG] ES Results count: {len(es_results)}")
        
        # 키워드 개수에 따라 검색 전략 변경
        # - 1개: BM25만 (정확한 텍스트 매칭)
        # - 2개 이상: 하이브리드 (BM25 + Vector)
        must_have_count = len(expansion.get("must_have", [])) if expansion else 0
        use_vector_search = must_have_count >= 2
        
        if use_vector_search:
            query_vec = self.embedder.embed_query(query)
            
            # 복수 키워드일 때는 임계값 강화 (도메인 내 과도한 유사도 방지)
            vector_threshold = 0.65  # 기본 0.35 → 0.65로 강화
            
            qdrant_filter = None
            if filters:
                conditions = []
                if filters.get("code"):
                    for code in filters["code"]:
                        conditions.append(FieldCondition(key="code", match=MatchValue(value=code)))
                if filters.get("doc_id"):
                    for doc_id in filters["doc_id"]:
                        conditions.append(FieldCondition(key="doc_id", match=MatchValue(value=doc_id)))
                if conditions:
                    qdrant_filter = Filter(should=conditions)
            
            vec_results = self.qdrant.search(
                collection_name=config.qdrant_collection_findings,
                query_vector=query_vec,
                query_filter=qdrant_filter,
                limit=config.findings_top_k_vec,
                search_params=SearchParams(
                    exact=False,
                    hnsw_ef=config.qdrant_ef_search
                ),
                score_threshold=vector_threshold  # 강화된 임계값
            )
            
            merged = self._rrf_merge(es_results, vec_results, k=config.findings_rrf_k)[:top_n]
            print(f"[RetrieveFindings] 하이브리드 검색: ES {len(es_results)}개 + Vector {len(vec_results)}개 → RRF {len(merged)}개")
        else:
            # BM25만 사용
            merged = es_results[:top_n]
            print(f"[RetrieveFindings] BM25 검색만 사용: {len(merged)}개")
        
        findings = []
        for hit in merged:
            source = hit.get("_source", {})
            if not source and "vec_hit" in hit:
                source = hit["vec_hit"].payload
            
            # BM25 전용일 때는 _score 사용, RRF일 때는 rrf_score 사용
            score = hit.get("rrf_score") if use_vector_search else hit.get("_score", 0.0)
            
            findings.append(FindingHit(
                finding_id=source.get("finding_id", hit["_id"]),
                doc_id=source.get("doc_id", ""),
                item=source.get("item"),
                item_detail=source.get("item_detail"),
                code=source.get("code"),
                score_combined=score
            ))
        
        # target_doc_ids 필터가 있으면 상위 findings만 유지
        if target_doc_ids and findings:
            # 문서 필터가 활성화된 경우 스코어 임계값 적용
            score_threshold = findings[0].score_combined * 0.5  # 최고 스코어의 50% 이상만
            findings = [f for f in findings if f.score_combined >= score_threshold][:top_n]
        
        return findings, target_doc_ids, keyword_freq
    
    def retrieve_chunks_by_section(
        self,
        query: str,
        section: str,
        finding_ids: List[str],
        filters: Optional[Dict[str, Any]] = None,
        top_n: int = 300
    ) -> List[ChunkHit]:
        """
        Chunks 섹션별 하이브리드 검색 (ES + Qdrant)
        """
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
        
        es_results = self.es.search(
            index="chunks",
            body={
                "query": {"bool": {"must": must_clauses}},
                "size": config.chunks_top_k_es,
                "_source": True  # 모든 필드 포함
            }
        )["hits"]["hits"]
        
        query_vec = self.embedder.embed_query(query)
        
        must_conditions = [
            FieldCondition(key="section", match=MatchValue(value=section))
        ]
        
        should_conditions = []
        for fid in finding_ids:
            should_conditions.append(FieldCondition(key="finding_id", match=MatchValue(value=fid)))
        
        additional_conditions = []
        if filters:
            if filters.get("code"):
                for code in filters["code"]:
                    additional_conditions.append(FieldCondition(key="code", match=MatchValue(value=code)))
            if filters.get("doc_id"):
                for doc_id in filters["doc_id"]:
                    must_conditions.append(FieldCondition(key="doc_id", match=MatchValue(value=doc_id)))
        
        if additional_conditions:
            qdrant_filter = Filter(must=must_conditions, should=should_conditions + additional_conditions)
        else:
            qdrant_filter = Filter(must=must_conditions, should=should_conditions)
        
        vec_results = self.qdrant.search(
            collection_name=config.qdrant_collection_chunks,
            query_vector=query_vec,
            query_filter=qdrant_filter,
            limit=config.chunks_top_k_vec,
            search_params=SearchParams(
                exact=False,
                hnsw_ef=config.qdrant_ef_search
            ),
            score_threshold=config.qdrant_score_threshold
        )
        
        merged = self._rrf_merge(es_results, vec_results, k=60)[:top_n]
        
        chunks = []
        for hit in merged:
            source = hit.get("_source", {})
            from_qdrant = False
            if not source and "vec_hit" in hit:
                source = hit["vec_hit"].payload
                from_qdrant = True
            
            # Qdrant payload에 text가 없으면 ES에서 가져오기
            text_content = source.get("text", "")
            if from_qdrant and (not text_content or len(text_content) < 10):
                chunk_id = source.get("chunk_id", hit.get("_id"))
                try:
                    # ES에서 해당 청크의 text 가져오기
                    es_doc = self.es.get(index="chunks", id=chunk_id, _source=["text", "text_norm"])
                    if es_doc and "_source" in es_doc:
                        text_content = es_doc["_source"].get("text", "")
                        source["text"] = text_content
                        source["text_norm"] = es_doc["_source"].get("text_norm", "")
                except Exception as e:
                    print(f"[WARN] ES에서 text 가져오기 실패: {chunk_id}, {e}")
            
            chunks.append(ChunkHit(
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
            ))
        
        return chunks

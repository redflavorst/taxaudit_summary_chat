"""
LangGraph State Schema
"""

from typing import TypedDict, List, Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class FindingHit:
    finding_id: str
    doc_id: str
    item: Optional[str]
    item_detail: Optional[str]
    code: Optional[str]
    score_bm25: float = 0.0
    score_vector: float = 0.0
    score_combined: float = 0.0


@dataclass
class ChunkHit:
    chunk_id: str
    finding_id: str
    doc_id: str
    section: str
    section_order: int
    chunk_order: int
    code: Optional[str]
    item: Optional[str]
    item_norm: Optional[str]
    page: Optional[int]
    start_line: Optional[int]
    end_line: Optional[int]
    text: str
    text_norm: Optional[str]
    score_bm25: float = 0.0
    score_vector: float = 0.0
    score_field: float = 0.0
    score_combined: float = 0.0


@dataclass
class RankedBlock:
    finding_id: str
    doc_id: str
    item: Optional[str]
    code: Optional[str]
    score: float
    chunks: List[ChunkHit]
    source_sections: List[str]


@dataclass
class Citation:
    doc_id: str
    finding_id: str
    chunk_id: str
    page: Optional[int]
    start_line: Optional[int]
    end_line: Optional[int]
    text: str
    section: str


class Slots(TypedDict, total=False):
    industry_sub: List[str]
    domain_tags: List[str]
    code: List[str]
    entities: List[str]
    section_hints: Dict[str, List[str]]  # {"착안": [...], "기법": [...]}
    required_terms: List[str]  # 필수 검색어
    optional_terms: List[str]  # 선택 검색어
    free_text: str
    confidence: float  # 슬롯 추출 신뢰도 (0.0~1.0)
    expansion: Optional[Dict[str, Any]]  # LLM 기반 쿼리 확장 결과


class ContextData(TypedDict):
    packed_text: str
    citations: List[Citation]


class AgentState(TypedDict):
    user_query: str
    normalized_query: Optional[str]  # 전처리된 질의
    intent: Optional[str]  # case_lookup, explain, clarify 등
    slots: Slots
    needs_clarification: bool  # Clarify 필요 여부
    clarification_question: Optional[str]  # Clarify 질문
    target_doc_ids: Optional[List[str]]  # 교집합 기반 문서 필터 (키워드 교집합 결과)
    keyword_freq: Optional[Dict[str, int]]  # 문서 레벨 키워드 빈도수 {keyword: count}
    keyword_block_counts: Optional[Dict[str, int]]  # 키워드별 블록 매칭 건수 {keyword: count}
    findings_candidates: List[FindingHit]
    chunks_candidates: List[ChunkHit]
    section_groups: Dict[str, List[ChunkHit]]  # {"착안": [...], "기법": [...]}
    block_ranking: List[RankedBlock]
    excluded_blocks: List[RankedBlock]  # 필터링으로 제외된 블록 (차집합)
    context: ContextData
    answer: Optional[str]
    error: Optional[str]

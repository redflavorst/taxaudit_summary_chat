"""
RetrieveChunksBySection Node: 섹션별 Chunks 하이브리드 검색
"""

from typing import List
from ..state import AgentState, ChunkHit
from ..retrieval import HybridRetriever
from ..config import config


def retrieve_chunks_by_section(state: AgentState) -> AgentState:
    """
    RetrieveChunksBySection 노드: 섹션별 Chunks 하이브리드 검색
    """
    findings = state["findings_candidates"]
    if not findings:
        print("[RetrieveChunksBySection] Findings가 없어 스킵")
        state["chunks_candidates"] = []
        state["section_groups"] = {"착안": [], "기법": []}
        return state
    
    finding_ids = [f.finding_id for f in findings]
    slots = state["slots"]
    section_hints = slots.get("section_hints", {"착안": [], "기법": []})
    free_text = slots.get("free_text", state["user_query"])
    
    retriever = HybridRetriever()
    
    filters = {}
    if slots.get("code"):
        filters["code"] = slots["code"]
    
    # 교집합 문서 필터 추가
    target_doc_ids = state.get("target_doc_ids")
    if target_doc_ids:
        filters["doc_id"] = target_doc_ids
        print(f"[RetrieveChunksBySection] 문서 필터 적용: {len(target_doc_ids)}개 문서로 제한")
    
    query_착안 = " ".join(section_hints.get("착안", [])) + " " + free_text
    query_기법 = " ".join(section_hints.get("기법", [])) + " " + free_text
    
    chunks_착안 = retriever.retrieve_chunks_by_section(
        query=query_착안.strip(),
        section="조사착안",
        finding_ids=finding_ids,
        filters=filters if filters else None,
        top_n=config.chunks_top_k_es
    )
    
    chunks_기법 = retriever.retrieve_chunks_by_section(
        query=query_기법.strip(),
        section="조사기법",
        finding_ids=finding_ids,
        filters=filters if filters else None,
        top_n=config.chunks_top_k_es
    )
    
    state["section_groups"] = {
        "착안": chunks_착안,
        "기법": chunks_기법
    }
    
    all_chunks = chunks_착안 + chunks_기법
    seen = set()
    unique_chunks = []
    for c in all_chunks:
        if c.chunk_id not in seen:
            seen.add(c.chunk_id)
            unique_chunks.append(c)
    
    state["chunks_candidates"] = unique_chunks
    
    print(f"[RetrieveChunksBySection] 착안: {len(chunks_착안)}개, 기법: {len(chunks_기법)}개")
    print(f"  총 unique chunks: {len(unique_chunks)}개")
    
    return state

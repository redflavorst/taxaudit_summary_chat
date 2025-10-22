"""
RetrieveFindings Node: Findings 하이브리드 검색
"""

from ..state import AgentState
from ..retrieval import HybridRetriever
from ..config import config


def retrieve_findings(state: AgentState) -> AgentState:
    """
    RetrieveFindings 노드: Findings 레벨 하이브리드 검색 (ES + Qdrant)
    
    expansion 정보가 있으면 LLM 기반 부스팅 쿼리 사용
    """
    query = state.get("normalized_query", state["user_query"])
    slots = state["slots"]
    expansion = slots.get("expansion")
    
    filters = {}
    if slots.get("code"):
        filters["code"] = slots["code"]
    if slots.get("industry_sub"):
        filters["industry_sub"] = slots["industry_sub"]
    if slots.get("domain_tags"):
        filters["domain_tags"] = slots["domain_tags"]
    
    retriever = HybridRetriever()
    
    findings, target_doc_ids, keyword_freq = retriever.retrieve_findings(
        query=query,
        filters=filters if filters else None,
        expansion=expansion,
        top_n=config.findings_final_top_n
    )
    
    state["findings_candidates"] = findings
    state["target_doc_ids"] = target_doc_ids
    state["keyword_freq"] = keyword_freq
    
    print(f"[RetrieveFindings] 검색된 findings: {len(findings)}개")
    if expansion:
        print(f"[RetrieveFindings] 확장된 쿼리 사용 - must: {expansion.get('must_have', [])}, should: {expansion.get('should_have', [])}")
    for i, f in enumerate(findings[:5], 1):
        print(f"  {i}. {f.finding_id} - {f.item} (score: {f.score_combined:.3f})")
    
    return state

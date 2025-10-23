"""
Route Node: Intent 기반 분기 결정
"""

from ..state import AgentState


CONFIDENCE_THRESHOLD = 0.4  # 신뢰도 임계값


def should_clarify(state: AgentState) -> bool:
    """Clarify 필요 여부 판단"""
    slots = state.get("slots", {})
    confidence = slots.get("confidence", 0.0)
    expansion = slots.get("expansion")
    
    if expansion and expansion.get("must_have"):
        return False
    
    if confidence < CONFIDENCE_THRESHOLD:
        return True
    
    has_any_slot = any([
        slots.get("industry_sub"),
        slots.get("domain_tags"),
        slots.get("actions"),
        slots.get("code")
    ])
    
    if not has_any_slot:
        return True
    
    return False


def route(state: AgentState) -> str:
    """
    Route 노드: Intent에 따라 다음 노드 결정

    Returns:
        "clarify": Clarify 노드로
        "search": RetrieveFindings 노드로
        "explain": ComposeAnswer 노드로 (검색 스킵)
    """
    intent = state.get("intent", "case_lookup")
    slots = state.get("slots", {})
    expansion = slots.get("expansion", {})
    keyword_roles = expansion.get("keyword_roles", {})

    # 우선순위 1: 키워드 역할 확인 필요
    if keyword_roles.get("needs_confirmation"):
        state["needs_clarification"] = True
        print(f"[Route] 키워드 역할 확인 필요 → Clarify")
        return "clarify"

    # 우선순위 2: 일반 명확화
    if should_clarify(state):
        state["needs_clarification"] = True
        print(f"[Route] Clarify 필요 (confidence: {state.get('slots', {}).get('confidence', 0.0):.2f})")
        return "clarify"

    if intent == "case_lookup":
        print(f"[Route] 검색 경로 선택 (intent: {intent})")
        return "search"

    elif intent == "explain":
        print(f"[Route] 설명 경로 선택 (intent: {intent})")
        return "explain"

    else:
        print(f"[Route] 기본 검색 경로 (intent: {intent})")
        return "search"

"""
ValidateOrFallback Node: 결과 검증 및 폴백 처리
"""

from ..state import AgentState


def validate_or_fallback(state: AgentState) -> AgentState:
    """
    ValidateOrFallback 노드: 결과 검증 및 폴백 처리
    """
    if state.get("error"):
        print(f"[ValidateOrFallback] 에러 감지: {state['error']}")
        return state
    
    if not state.get("answer"):
        state["answer"] = "죄송합니다. 답변을 생성할 수 없습니다. 다시 시도해주세요."
        print("[ValidateOrFallback] 답변 없음")
        return state
    
    if not state.get("context", {}).get("citations"):
        print("[ValidateOrFallback] 경고: 인용이 없습니다.")
        state["answer"] += "\n\n(주의: 검색 결과가 부족할 수 있습니다.)"
    
    blocks = state.get("block_ranking", [])
    if len(blocks) == 0:
        print("[ValidateOrFallback] 경고: 검색된 블록이 없습니다.")
        state["answer"] = "관련된 세무조사 사례를 찾을 수 없습니다.\n\n다음을 확인해주세요:\n- 업종, 코드, 키워드를 더 구체적으로 입력\n- 유사한 용어로 재검색"
    
    print(f"[ValidateOrFallback] 검증 완료 (블록: {len(blocks)}개)")
    
    return state

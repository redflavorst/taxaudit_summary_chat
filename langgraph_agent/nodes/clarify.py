"""
Clarify Node: 질의 명확화 1턴 대화
"""

import requests
from ..state import AgentState
from ..config import config


def generate_clarification_question(state: AgentState) -> str:
    """명확화 질문 생성"""
    query = state.get("normalized_query", state["user_query"])
    slots = state.get("slots", {})
    
    missing_info = []
    
    if not slots.get("industry_sub"):
        missing_info.append("업종(제조업, 도소매업 등)")
    
    if not slots.get("domain_tags") and not slots.get("actions"):
        missing_info.append("주제(매출누락, 가공경비, 인건비 등)")
    
    if not slots.get("code"):
        missing_info.append("항목코드(예: 10501, 11209)")
    
    if missing_info:
        return f"질문을 더 구체적으로 해주세요. 다음 정보를 포함해주시면 더 정확한 답변이 가능합니다:\n- " + "\n- ".join(missing_info)
    
    return "질문이 명확하지 않습니다. 다음 중 하나를 선택해주세요:\n1. 특정 세무조사 사례를 찾고 싶으신가요?\n2. 세법 규정 설명을 듣고 싶으신가요?\n3. 조사 기법/절차를 알고 싶으신가요?"


def clarify(state: AgentState) -> AgentState:
    """
    Clarify 노드: 질의 명확화
    
    - confidence가 낮거나 필수 슬롯이 없을 때 실행
    - 사용자에게 추가 정보를 요청하는 질문 생성
    """
    question = generate_clarification_question(state)
    
    state["clarification_question"] = question
    state["needs_clarification"] = True
    
    print(f"[Clarify] 명확화 질문: {question}")
    
    state["answer"] = f"## 추가 정보가 필요합니다\n\n{question}"
    
    return state

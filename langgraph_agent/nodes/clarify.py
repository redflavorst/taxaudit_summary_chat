"""
Clarify Node: 질의 명확화 1턴 대화
"""

import requests
from typing import Dict
from ..state import AgentState
from ..config import config


def generate_keyword_role_confirmation(
    context_keywords: list,
    target_keywords: list,
    confidence: float,
    llm_reasoning: str = ""
) -> str:
    """키워드 역할 확인 질문 생성"""

    question = "🔍 **검색 키워드를 확인해주세요**\n\n"

    if context_keywords:
        question += f"**조사 대상/배경**: {', '.join(context_keywords)}\n"
        question += f"  → 이런 상황/업종의 사례를 검색합니다\n\n"

    if target_keywords:
        question += f"**적출 항목**: {', '.join(target_keywords)}\n"
        question += f"  → 이런 계정/항목을 찾습니다\n\n"

    if llm_reasoning:
        question += f"*분류 근거: {llm_reasoning}*\n\n"

    question += "---\n\n"
    question += "다음 중 선택하세요:\n\n"
    question += "1️⃣ **맞습니다** → 이대로 검색\n"
    question += "2️⃣ **조사 대상과 적출 항목을 바꿔주세요**\n"
    question += "3️⃣ **모두 적출 항목입니다** (OR 검색)\n"
    question += "4️⃣ **직접 수정**\n\n"
    question += "> 번호를 입력하거나, '직접 수정'을 선택하여 수정해주세요.\n"
    question += "> 예: `조사대상=합병법인, 적출항목=미환류소득,대리납부`"

    return question


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
    - 키워드 역할 확인이 필요할 때도 실행
    - 사용자에게 추가 정보를 요청하는 질문 생성
    """
    slots = state.get("slots", {})
    expansion = slots.get("expansion", {})
    keyword_roles = expansion.get("keyword_roles", {})

    # 우선순위 1: 키워드 역할 확인
    if keyword_roles.get("needs_confirmation"):
        question = generate_keyword_role_confirmation(
            context_keywords=keyword_roles.get("context_keywords", []),
            target_keywords=keyword_roles.get("target_keywords", []),
            confidence=keyword_roles.get("confidence", 0.0),
            llm_reasoning=keyword_roles.get("llm_reasoning", "")
        )
    # 우선순위 2: 일반 명확화 질문
    else:
        question = generate_clarification_question(state)

    state["clarification_question"] = question
    state["needs_clarification"] = True

    print(f"[Clarify] 명확화 질문:\n{question}")

    state["answer"] = f"## 추가 정보가 필요합니다\n\n{question}"

    return state

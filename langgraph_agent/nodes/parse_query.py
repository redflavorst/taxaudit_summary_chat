"""
ParseQuery Node: 질의 분석 및 슬롯 추출
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent / "create_db"))

import re
import json
from typing import Dict, List
import requests

from create_db.extract_meta import vocab_loader
from ..state import AgentState, Slots


SECTION_KEYWORDS = {
    "착안": ["착안", "발견", "적발", "확인", "검토", "문제점", "의혹", "혐의"],
    "기법": ["조사기법", "기법", "방법", "절차", "확인방법", "검증", "조사방법", "접근"]
}


def remove_noise_keywords(query: str) -> str:
    """노이즈 키워드 제거 (핵심 검색어만 남김)"""
    noise_keywords = [
        "사례", "사건", "적발", "적출", "조사", "예시", "예제",
        "알려줘", "알려주세요", "찾아줘", "검색", "보여줘", "관련",
        "세무조사", "세무조사시", "조사시", "알아야할", "알아야", "뭐야", "있어"
    ]
    
    cleaned = query
    for noise in noise_keywords:
        cleaned = re.sub(rf'\b{re.escape(noise)}\b', '', cleaned, flags=re.IGNORECASE)
    
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned


def classify_intent(query: str) -> str:
    """
    Intent 분류 (단순화)
    
    모든 질의는 기본적으로 세무조사 사례 검색이 목적.
    단, "설명", "정의" 등 명확한 설명 요청만 구분.
    """
    query_lower = query.lower()
    
    explain_keywords = ["설명해", "뭐야", "무엇인지", "정의", "의미"]
    
    if any(kw in query_lower for kw in explain_keywords):
        return "explain"
    
    return "case_lookup"


def calculate_confidence(slots: Slots) -> float:
    """슬롯 추출 신뢰도 계산"""
    score = 0.0
    
    if slots.get("code"):
        score += 0.3
    
    if slots.get("industry_sub"):
        score += 0.2
    
    if slots.get("domain_tags"):
        score += 0.25
    
    
    if slots.get("section_hints", {}).get("착안") or slots.get("section_hints", {}).get("기법"):
        score += 0.1
    
    return min(score, 1.0)


def extract_slots_rule_based(query: str) -> Slots:
    """규칙 기반 슬롯 추출"""
    slots: Slots = {
        "industry_sub": [],
        "domain_tags": [],
        "code": [],
        "entities": [],
        "section_hints": {"착안": [], "기법": []},
        "free_text": query
    }
    
    code_pattern = r'\b([A-Z]\d{2,4})\b'
    codes = re.findall(code_pattern, query)
    if codes:
        slots["code"] = list(set(codes))
    
    for industry, meta in vocab_loader.industry_vocab.items():
        synonyms = [industry] + meta.get("synonyms", [])
        for syn in synonyms:
            if syn in query:
                slots["industry_sub"].append(industry)
                break
    
    # domain_tags와 actions는 명시적으로 언급된 경우에만 추가
    # (너무 넓은 태그 매칭 방지 - 핵심 키워드가 vocab에 우연히 매칭되는 것 방지)
    
    for section, keywords in SECTION_KEYWORDS.items():
        for kw in keywords:
            if kw in query:
                slots["section_hints"][section].append(kw)
    
    slots["industry_sub"] = list(set(slots["industry_sub"]))
    
    slots["required_terms"] = []
    slots["optional_terms"] = []
    
    all_terms = (slots.get("industry_sub", []) + 
                 slots.get("domain_tags", []) + 
                 slots.get("actions", []))
    slots["required_terms"] = all_terms[:2] if len(all_terms) >= 2 else all_terms
    slots["optional_terms"] = all_terms[2:] if len(all_terms) > 2 else []
    
    slots["confidence"] = calculate_confidence(slots)
    
    return slots


def extract_slots_with_llm(query: str, ollama_url: str, model: str) -> Slots:
    """Ollama를 사용한 LLM 기반 슬롯 추출"""
    prompt = f"""질문에서 명시된 정보만 JSON으로 추출하세요. 추측 금지.

질문: {query}

JSON 형식:
{{
  "industry_sub": [],  // 제조업, 도소매업 등 명시된 업종만
  "domain_tags": [],   // 빈 리스트로 유지
  "code": [],         // 5자리 숫자 코드만 (예: 10501)
  "entities": [],     // 회사명, 인명 등
  "section_hints": {{"착안": [], "기법": []}}  // "조사착안", "조사기법", "방법" 등이 있으면 추가
}}

**중요 규칙**: 
- **domain_tags는 항상 빈 리스트로 유지하세요** (자동 추론 금지)
- 예: "감가상각비 사례" → domain_tags=[]
- code와 industry_sub만 추출하세요
- JSON만 반환하세요."""

    try:
        response = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            },
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            extracted = json.loads(result.get("response", "{}"))
            
            def ensure_list(val):
                if isinstance(val, list):
                    return val
                elif isinstance(val, str):
                    return [val] if val else []
                else:
                    return []
            
            return Slots(
                industry_sub=ensure_list(extracted.get("industry_sub", [])),
                domain_tags=ensure_list(extracted.get("domain_tags", [])),
                code=ensure_list(extracted.get("code", [])),
                entities=ensure_list(extracted.get("entities", [])),
                section_hints=extracted.get("section_hints", {"착안": [], "기법": []}),
                free_text=query
            )
    except Exception as e:
        print(f"LLM 슬롯 추출 실패: {e}")
    
    return extract_slots_rule_based(query)


def parse_query(state: AgentState) -> AgentState:
    """
    ParseQuery 노드: 사용자 질의 분석 및 슬롯 추출
    
    전략: LLM 우선 호출 → vocab 매칭 제약 없이 자유롭게 추출
    """
    query = state.get("normalized_query", state["user_query"])
    
    intent = classify_intent(query)
    state["intent"] = intent
    
    from ..config import config
    slots = extract_slots_with_llm(query, config.ollama_base_url, config.ollama_model)
    
    if not any([slots.get("industry_sub"), slots.get("domain_tags"), slots.get("actions")]):
        slots = extract_slots_rule_based(query)
    
    slots["confidence"] = calculate_confidence(slots)
    slots["free_text"] = query
    
    state["slots"] = slots
    state["needs_clarification"] = False
    
    print(f"[ParseQuery] 질의: {query}")
    print(f"[ParseQuery] Intent: {intent}")
    print(f"[ParseQuery] Confidence: {slots.get('confidence', 0.0):.2f}")
    print(f"[ParseQuery] 추출된 슬롯: {slots}")
    
    return state

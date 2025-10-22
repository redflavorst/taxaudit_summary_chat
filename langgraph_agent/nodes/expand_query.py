"""
Query Expansion Node: LLM 기반 쿼리 확장 및 부스팅 전략 생성
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent / "create_db"))

import json
import requests
from typing import Dict, List
from ..state import AgentState
from create_db.extract_meta import vocab_loader


def build_vocab_prompt() -> str:
    """도메인 사전을 프롬프트 형식으로 변환"""
    vocab_lines = []
    
    vocab_lines.append("세무조사 도메인 용어 사전:")
    vocab_lines.append("")
    
    if vocab_loader.domain_tags_vocab:
        vocab_lines.append("주제 분야:")
        for tag, meta in list(vocab_loader.domain_tags_vocab.items())[:20]:
            synonyms = meta.get("synonyms", [])
            if synonyms:
                vocab_lines.append(f"  - {tag}: {', '.join(synonyms[:5])}")
            else:
                vocab_lines.append(f"  - {tag}")
        vocab_lines.append("")
    
    if vocab_loader.actions_vocab:
        vocab_lines.append("행위 유형:")
        for action, meta in list(vocab_loader.actions_vocab.items())[:10]:
            synonyms = meta.get("synonyms", [])
            if synonyms:
                vocab_lines.append(f"  - {action}: {', '.join(synonyms[:3])}")
            else:
                vocab_lines.append(f"  - {action}")
        vocab_lines.append("")
    
    return "\n".join(vocab_lines)


def expand_query_with_llm(query: str, slots: Dict, ollama_url: str, model: str) -> Dict:
    """
    LLM을 사용하여 쿼리 확장 및 부스팅 전략 생성
    
    Returns:
        {
            "must_have": ["합병법인"],
            "should_have": ["자산", "자산가치"],
            "related_terms": ["인수합병", "M&A", "기업결합", "순자산가액"],
            "boost_weights": {
                "합병법인": 3.0,
                "자산": 1.5,
                "인수합병": 1.2
            }
        }
    """
    vocab_prompt = build_vocab_prompt()
    
    domain_tags = slots.get("domain_tags", [])
    
    prompt = f"""{vocab_prompt}

사용자 질문: {query}

위 도메인 사전을 참고하여 다음을 수행하세요:

1. **핵심 키워드 (must_have)**: 사용자가 명시한 모든 중요 키워드
2. **보조 키워드 (should_have)**: 직접 언급하지 않았지만 관련될 수 있는 키워드 (0-2개, 없어도 됨)
3. **관련 용어 (related_terms)**: 동의어, 유사어, 관련 개념 (3-5개)
4. **부스팅 가중치 (boost_weights)**: 각 키워드의 중요도 점수 (1.0-3.0)

**핵심 원칙**:
1. **must_have = 세무 관련 핵심 명사만**
   - 세무 항목만 추출 (예: 감가상각비, 접대비, 기부금, 미환류소득)
   - 콤마(,) 또는 공백으로 나열된 세무 명사도 모두 포함
   - 예: "감가상각비 관련 적출사례" → ["감가상각비"]  ✅ (적출사례 제외)
   - 예: "접대비, 기부금 사례" → ["접대비", "기부금"]  ✅
   - 예: "합병법인의 미환류소득" → ["합병법인", "미환류소득"]  ✅

2. **should_have = 사용자가 직접 언급하지 않은 보조 키워드** (선택, 비어있어도 됨)
   - 질문에 없지만 관련될 수 있는 세무 개념만

3. **related_terms = 도메인 사전의 동의어/유사어**
   - 도메인 사전에 있는 동의어만 추가

4. **boost_weights**: must_have=3.0, should_have=1.5, related_terms=1.0-1.3

**⚠️ 절대 추가 금지 (검색에 무의미한 일반 용어) ⚠️**:
- 세무조사, 조사, 소득세, 법인세
- **사례, 적출사례, 사건, 적발, 적출, 예시, 케이스**
- 관련, 있어, 찾아줘, 알려줘, 검색
- 이러한 일반 용어가 포함된 복합명사도 제외 (예: "적출사례" ❌)

JSON 형식으로만 응답하세요:
{{
  "must_have": [...],
  "should_have": [...],
  "related_terms": [...],
  "boost_weights": {{...}}
}}"""

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
            expansion = json.loads(result.get("response", "{}"))
            
            if not expansion.get("must_have"):
                expansion["must_have"] = domain_tags[:1] if domain_tags else []
            if not expansion.get("should_have"):
                expansion["should_have"] = domain_tags[1:]
            if not expansion.get("related_terms"):
                expansion["related_terms"] = []
            if not expansion.get("boost_weights"):
                expansion["boost_weights"] = {}
            
            return expansion
    
    except Exception as e:
        print(f"[ExpandQuery] LLM 확장 실패: {e}")
    
    return {
        "must_have": domain_tags[:1] if domain_tags else [],
        "should_have": domain_tags[1:],
        "related_terms": [],
        "boost_weights": {}
    }


def expand_query(state: AgentState) -> AgentState:
    """
    Query Expansion 노드: LLM 기반 쿼리 확장
    
    1. LLM에 도메인 사전 주입
    2. must_have / should_have / related_terms 추출
    3. boost_weights 계산
    4. state["slots"]["expansion"] 필드에 저장
    """
    from ..config import config
    
    query = state.get("normalized_query", state["user_query"])
    slots = state.get("slots", {})
    
    if state.get("intent") != "case_lookup":
        state["slots"]["expansion"] = None
        return state
    
    expansion = expand_query_with_llm(
        query=query,
        slots=slots,
        ollama_url=config.ollama_base_url,
        model=config.ollama_model
    )
    
    state["slots"]["expansion"] = expansion
    
    new_confidence = calculate_expansion_confidence(expansion)
    old_confidence = state["slots"].get("confidence", 0.0)
    state["slots"]["confidence"] = max(old_confidence, new_confidence)
    
    print(f"[ExpandQuery] 원본 질의: {query}")
    print(f"[ExpandQuery] Must-have: {expansion.get('must_have', [])}")
    print(f"[ExpandQuery] Should-have: {expansion.get('should_have', [])}")
    print(f"[ExpandQuery] Related terms: {expansion.get('related_terms', [])}")
    print(f"[ExpandQuery] Boost weights: {expansion.get('boost_weights', {})}")
    print(f"[ExpandQuery] Confidence: {old_confidence:.2f} → {state['slots']['confidence']:.2f}")
    
    return state


def calculate_expansion_confidence(expansion: Dict) -> float:
    """
    쿼리 확장 결과 기반 신뢰도 계산
    
    - must_have 1개: 0.5
    - must_have 2개 이상: 0.7
    - should_have 있음: +0.1
    - related_terms 3개 이상: +0.1
    """
    if not expansion:
        return 0.0
    
    score = 0.0
    
    must_count = len(expansion.get("must_have", []))
    if must_count >= 2:
        score = 0.7
    elif must_count == 1:
        score = 0.5
    
    should_count = len(expansion.get("should_have", []))
    if should_count > 0:
        score += 0.1
    
    related_count = len(expansion.get("related_terms", []))
    if related_count >= 3:
        score += 0.1
    
    return min(score, 1.0)

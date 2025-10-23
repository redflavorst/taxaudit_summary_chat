"""
키워드 역할 분류 모듈 (사전 기반 + LLM)
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "create_db"))

import json
import requests
from typing import List, Dict, Tuple
from create_db.extract_meta import vocab_loader
from .logger import setup_logger

logger = setup_logger(__name__)


def build_vocab_prompt_for_classification() -> str:
    """
    키워드 분류를 위한 사전 프롬프트 생성
    """
    lines = []

    # 조사 대상/배경 사전
    lines.append("## 조사 대상/배경 키워드 (context)")
    lines.append("")

    # context_keywords를 카테고리별로 정리
    by_category = {}
    for keyword, meta in vocab_loader.context_keywords.items():
        category = meta.get("category", "기타")
        if category not in by_category:
            by_category[category] = []

        synonyms = meta.get("synonyms", [])
        if synonyms:
            by_category[category].append(f"{keyword} ({', '.join(synonyms[:3])})")
        else:
            by_category[category].append(keyword)

    for category, keywords in by_category.items():
        lines.append(f"**{category}**:")
        lines.append(", ".join(keywords[:15]))  # 최대 15개만
        lines.append("")

    # 적출 항목 사전
    lines.append("## 적출 항목 키워드 (target)")
    lines.append("")

    # target_keywords를 카테고리별로 정리
    by_category = {}
    for keyword, meta in vocab_loader.target_keywords.items():
        category = meta.get("category", "기타")
        if category not in by_category:
            by_category[category] = []

        synonyms = meta.get("synonyms", [])
        if synonyms:
            by_category[category].append(f"{keyword} ({', '.join(synonyms[:2])})")
        else:
            by_category[category].append(keyword)

    for category, keywords in list(by_category.items())[:10]:  # 상위 10개 카테고리
        lines.append(f"**{category}**:")
        lines.append(", ".join(keywords[:20]))  # 최대 20개만
        lines.append("")

    return "\n".join(lines)


def classify_by_vocab(keywords: List[str]) -> Tuple[List[str], List[str], List[str]]:
    """
    사전 기반 1차 분류 (빠른 룰 베이스)

    Returns:
        (context_keywords, target_keywords, unknown_keywords)
    """
    context_kws = []
    target_kws = []
    unknown_kws = []

    for kw in keywords:
        # 동의어 확인 (대소문자 무시)
        kw_lower = kw.lower()

        # context 사전 확인
        found_in_context = False
        for dict_kw, meta in vocab_loader.context_keywords.items():
            if kw == dict_kw or kw_lower == dict_kw.lower():
                context_kws.append(kw)
                found_in_context = True
                break

            # 동의어 확인
            synonyms = meta.get("synonyms", [])
            if any(kw_lower == syn.lower() for syn in synonyms):
                context_kws.append(kw)
                found_in_context = True
                break

        if found_in_context:
            continue

        # target 사전 확인
        found_in_target = False
        for dict_kw, meta in vocab_loader.target_keywords.items():
            if kw == dict_kw or kw_lower == dict_kw.lower():
                target_kws.append(kw)
                found_in_target = True
                break

            # 동의어 확인
            synonyms = meta.get("synonyms", [])
            if any(kw_lower == syn.lower() for syn in synonyms):
                target_kws.append(kw)
                found_in_target = True
                break

        if found_in_target:
            continue

        # 둘 다 없으면 unknown
        unknown_kws.append(kw)

    logger.info(f"사전 기반 분류: context={context_kws}, target={target_kws}, unknown={unknown_kws}")
    return context_kws, target_kws, unknown_kws


def classify_by_llm(
    query: str,
    keywords: List[str],
    unknown_keywords: List[str],
    ollama_url: str,
    model: str
) -> Dict:
    """
    LLM으로 unknown 키워드 분류
    """
    if not unknown_keywords:
        return {"context_keywords": [], "target_keywords": [], "confidence": 1.0}

    vocab_prompt = build_vocab_prompt_for_classification()

    prompt = f"""당신은 세무조사 전문가입니다. 아래 사전을 참고하여 키워드를 분류하세요.

{vocab_prompt}

---

**사용자 질의**: {query}

**분류할 키워드**: {unknown_keywords}

**분류 규칙**:
1. **조사 대상/배경 (context)**: 업종, 기업 특성, 특수 상황, 거래 유형
   - 검색 범위를 좁히는 역할
   - 예: 합병법인, 제조업, 수출기업, 온라인판매

2. **적출 항목 (target)**: 계정과목, 세무 조정 항목, 특수 거래
   - 실제 찾고자 하는 적출 내용
   - 예: 접대비, 미환류소득, 감가상각비, 대리납부

**판단 기준**:
- 사전에 있으면 해당 카테고리 사용
- 사전에 없으면 질의 문맥과 도메인 지식으로 판단
- 애매하면 더 구체적인 키워드를 target으로 분류
- 일반적/포괄적 키워드는 context

**예시**:
- "합병법인의 미환류소득" → context: [합병법인], target: [미환류소득]
- "플랫폼 접대비" → context: [플랫폼사업], target: [접대비]
- "환율손실" (사전 없음) → target (구체적 계정과목)

JSON만 반환:
{{
  "context_keywords": [...],
  "target_keywords": [...],
  "confidence": 0.0-1.0,
  "reasoning": "분류 이유"
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
            timeout=30
        )

        result = json.loads(response.json().get("response", "{}"))

        logger.info(f"LLM 분류 (unknown): context={result.get('context_keywords')}, target={result.get('target_keywords')}")
        logger.debug(f"LLM 분류 이유: {result.get('reasoning', 'N/A')}")

        return result

    except Exception as e:
        logger.error(f"LLM 분류 실패: {e}")
        # 폴백: unknown은 모두 target으로
        return {
            "context_keywords": [],
            "target_keywords": unknown_keywords,
            "confidence": 0.5,
            "reasoning": "LLM 실패, 기본값 사용"
        }


def classify_keyword_roles(
    query: str,
    keywords: List[str],
    ollama_url: str,
    model: str
) -> Dict:
    """
    하이브리드 키워드 분류 (사전 + LLM)

    Returns:
        {
            "context_keywords": ["합병법인"],
            "target_keywords": ["미환류소득", "대리납부"],
            "confidence": 0.95,
            "method": "vocab" | "llm" | "hybrid",
            "needs_confirmation": False
        }
    """
    # Step 1: 사전 기반 1차 분류
    vocab_context, vocab_target, unknown = classify_by_vocab(keywords)

    # Step 2: unknown이 없으면 사전 결과 반환
    if not unknown:
        return {
            "context_keywords": vocab_context,
            "target_keywords": vocab_target,
            "confidence": 0.95,
            "method": "vocab",
            "needs_confirmation": False
        }

    # Step 3: unknown이 있으면 LLM 분류
    llm_result = classify_by_llm(query, keywords, unknown, ollama_url, model)

    # Step 4: 결과 병합
    final_context = vocab_context + llm_result.get("context_keywords", [])
    final_target = vocab_target + llm_result.get("target_keywords", [])
    llm_confidence = llm_result.get("confidence", 0.5)

    # Step 5: 신뢰도 계산
    vocab_ratio = (len(vocab_context) + len(vocab_target)) / len(keywords)
    final_confidence = vocab_ratio * 0.95 + (1 - vocab_ratio) * llm_confidence

    # Step 6: 확인 필요 여부 판단
    needs_confirmation = False

    if final_confidence < 0.7:
        # 신뢰도 낮음 → 확인 필요
        needs_confirmation = True
        logger.warning(f"신뢰도 낮음 ({final_confidence:.1%}) → 사용자 확인 필요")

    elif len(final_context) == 0 and len(final_target) >= 3:
        # context 없이 target만 3개 이상 → 확인 필요
        needs_confirmation = True
        logger.warning("context 없이 target 3개 이상 → 사용자 확인 필요")

    return {
        "context_keywords": final_context,
        "target_keywords": final_target,
        "confidence": final_confidence,
        "method": "hybrid" if unknown else "vocab",
        "needs_confirmation": needs_confirmation,
        "unknown_keywords": unknown,
        "llm_reasoning": llm_result.get("reasoning", "")
    }

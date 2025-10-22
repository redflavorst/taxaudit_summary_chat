"""
ComposeAnswer Node: Ollama를 사용한 답변 생성
"""

import requests
from ..state import AgentState
from ..config import config


ANSWER_TEMPLATE = """당신은 세무조사 전문가입니다. 아래 컨텍스트를 참고하여 사용자 질문에 답변하세요.

# 사용자 질문
{query}

# 검색된 사례 컨텍스트
{context}

# 답변 지침
1. **중요**: 컨텍스트에 제공된 사례는 모두 질문과 관련된 적출 사례입니다. "관련 없음"이라고 하지 마세요.
2. 적출 블록별로 카드 형식으로 정리
3. 각 블록마다 다음 포함:
   - 코드 (예: 11608)
   - 항목명 (예: 대손준비금환입분 미차감)
   - 조사착안 (어떻게 발견했는지)
   - 조사기법 (어떻게 확인했는지)
   - 사용자 질문과의 연관성 (왜 이 사례가 관련있는지 설명)
4. 근거는 반드시 문서ID와 페이지/라인 번호로 인용
5. 추가 검색 키워드 제안

답변:"""


def compose_answer(state: AgentState) -> AgentState:
    """
    ComposeAnswer 노드: Ollama를 사용한 답변 생성
    """
    context_data = state["context"]
    excluded_blocks = state.get("excluded_blocks", [])
    
    if not context_data["packed_text"]:
        state["answer"] = "검색 결과가 없습니다. 질문을 더 구체적으로 작성해주세요."
        return state
    
    # 검색 전략 메시지 생성
    search_strategy = ""
    slots = state.get("slots", {})
    expansion = slots.get("expansion", {})
    must_keywords = expansion.get("must_have", [])
    keyword_block_counts = state.get("keyword_block_counts", {})
    show_strategy = len(must_keywords) >= 2  # 키워드 2개 이상일 때만 전략 표시
    
    if show_strategy:
        doc_kw = must_keywords[0]
        block_kws = must_keywords[1:]
        
        if len(block_kws) == 1:
            search_strategy = f"\n> 💡 **검색 전략**: '{doc_kw}' 문서 내에서 '{block_kws[0]}' 포함 사례를 검색했습니다.\n"
        else:
            block_kws_str = "' 또는 '".join(block_kws)
            search_strategy = f"\n> 💡 **검색 전략**: '{doc_kw}' 문서 내에서 '{block_kws_str}' 포함 사례를 검색했습니다.\n"
        
        search_strategy += "> 다른 우선순위를 원하시면 질의 순서를 조정해주세요.\n"
        
        # 키워드별 블록 건수 추가
        if keyword_block_counts:
            search_strategy += ">\n"
            search_strategy += "> **검색된 사례 건수**:\n"
            for kw in must_keywords:
                count = keyword_block_counts.get(kw, 0)
                search_strategy += f"> - '{kw}' 관련 적출 사례: **{count}건**\n"
            search_strategy += ">\n"
            search_strategy += "> 특정 키워드로 재질의하시면 해당 사례만 상세히 확인하실 수 있습니다.\n"
    
    prompt = ANSWER_TEMPLATE.format(
        query=state["user_query"],
        context=context_data["packed_text"]
    )
    
    try:
        response = requests.post(
            f"{config.ollama_base_url}/api/generate",
            json={
                "model": config.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": config.ollama_temperature
                }
            },
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            answer = result.get("response", "")
            
            citations_text = "\n\n## 참고 문헌\n"
            seen_findings = set()
            for cite in context_data["citations"]:
                if cite.finding_id not in seen_findings:
                    citations_text += f"- [{cite.doc_id}] {cite.finding_id} (p.{cite.page}, L{cite.start_line}-{cite.end_line})\n"
                    seen_findings.add(cite.finding_id)
            
            # 제외된 블록 정보 추가 (키워드 2개 이상일 때만)
            excluded_info = ""
            if excluded_blocks and show_strategy:
                # 문서별로 그룹화
                excluded_by_doc = {}
                for block in excluded_blocks:
                    doc_id = block.doc_id
                    if doc_id not in excluded_by_doc:
                        excluded_by_doc[doc_id] = []
                    excluded_by_doc[doc_id].append(block)
                
                excluded_info = "\n\n---\n\n### 추가 정보\n\n"
                excluded_info += f"검색된 문서에는 위 사례 외에도 **{len(excluded_blocks)}건의 다른 적출 사례**가 포함되어 있습니다:\n\n"
                
                for doc_id, blocks in list(excluded_by_doc.items())[:2]:  # 최대 2개 문서
                    excluded_info += f"**문서 {doc_id}**:\n"
                    for i, block in enumerate(blocks[:3], 1):  # 문서당 최대 3개
                        excluded_info += f"{i}. {block.item} (코드: {block.code})\n"
                    if len(blocks) > 3:
                        excluded_info += f"... 외 {len(blocks) - 3}건\n"
                    excluded_info += "\n"
                
                excluded_info += "*더 자세한 정보가 필요하시면 구체적인 키워드로 재질의해주세요.*\n"
            
            state["answer"] = search_strategy + answer + citations_text + excluded_info
            print(f"[ComposeAnswer] 답변 생성 완료 ({len(answer)}자)")
        else:
            state["answer"] = f"LLM 응답 실패: {response.status_code}"
            state["error"] = f"Ollama API error: {response.status_code}"
    
    except Exception as e:
        state["answer"] = f"답변 생성 중 오류 발생: {str(e)}"
        state["error"] = str(e)
        print(f"[ComposeAnswer] 오류: {e}")
    
    return state

# LangGraph Studio 설치 및 사용 가이드

## 1. LangGraph Studio 설치

### 방법 1: Desktop 앱 설치 (권장)

```bash
# macOS
brew install --cask langgraph-studio

# Windows/Linux - 다운로드 페이지에서 설치
# https://github.com/langchain-ai/langgraph-studio/releases
```

### 방법 2: Docker 사용

```bash
# Docker 이미지 pull
docker pull langchain/langgraph-studio:latest

# 실행
docker run -p 8123:8123 \
  -v $(pwd):/app \
  langchain/langgraph-studio:latest
```

## 2. 프로젝트 구조 설정

LangGraph Studio가 인식할 수 있도록 프로젝트 구조를 설정해야 합니다.

```
your-project/
├── langgraph.json          # 필수: Studio 설정 파일
├── agent.py                # 그래프 정의 파일
├── requirements.txt        # 의존성
└── .env                    # 환경 변수
```

### langgraph.json 생성

```json
{
  "graphs": {
    "tax_agent": "./agent.py:graph"
  },
  "env": ".env",
  "python_version": "3.11"
}
```

## 3. 그래프 코드 예시

### agent.py 구조

```python
from typing import TypedDict, Optional, List, Dict
from langgraph.graph import StateGraph, END

# State 정의
class AgentState(TypedDict):
    user_query: str
    normalized_query: Optional[str]
    intent: Optional[str]
    slots: dict
    needs_clarification: bool
    clarification_question: Optional[str]
    target_doc_ids: Optional[List[str]]
    keyword_freq: Optional[Dict[str, int]]
    findings_candidates: List[dict]
    section_groups: Dict[str, List[dict]]
    block_ranking: List[dict]
    excluded_blocks: List[dict]
    context: dict
    answer: Optional[str]
    error: Optional[str]
    # 멀티턴 대화를 위한 추가 필드
    conversation_history: List[Dict[str, str]]
    session_id: Optional[str]

# 노드 함수들
def preprocess_node(state: AgentState) -> AgentState:
    """전처리 노드"""
    # 구현...
    return state

def parse_query_node(state: AgentState) -> AgentState:
    """쿼리 파싱 노드"""
    # 구현...
    return state

def expand_query_node(state: AgentState) -> AgentState:
    """쿼리 확장 노드"""
    # 구현...
    return state

def route_decision(state: AgentState) -> str:
    """라우팅 결정"""
    if state.get("needs_clarification"):
        return "clarify"
    elif state.get("intent") == "case_lookup":
        return "search"
    elif state.get("intent") == "explain":
        return "explain"
    else:
        return "search"

def clarify_node(state: AgentState) -> AgentState:
    """재질의 노드"""
    # 구현...
    return state

def retrieve_findings_node(state: AgentState) -> AgentState:
    """Findings 검색 노드"""
    # 구현...
    return state

def retrieve_chunks_node(state: AgentState) -> AgentState:
    """Chunks 검색 노드"""
    # 구현...
    return state

def promote_to_blocks_node(state: AgentState) -> AgentState:
    """블록 승격 노드"""
    # 구현...
    return state

def context_pack_node(state: AgentState) -> AgentState:
    """컨텍스트 패킹 노드"""
    # 구현...
    return state

def compose_answer_node(state: AgentState) -> AgentState:
    """답변 생성 노드"""
    # 구현...
    return state

def validate_node(state: AgentState) -> AgentState:
    """검증 노드"""
    # 구현...
    return state

# 그래프 구축
workflow = StateGraph(AgentState)

# 노드 추가
workflow.add_node("preprocess", preprocess_node)
workflow.add_node("parse_query", parse_query_node)
workflow.add_node("expand_query", expand_query_node)
workflow.add_node("clarify", clarify_node)
workflow.add_node("retrieve_findings", retrieve_findings_node)
workflow.add_node("retrieve_chunks", retrieve_chunks_node)
workflow.add_node("promote_to_blocks", promote_to_blocks_node)
workflow.add_node("context_pack", context_pack_node)
workflow.add_node("compose_answer", compose_answer_node)
workflow.add_node("validate", validate_node)

# 엣지 추가
workflow.set_entry_point("preprocess")
workflow.add_edge("preprocess", "parse_query")
workflow.add_edge("parse_query", "expand_query")

# 조건부 라우팅
workflow.add_conditional_edges(
    "expand_query",
    route_decision,
    {
        "clarify": "clarify",
        "search": "retrieve_findings",
        "explain": "compose_answer"
    }
)

# Clarify 경로
workflow.add_edge("clarify", END)

# Search 경로
workflow.add_edge("retrieve_findings", "retrieve_chunks")
workflow.add_edge("retrieve_chunks", "promote_to_blocks")
workflow.add_edge("promote_to_blocks", "context_pack")
workflow.add_edge("context_pack", "compose_answer")

# 최종 검증
workflow.add_edge("compose_answer", "validate")
workflow.add_edge("validate", END)

# 그래프 컴파일
graph = workflow.compile()
```

## 4. LangGraph Studio 사용법

### 4.1 Studio 실행

```bash
# Desktop 앱 실행 후 프로젝트 폴더 선택
# 또는
cd your-project
langgraph dev
```

Studio가 실행되면 브라우저에서 `http://localhost:8123` 접속

### 4.2 주요 기능

#### A. 그래프 시각화
- 자동으로 노드와 엣지를 시각적으로 표시
- 조건부 라우팅도 표시됨
- 실시간 그래프 구조 확인

#### B. 인터랙티브 디버깅
```python
# Breakpoint 설정
workflow.add_node("retrieve_findings", retrieve_findings_node)
# Studio에서 이 노드에 중단점 설정 가능
```

#### C. State 검사
- 각 노드 실행 후 State 변화 확인
- JSON 형태로 표시
- 히스토리 추적

#### D. 실시간 테스트
```python
# Studio UI에서 입력
{
  "user_query": "합병법인 조사시 미환류소득 관련 사례",
  "conversation_history": []
}
```

### 4.3 멀티턴 대화 테스트

```python
# 첫 번째 쿼리
input1 = {
    "user_query": "합병법인 조사 관련 사례 알려줘",
    "conversation_history": []
}

# Studio에서 실행 후 결과 확인

# 두 번째 쿼리 (후속 질문)
input2 = {
    "user_query": "더 자세히 설명해줘",
    "conversation_history": [
        {"role": "user", "content": "합병법인 조사 관련 사례 알려줘"},
        {"role": "assistant", "content": "...이전 답변..."}
    ]
}
```

## 5. 멀티턴 대화 구현 예시

### 5.1 대화 히스토리 관리

```python
def load_conversation_context(state: AgentState) -> AgentState:
    """이전 대화 컨텍스트 로드"""
    session_id = state.get("session_id")
    if session_id:
        # DB나 캐시에서 이전 대화 로드
        history = load_from_db(session_id)
        state["conversation_history"] = history
    return state

def save_conversation_state(state: AgentState) -> AgentState:
    """대화 상태 저장"""
    session_id = state.get("session_id")
    if session_id:
        save_to_db(session_id, {
            "query": state["user_query"],
            "answer": state["answer"],
            "context": state["context"]
        })
    return state
```

### 5.2 그래프에 추가

```python
# 대화 컨텍스트 로드 노드 추가
workflow.add_node("load_context", load_conversation_context)
workflow.add_node("save_state", save_conversation_state)

# 시작점을 load_context로 변경
workflow.set_entry_point("load_context")
workflow.add_edge("load_context", "preprocess")

# 마지막에 상태 저장
workflow.add_edge("validate", "save_state")
workflow.add_edge("save_state", END)
```

## 6. Studio에서 시각화되는 내용

### 실행 중 표시 정보:
1. **현재 활성 노드** (하이라이트)
2. **실행 경로** (화살표 애니메이션)
3. **State 변화**
   ```json
   {
     "before": { "normalized_query": null },
     "after": { "normalized_query": "합병법인 조사 미환류소득" }
   }
   ```
4. **실행 시간**
5. **에러 위치** (빨간색 표시)

## 7. 유용한 Studio 단축키

- `Cmd/Ctrl + R`: 그래프 재실행
- `Cmd/Ctrl + B`: 중단점 토글
- `Space`: 일시정지/재개
- `→`: 다음 노드로 이동 (step over)
- `Cmd/Ctrl + →`: 끝까지 실행

## 8. 트러블슈팅

### 문제: Studio가 그래프를 인식하지 못함
**해결**:
```python
# agent.py 마지막에 반드시 추가
if __name__ == "__main__":
    # 테스트 코드
    pass

# 그래프 export 확인
__all__ = ["graph"]
```

### 문제: 노드 실행이 느림
**해결**:
- Studio 설정에서 "Auto-run" 비활성화
- 필요한 노드만 중단점 설정

### 문제: State가 너무 큼
**해결**:
```python
# 큰 데이터는 별도 저장소에 저장하고 참조만 State에 보관
class AgentState(TypedDict):
    findings_ref: str  # DB 키
    # findings_candidates: List[dict]  # 이렇게 하지 말 것
```

## 9. 로컬 전용 구성

```bash
# .env 파일
OLLAMA_HOST=http://localhost:11434
ELASTICSEARCH_URL=http://localhost:9200
QDRANT_URL=http://localhost:6333

# 외부 API 사용 안 함
LANGGRAPH_TELEMETRY=false
```

## 10. 추가 시각화 도구 연동

### Streamlit 대시보드 추가
```python
# dashboard.py
import streamlit as st
from agent import graph

st.title("LangGraph Agent Monitor")

if st.button("Run Agent"):
    result = graph.invoke({
        "user_query": st.text_input("Query")
    })
    
    st.json(result)
    
    # 실행 경로 표시
    st.graphviz_chart(generate_execution_graph(result))
```

이제 LangGraph Studio를 사용하여 에이전트를 시각적으로 개발하고 디버깅할 수 있습니다!

# 멀티턴 대화 구현 가이드

## 1. 멀티턴 대화 구현 전략

### 현재 문제점
- 단일 질문에 대한 답변만 가능
- 이전 대화 컨텍스트 미보존
- 재질의 후 후속 처리 불가능

### 해결 방안
1. **대화 히스토리 관리** (State에 저장)
2. **세션 관리** (DB/Redis)
3. **컨텍스트 참조** (이전 답변 활용)
4. **Follow-up 의도 감지** (새로운 라우팅)

## 2. State 확장

```python
from typing import TypedDict, Optional, List, Dict, Literal
from datetime import datetime

class ConversationTurn(TypedDict):
    """대화 턴 정의"""
    timestamp: str
    role: Literal["user", "assistant"]
    content: str
    metadata: Optional[Dict]  # 검색 결과, 블록 정보 등

class AgentState(TypedDict):
    # 기존 필드들
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
    
    # ✨ 멀티턴 대화를 위한 추가 필드
    session_id: str  # 세션 ID
    conversation_history: List[ConversationTurn]  # 대화 히스토리
    previous_context: Optional[Dict]  # 이전 검색 컨텍스트
    is_followup: bool  # 후속 질문 여부
    referenced_turn: Optional[int]  # 참조하는 이전 턴
```

## 3. 노드 추가 및 수정

### 3.1 대화 컨텍스트 로드 노드

```python
import redis
import json
from typing import Optional

class ConversationStore:
    """대화 저장소 (Redis 사용)"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_client = redis.from_url(redis_url)
        self.ttl = 3600 * 24  # 24시간
    
    def save_turn(self, session_id: str, turn: ConversationTurn):
        """대화 턴 저장"""
        key = f"session:{session_id}:history"
        self.redis_client.rpush(key, json.dumps(turn, ensure_ascii=False))
        self.redis_client.expire(key, self.ttl)
    
    def get_history(self, session_id: str) -> List[ConversationTurn]:
        """대화 히스토리 조회"""
        key = f"session:{session_id}:history"
        history = self.redis_client.lrange(key, 0, -1)
        return [json.loads(h) for h in history]
    
    def save_context(self, session_id: str, context: Dict):
        """검색 컨텍스트 저장"""
        key = f"session:{session_id}:context"
        self.redis_client.set(key, json.dumps(context, ensure_ascii=False), ex=self.ttl)
    
    def get_context(self, session_id: str) -> Optional[Dict]:
        """검색 컨텍스트 조회"""
        key = f"session:{session_id}:context"
        context = self.redis_client.get(key)
        return json.loads(context) if context else None

# 저장소 인스턴스
store = ConversationStore()

def load_conversation_context_node(state: AgentState) -> AgentState:
    """대화 컨텍스트 로드 노드"""
    session_id = state.get("session_id")
    
    if not session_id:
        # 새로운 세션 생성
        import uuid
        session_id = str(uuid.uuid4())
        state["session_id"] = session_id
        state["conversation_history"] = []
        state["is_followup"] = False
        return state
    
    # 기존 세션: 히스토리 로드
    history = store.get_history(session_id)
    state["conversation_history"] = history
    
    # 이전 검색 컨텍스트 로드
    previous_context = store.get_context(session_id)
    state["previous_context"] = previous_context
    
    # 후속 질문 여부 판단 (간단한 휴리스틱)
    if history and len(history) > 0:
        state["is_followup"] = True
    
    return state
```

### 3.2 후속 질문 의도 감지

```python
def detect_followup_intent_node(state: AgentState) -> AgentState:
    """후속 질문 의도 감지"""
    
    if not state.get("is_followup"):
        return state
    
    user_query = state["user_query"].lower()
    history = state["conversation_history"]
    
    # 후속 질문 패턴
    followup_patterns = [
        "더", "자세히", "또", "그럼", "그래서", "그러면",
        "이거", "저거", "그거", "위에", "앞에",
        "말한", "설명한", "언급한"
    ]
    
    is_followup_query = any(pattern in user_query for pattern in followup_patterns)
    
    if is_followup_query and len(history) > 0:
        # 마지막 턴 참조
        state["referenced_turn"] = len(history) - 1
        
        # 이전 답변과 연결
        last_turn = history[-1]
        if last_turn["role"] == "assistant":
            state["previous_answer"] = last_turn["content"]
            state["previous_metadata"] = last_turn.get("metadata", {})
    
    return state
```

### 3.3 ParseQuery 수정 (컨텍스트 반영)

```python
def parse_query_with_context_node(state: AgentState) -> AgentState:
    """컨텍스트를 반영한 쿼리 파싱"""
    
    normalized_query = state["normalized_query"]
    
    # 기존 파싱 로직
    intent, slots, confidence = parse_query(normalized_query)
    
    # 후속 질문인 경우 이전 컨텍스트 병합
    if state.get("is_followup") and state.get("previous_context"):
        prev_ctx = state["previous_context"]
        
        # 이전 키워드 재사용
        if "keywords" in prev_ctx:
            slots["inherited_keywords"] = prev_ctx["keywords"]
        
        # 이전 문서 ID 재사용
        if "target_doc_ids" in prev_ctx:
            slots["previous_doc_ids"] = prev_ctx["target_doc_ids"]
        
        # 신뢰도 보정
        confidence = min(confidence + 0.2, 1.0)
    
    state["intent"] = intent
    state["slots"] = slots
    state["slots"]["confidence"] = confidence
    
    return state
```

### 3.4 라우팅 수정

```python
def route_decision_with_followup(state: AgentState) -> str:
    """후속 질문을 고려한 라우팅"""
    
    # Clarification 필요
    if state.get("needs_clarification"):
        return "clarify"
    
    # 후속 질문 처리
    if state.get("is_followup") and state.get("previous_context"):
        # 이전 검색 결과 재사용 가능한지 확인
        if can_reuse_context(state):
            return "reuse_context"
        else:
            return "search"  # 새로운 검색 필요
    
    # 일반 라우팅
    intent = state.get("intent")
    if intent == "case_lookup":
        return "search"
    elif intent == "explain":
        return "explain"
    else:
        return "search"

def can_reuse_context(state: AgentState) -> bool:
    """이전 컨텍스트 재사용 가능 여부"""
    user_query = state["user_query"].lower()
    
    # "더 자세히", "요약해줘" 등은 재사용 가능
    reuse_patterns = ["자세히", "요약", "간단히", "설명"]
    return any(pattern in user_query for pattern in reuse_patterns)
```

### 3.5 이전 컨텍스트 재사용 노드

```python
def reuse_previous_context_node(state: AgentState) -> AgentState:
    """이전 검색 결과 재사용"""
    
    prev_ctx = state.get("previous_context", {})
    
    # 이전 블록 랭킹 재사용
    if "block_ranking" in prev_ctx:
        state["block_ranking"] = prev_ctx["block_ranking"]
    
    # 이전 컨텍스트 재사용
    if "context" in prev_ctx:
        state["context"] = prev_ctx["context"]
    
    # 답변 생성 방식만 변경 (예: 더 자세히, 요약)
    user_query = state["user_query"].lower()
    if "자세히" in user_query:
        state["answer_style"] = "detailed"
    elif "요약" in user_query or "간단히" in user_query:
        state["answer_style"] = "summary"
    
    return state
```

### 3.6 답변 생성 수정 (스타일 반영)

```python
def compose_answer_with_style_node(state: AgentState) -> AgentState:
    """스타일을 반영한 답변 생성"""
    
    context = state["context"]
    answer_style = state.get("answer_style", "default")
    
    # 프롬프트 수정
    if answer_style == "detailed":
        system_prompt = "다음 정보를 바탕으로 매우 상세하게 설명해주세요."
    elif answer_style == "summary":
        system_prompt = "다음 정보를 바탕으로 핵심만 간단하게 요약해주세요."
    else:
        system_prompt = "다음 정보를 바탕으로 답변해주세요."
    
    # 이전 답변 참조
    if state.get("previous_answer"):
        system_prompt += f"\n\n이전 답변: {state['previous_answer'][:200]}..."
    
    # LLM 호출
    answer = generate_answer(system_prompt, context)
    state["answer"] = answer
    
    return state
```

### 3.7 대화 상태 저장 노드

```python
def save_conversation_state_node(state: AgentState) -> AgentState:
    """대화 상태 저장"""
    
    session_id = state["session_id"]
    
    # 사용자 턴 저장
    user_turn: ConversationTurn = {
        "timestamp": datetime.now().isoformat(),
        "role": "user",
        "content": state["user_query"],
        "metadata": None
    }
    store.save_turn(session_id, user_turn)
    
    # 어시스턴트 턴 저장
    assistant_turn: ConversationTurn = {
        "timestamp": datetime.now().isoformat(),
        "role": "assistant",
        "content": state["answer"],
        "metadata": {
            "intent": state.get("intent"),
            "target_doc_ids": state.get("target_doc_ids"),
            "block_count": len(state.get("block_ranking", []))
        }
    }
    store.save_turn(session_id, assistant_turn)
    
    # 검색 컨텍스트 저장 (후속 질문 대비)
    if state.get("block_ranking"):
        search_context = {
            "keywords": state.get("slots", {}).get("expansion", {}).get("must_have", []),
            "target_doc_ids": state.get("target_doc_ids"),
            "block_ranking": state.get("block_ranking"),
            "context": state.get("context")
        }
        store.save_context(session_id, search_context)
    
    return state
```

## 4. 그래프 재구성

```python
from langgraph.graph import StateGraph, END

# 그래프 생성
workflow = StateGraph(AgentState)

# 노드 추가
workflow.add_node("load_context", load_conversation_context_node)
workflow.add_node("detect_followup", detect_followup_intent_node)
workflow.add_node("preprocess", preprocess_node)
workflow.add_node("parse_query", parse_query_with_context_node)
workflow.add_node("expand_query", expand_query_node)
workflow.add_node("clarify", clarify_node)
workflow.add_node("reuse_context", reuse_previous_context_node)
workflow.add_node("retrieve_findings", retrieve_findings_node)
workflow.add_node("retrieve_chunks", retrieve_chunks_node)
workflow.add_node("promote_to_blocks", promote_to_blocks_node)
workflow.add_node("context_pack", context_pack_node)
workflow.add_node("compose_answer", compose_answer_with_style_node)
workflow.add_node("validate", validate_node)
workflow.add_node("save_state", save_conversation_state_node)

# 엣지 연결
workflow.set_entry_point("load_context")
workflow.add_edge("load_context", "detect_followup")
workflow.add_edge("detect_followup", "preprocess")
workflow.add_edge("preprocess", "parse_query")
workflow.add_edge("parse_query", "expand_query")

# 조건부 라우팅
workflow.add_conditional_edges(
    "expand_query",
    route_decision_with_followup,
    {
        "clarify": "clarify",
        "search": "retrieve_findings",
        "explain": "compose_answer",
        "reuse_context": "reuse_context"  # ✨ 새로운 경로
    }
)

# Clarify 경로
workflow.add_edge("clarify", "save_state")

# Reuse 경로
workflow.add_edge("reuse_context", "compose_answer")

# Search 경로
workflow.add_edge("retrieve_findings", "retrieve_chunks")
workflow.add_edge("retrieve_chunks", "promote_to_blocks")
workflow.add_edge("promote_to_blocks", "context_pack")
workflow.add_edge("context_pack", "compose_answer")

# 최종 검증 및 저장
workflow.add_edge("compose_answer", "validate")
workflow.add_edge("validate", "save_state")
workflow.add_edge("save_state", END)

# 컴파일
graph = workflow.compile()
```

## 5. 사용 예시

### 5.1 첫 번째 질문

```python
result1 = graph.invoke({
    "user_query": "합병법인 조사시 미환류소득 관련 사례 알려줘",
    "session_id": None  # 새 세션
})

print(f"세션 ID: {result1['session_id']}")
print(f"답변: {result1['answer']}")
```

### 5.2 후속 질문 (같은 세션)

```python
result2 = graph.invoke({
    "user_query": "더 자세히 설명해줘",
    "session_id": result1["session_id"]  # 같은 세션
})

print(f"답변: {result2['answer']}")
# 이전 검색 결과를 재사용하여 더 자세한 답변 생성
```

### 5.3 새로운 질문 (같은 세션)

```python
result3 = graph.invoke({
    "user_query": "대리납부 관련 사례도 있어?",
    "session_id": result1["session_id"]
})

print(f"답변: {result3['answer']}")
# 새로운 검색 수행, 하지만 이전 컨텍스트 참고
```

## 6. Streamlit UI 구현

```python
import streamlit as st
from agent import graph

st.title("세무 조사 사례 검색 챗봇")

# 세션 상태 초기화
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# 대화 히스토리 표시
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("metadata"):
            with st.expander("검색 정보"):
                st.json(msg["metadata"])

# 사용자 입력
if user_input := st.chat_input("질문을 입력하세요"):
    # 사용자 메시지 추가
    st.session_state.messages.append({
        "role": "user",
        "content": user_input
    })
    
    with st.chat_message("user"):
        st.write(user_input)
    
    # 그래프 실행
    with st.spinner("답변 생성 중..."):
        result = graph.invoke({
            "user_query": user_input,
            "session_id": st.session_state.session_id
        })
    
    # 세션 ID 저장
    if st.session_state.session_id is None:
        st.session_state.session_id = result["session_id"]
    
    # 어시스턴트 메시지 추가
    st.session_state.messages.append({
        "role": "assistant",
        "content": result["answer"],
        "metadata": {
            "intent": result.get("intent"),
            "is_followup": result.get("is_followup"),
            "block_count": len(result.get("block_ranking", []))
        }
    })
    
    with st.chat_message("assistant"):
        st.write(result["answer"])
        with st.expander("검색 정보"):
            st.json(st.session_state.messages[-1]["metadata"])

# 사이드바: 대화 초기화
with st.sidebar:
    if st.button("새 대화 시작"):
        st.session_state.session_id = None
        st.session_state.messages = []
        st.rerun()
```

## 7. 테스트 시나리오

```python
# test_multiturn.py
import pytest
from agent import graph

def test_first_question():
    """첫 번째 질문"""
    result = graph.invoke({
        "user_query": "합병법인 조사 사례",
        "session_id": None
    })
    assert result["answer"] is not None
    assert result["session_id"] is not None
    return result["session_id"]

def test_followup_detail(session_id):
    """후속 질문: 자세히"""
    result = graph.invoke({
        "user_query": "더 자세히 설명해줘",
        "session_id": session_id
    })
    assert result["is_followup"] is True
    assert "detailed" in result.get("answer_style", "")

def test_followup_summary(session_id):
    """후속 질문: 요약"""
    result = graph.invoke({
        "user_query": "간단히 요약해줘",
        "session_id": session_id
    })
    assert result["is_followup"] is True
    assert "summary" in result.get("answer_style", "")

def test_new_question_same_session(session_id):
    """같은 세션에서 새로운 질문"""
    result = graph.invoke({
        "user_query": "대리납부 관련 사례",
        "session_id": session_id
    })
    assert result["session_id"] == session_id
    # 새로운 검색 수행되어야 함
    assert result.get("target_doc_ids") is not None
```

이제 멀티턴 대화가 가능한 LangGraph 에이전트가 완성되었습니다!

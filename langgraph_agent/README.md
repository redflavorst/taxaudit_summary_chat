# LangGraph 기반 세무조사 RAG 에이전트

폐쇄망 환경에서 Ollama + Qdrant + Elasticsearch를 사용한 하이브리드 검색 에이전트

## 아키텍처

```
사용자 질문
    ↓
ParseQuery (슬롯 추출)
    ↓
RetrieveFindings (하이브리드 검색 1단계: ES+Qdrant)
    ↓
RetrieveChunksBySection (하이브리드 검색 2단계: 섹션별)
    ↓
PromoteToBlocks (청크 → 블록 승격, 교집합/블렌딩)
    ↓
ContextPack (컨텍스트 패킹)
    ↓
ComposeAnswer (Ollama 답변 생성)
    ↓
ValidateOrFallback (검증)
    ↓
답변 반환
```

## 설치

```bash
pip install -r requirements.txt
```

## 사용법

### 대화형 모드
```bash
python -m langgraph_agent.main
```

### 단일 질의
```bash
python -m langgraph_agent.main "제조업에서 매출누락 조사기법은?"
```

### Python 코드에서 사용
```python
from langgraph_agent.main import run_query

answer = run_query("제조업에서 매출누락 조사기법은?")
print(answer)
```

## 설정

`langgraph_agent/config.py`에서 설정 변경 가능:

- Ollama URL/모델
- Elasticsearch/Qdrant 연결 정보
- 검색 파라미터 (top-k, RRF-k, 가중치 등)
- 블록 랭킹 설정
- 섹션 가중치 (기본: 5:5)

## 주요 특징

1. **하이브리드 검색**: ES(BM25) + Qdrant(벡터) RRF 결합
2. **섹션별 검색**: 조사착안/조사기법 분리 검색
3. **교집합 우선**: 두 섹션 모두 매칭되는 블록 우선
4. **5:5 블렌딩**: 교집합 부족 시 동등 가중 결합
5. **출처 100% 포함**: 페이지/라인 번호 인용
6. **폐쇄망 지원**: Ollama 로컬 LLM 사용

## 평가

- Hit@K, NDCG@10
- 교집합 사용률
- 응답 시간

## 라이선스

MIT

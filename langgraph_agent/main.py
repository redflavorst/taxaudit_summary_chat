"""
LangGraph Agent 메인 실행 스크립트
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from langgraph_agent.graph import agent_app
from langgraph_agent.state import AgentState


def run_query(query: str) -> str:
    """
    질의 실행
    
    Args:
        query: 사용자 질문
    
    Returns:
        답변 텍스트
    """
    initial_state: AgentState = {
        "user_query": query,
        "normalized_query": None,
        "intent": None,
        "slots": {},
        "needs_clarification": False,
        "clarification_question": None,
        "target_doc_ids": None,
        "keyword_freq": None,
        "keyword_block_counts": None,
        "findings_candidates": [],
        "chunks_candidates": [],
        "section_groups": {"착안": [], "기법": []},
        "block_ranking": [],
        "excluded_blocks": [],
        "context": {"packed_text": "", "citations": []},
        "answer": None,
        "error": None
    }
    
    print(f"\n{'='*70}")
    print(f"질문: {query}")
    print(f"{'='*70}\n")
    
    result = agent_app.invoke(initial_state)
    
    answer = result.get("answer", "답변을 생성할 수 없습니다.")
    
    print(f"\n{'='*70}")
    print(f"답변:")
    print(f"{'='*70}")
    print(answer)
    print(f"{'='*70}\n")
    
    return answer


def interactive_mode():
    """대화형 모드"""
    print("=" * 70)
    print("세무조사 챗봇 에이전트 (LangGraph + Ollama + Qdrant + ES)")
    print("=" * 70)
    print("종료하려면 'exit' 또는 'quit'을 입력하세요.\n")
    
    while True:
        try:
            query = input("질문> ").strip()
            
            if not query:
                continue
            
            if query.lower() in ["exit", "quit", "종료"]:
                print("종료합니다.")
                break
            
            run_query(query)
        
        except KeyboardInterrupt:
            print("\n\n종료합니다.")
            break
        except Exception as e:
            print(f"\n오류 발생: {e}\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        run_query(query)
    else:
        interactive_mode()

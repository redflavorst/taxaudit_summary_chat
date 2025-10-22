"""
LangGraph 에이전트 그래프 정의
"""

from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import (
    preprocess,
    parse_query,
    expand_query,
    route,
    clarify,
    retrieve_findings,
    retrieve_chunks_by_section,
    promote_to_blocks,
    context_pack,
    compose_answer,
    validate_or_fallback
)


def route_decision(state: AgentState) -> str:
    """Route 결과에 따라 다음 노드 결정"""
    return route(state)


def create_agent_graph():
    """LangGraph 에이전트 생성"""
    
    graph = StateGraph(AgentState)
    
    graph.add_node("preprocess", preprocess)
    graph.add_node("parse_query", parse_query)
    graph.add_node("expand_query", expand_query)
    graph.add_node("clarify", clarify)
    graph.add_node("retrieve_findings", retrieve_findings)
    graph.add_node("retrieve_chunks", retrieve_chunks_by_section)
    graph.add_node("promote_blocks", promote_to_blocks)
    graph.add_node("context_pack", context_pack)
    graph.add_node("compose_answer", compose_answer)
    graph.add_node("validate", validate_or_fallback)
    
    graph.set_entry_point("preprocess")
    
    graph.add_edge("preprocess", "parse_query")
    graph.add_edge("parse_query", "expand_query")
    
    graph.add_conditional_edges(
        "expand_query",
        route_decision,
        {
            "clarify": "clarify",
            "search": "retrieve_findings",
            "explain": "compose_answer"
        }
    )
    
    graph.add_edge("clarify", END)
    
    graph.add_edge("retrieve_findings", "retrieve_chunks")
    graph.add_edge("retrieve_chunks", "promote_blocks")
    graph.add_edge("promote_blocks", "context_pack")
    graph.add_edge("context_pack", "compose_answer")
    graph.add_edge("compose_answer", "validate")
    graph.add_edge("validate", END)
    
    return graph.compile()


agent_app = create_agent_graph()

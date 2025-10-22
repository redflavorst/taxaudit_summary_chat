"""
ContextPack Node: 컨텍스트 패킹 및 인용 생성
"""

from typing import List
from ..state import AgentState, Citation, ChunkHit, ContextData
from ..config import config


SECTION_ORDER = {
    "조사기법": 1,
    "과세논리": 2,
    "증빙 및 리스크": 3,
    "조사착안": 4
}


def merge_adjacent_chunks(chunks: List[ChunkHit]) -> List[ChunkHit]:
    """인접 청크 병합"""
    if not config.context_merge_adjacent or len(chunks) <= 1:
        return chunks
    
    merged = []
    current = chunks[0]
    
    for next_chunk in chunks[1:]:
        if (current.finding_id == next_chunk.finding_id and
            current.section == next_chunk.section and
            current.chunk_order + 1 == next_chunk.chunk_order):
            current.text += "\n" + next_chunk.text
            current.end_line = next_chunk.end_line
        else:
            merged.append(current)
            current = next_chunk
    
    merged.append(current)
    return merged


def context_pack(state: AgentState) -> AgentState:
    """
    ContextPack 노드: 컨텍스트 패킹 및 인용 생성
    """
    blocks = state["block_ranking"]
    
    if not blocks:
        print("[ContextPack] 블록이 없어 스킵")
        state["context"] = ContextData(packed_text="", citations=[])
        return state
    
    packed_parts = []
    citations = []
    token_count = 0
    
    for block_idx, block in enumerate(blocks, 1):
        if token_count >= config.context_token_budget:
            break
        
        block_header = f"\n## 적출 블록 {block_idx}\n"
        block_header += f"- 문서: {block.doc_id}\n"
        block_header += f"- 적출ID: {block.finding_id}\n"
        block_header += f"- 항목: {block.item}\n"
        block_header += f"- 코드: {block.code}\n"
        block_header += f"- 섹션: {', '.join(block.source_sections)}\n\n"
        
        packed_parts.append(block_header)
        token_count += len(block_header) // 4
        
        chunks_by_section = {}
        for c in block.chunks:
            if c.section not in chunks_by_section:
                chunks_by_section[c.section] = []
            chunks_by_section[c.section].append(c)
        
        for section in sorted(chunks_by_section.keys(), key=lambda s: SECTION_ORDER.get(s, 99)):
            section_chunks = chunks_by_section[section]
            section_chunks = sorted(section_chunks, key=lambda c: (c.section_order, c.chunk_order))
            
            selected_chunks = section_chunks[:config.context_chunks_per_block]
            merged_chunks = merge_adjacent_chunks(selected_chunks)
            
            section_text = f"### {section}\n"
            packed_parts.append(section_text)
            token_count += len(section_text) // 4
            
            for chunk in merged_chunks:
                chunk_text = f"{chunk.text}\n"
                chunk_text += f"(출처: p.{chunk.page}, L{chunk.start_line}-{chunk.end_line})\n\n"
                
                packed_parts.append(chunk_text)
                token_count += len(chunk_text) // 4
                
                citations.append(Citation(
                    doc_id=chunk.doc_id,
                    finding_id=chunk.finding_id,
                    chunk_id=chunk.chunk_id,
                    page=chunk.page,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    text=chunk.text,
                    section=chunk.section
                ))
                
                if token_count >= config.context_token_budget:
                    break
            
            if token_count >= config.context_token_budget:
                break
    
    packed_text = "".join(packed_parts)
    
    state["context"] = ContextData(
        packed_text=packed_text,
        citations=citations
    )
    
    print(f"[ContextPack] 컨텍스트 생성: {len(packed_text)}자, 인용: {len(citations)}개")
    
    return state

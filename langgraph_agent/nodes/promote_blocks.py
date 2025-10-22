"""
PromoteToBlocks Node: 청크를 적출블록으로 승격 및 랭킹
"""

from collections import defaultdict
from typing import List, Dict
from ..state import AgentState, ChunkHit, RankedBlock
from ..config import config


def calculate_chunk_score(chunk: ChunkHit) -> float:
    """청크 점수 계산: α*BM25 + β*Vector + γ*Field"""
    return (
        config.alpha_bm25 * chunk.score_bm25 +
        config.beta_vector * chunk.score_vector +
        config.gamma_field * chunk.score_field
    )


def dedup_by_section(chunks: List[ChunkHit]) -> List[ChunkHit]:
    """섹션 중복 제거: 같은 섹션은 1개만 유지"""
    seen_sections = set()
    result = []
    for chunk in sorted(chunks, key=lambda c: c.score_combined, reverse=True):
        if chunk.section not in seen_sections:
            seen_sections.add(chunk.section)
            result.append(chunk)
    return result


def block_score_from_chunks(chunks: List[ChunkHit], top_k: int = 3) -> float:
    """블록 점수 계산: 섹션 중복 제거 후 상위 k개 평균"""
    if not chunks:
        return 0.0
    
    deduped = dedup_by_section(chunks)
    top_chunks = sorted(deduped, key=lambda c: c.score_combined, reverse=True)[:top_k]
    
    if not top_chunks:
        return 0.0
    
    return sum(c.score_combined for c in top_chunks) / len(top_chunks)


def determine_block_level_keywords(keywords: List[str]) -> tuple[str, List[str]]:
    """
    위치 기반으로 블록 레벨 필수 키워드 결정
    
    전략:
    - 첫 번째 키워드 = 문서 레벨 컨텍스트 (예: "합병법인")
    - 나머지 키워드 = 블록 레벨 필수 (OR 관계) (예: ["미환류소득", "대리납부"])
    
    자연스러운 질의 구조:
    - "합병법인의 접대비 적출사례" → 합병법인(문서) + 접대비(블록)
    - "합병법인의 미환류소득, 대리납부 사례" → 합병법인(문서) + 미환류소득 OR 대리납부(블록)
    
    Args:
        keywords: 검색 키워드 리스트 (must_have)
    
    Returns:
        (doc_level_keyword, block_level_keywords)
    """
    if not keywords:
        return None, []
    
    if len(keywords) == 1:
        # 단일 키워드는 블록 필수
        return None, keywords
    
    # 첫 번째 = 문서 레벨, 나머지 = 블록 레벨 (OR)
    doc_level_kw = keywords[0]
    block_level_kws = keywords[1:]
    
    return doc_level_kw, block_level_kws


def promote_to_blocks(state: AgentState) -> AgentState:
    """
    PromoteToBlocks 노드: 청크를 적출블록으로 승격 및 랭킹
    - 섹션 교집합 우선
    - 교집합 부족 시 5:5 블렌딩
    - 블록 레벨 키워드 필터링 추가
    """
    section_groups = state["section_groups"]
    chunks_착안 = section_groups.get("착안", [])
    chunks_기법 = section_groups.get("기법", [])
    
    # 사용자 질의의 핵심 키워드 (필터링용)
    slots = state.get("slots", {})
    expansion = slots.get("expansion", {})
    must_keywords = expansion.get("must_have", [])
    
    if not chunks_착안 and not chunks_기법:
        print("[PromoteToBlocks] 청크가 없어 스킵")
        state["block_ranking"] = []
        return state
    
    grp_착안 = defaultdict(list)
    for c in chunks_착안:
        grp_착안[c.finding_id].append(c)
    
    grp_기법 = defaultdict(list)
    for c in chunks_기법:
        grp_기법[c.finding_id].append(c)
    
    I = set(grp_착안.keys()) & set(grp_기법.keys())
    
    ranked = []
    
    if len(I) >= config.block_intersection_min:
        print(f"[PromoteToBlocks] 교집합 우선 (교집합 크기: {len(I)})")
        for fid in I:
            combined_chunks = grp_착안[fid] + grp_기법[fid]
            score = block_score_from_chunks(combined_chunks, top_k=config.block_top_k_chunks)
            ranked.append((fid, score, combined_chunks))
    else:
        print(f"[PromoteToBlocks] 합집합 5:5 블렌딩 (교집합 크기: {len(I)})")
        U = set(grp_착안.keys()) | set(grp_기법.keys())
        for fid in U:
            s_착안 = block_score_from_chunks(grp_착안.get(fid, []), top_k=config.block_top_k_chunks)
            s_기법 = block_score_from_chunks(grp_기법.get(fid, []), top_k=config.block_top_k_chunks)
            
            score = config.weight_section_착안 * s_착안 + config.weight_section_기법 * s_기법
            
            combined_chunks = grp_착안.get(fid, []) + grp_기법.get(fid, [])
            ranked.append((fid, score, combined_chunks))
    
    ranked.sort(key=lambda x: x[1], reverse=True)
    
    # 키워드 전략 결정: 위치 기반
    doc_level_kw = None
    block_level_keywords = []
    enable_filtering = False  # 키워드 필터링 활성화 여부
    
    if must_keywords:
        doc_level_kw, block_level_keywords = determine_block_level_keywords(must_keywords)
        
        # 키워드 2개 이상일 때만 필터링 활성화
        enable_filtering = len(must_keywords) >= 2
        
        print(f"[PromoteToBlocks] 키워드 전략 (위치 기반):")
        if len(must_keywords) == 1:
            print(f"  - 단일 키워드: '{must_keywords[0]}' (필터링 없음)")
        else:
            if doc_level_kw:
                print(f"  - 문서 컨텍스트: '{doc_level_kw}'")
            if block_level_keywords:
                print(f"  - 블록 필수 (OR): {block_level_keywords}")
    
    # 블록 레벨 키워드 필터링
    doc_counts = defaultdict(int)
    final_blocks = []
    excluded_blocks = []
    
    # 키워드별 블록 매칭 건수 추적
    keyword_block_counts = {kw: 0 for kw in must_keywords} if must_keywords else {}
    
    for fid, score, chunks in ranked:
        if not chunks:
            continue
        
        doc_id = chunks[0].doc_id
        sections = list(set(c.section for c in chunks))
        
        # 디버깅: 청크 수 확인
        print(f"  [블록 생성] {fid}: {len(chunks)}개 청크")
        
        block = RankedBlock(
            finding_id=fid,
            doc_id=doc_id,
            item=chunks[0].item,
            code=chunks[0].code,
            score=score,
            chunks=sorted(chunks, key=lambda c: c.score_combined, reverse=True),
            source_sections=sections
        )
        
        # 키워드 필터링: must_have 키워드 매칭 확인
        block_text = " ".join([c.text for c in chunks])
        matched_keywords = []
        
        if must_keywords:
            for kw in must_keywords:
                if kw in block_text:
                    matched_keywords.append(kw)
                    # 키워드별 블록 매칭 건수 증가
                    keyword_block_counts[kw] += 1
        
        # 전략: 위치 기반 키워드 필터링 (키워드 2개 이상일 때만)
        if not enable_filtering:
            # 키워드 1개 또는 없음: 필터링 없이 모든 블록 포함
            if doc_counts[doc_id] >= config.max_blocks_per_doc:
                continue
            
            doc_counts[doc_id] += 1
            final_blocks.append(block)
            
            if len(final_blocks) >= config.block_final_top_n:
                break
        else:
            # 키워드 2개 이상: 필터링 활성화
            # - 첫 번째 키워드(문서 레벨) = 문서 교집합에서 이미 확인됨, 블록에 없어도 OK
            # - 나머지 키워드(블록 레벨) = 블록에 최소 1개 이상 있어야 함 (OR 관계)
            if block_level_keywords:
                # 블록 필수 키워드 중 최소 1개 매칭되면 완전매칭
                matched_block_kws = [kw for kw in block_level_keywords if kw in matched_keywords]
                is_full_match = len(matched_block_kws) > 0
                is_partial_match = doc_level_kw in matched_keywords if doc_level_kw else False
            else:
                is_full_match = True
                is_partial_match = False
            
            # 디버깅 로그
            match_status = "완전매칭" if is_full_match else ("부분매칭" if is_partial_match else "불일치")
            matched_block_kws = [kw for kw in block_level_keywords if kw in matched_keywords]
            print(f"    [필터링] {fid}: 블록필수={block_level_keywords}, 매칭={matched_block_kws} ({match_status})")
            
            if is_full_match:
                # 완전 매칭: 메인 답변에 포함
                if doc_counts[doc_id] >= config.max_blocks_per_doc:
                    excluded_blocks.append(block)
                    continue
                
                doc_counts[doc_id] += 1
                final_blocks.append(block)
                
                if len(final_blocks) >= config.block_final_top_n:
                    break
            elif is_partial_match:
                # 부분 매칭: 제외 블록에 포함 (추가 정보로 제공)
                print(f"      → 부분매칭으로 제외 (필요: {must_keywords}, 매칭: {matched_keywords})")
                excluded_blocks.append(block)
            else:
                # 불일치: 제외
                excluded_blocks.append(block)
    
    state["block_ranking"] = final_blocks
    state["excluded_blocks"] = excluded_blocks
    state["keyword_block_counts"] = keyword_block_counts
    
    print(f"[PromoteToBlocks] 최종 블록: {len(final_blocks)}개 (제외: {len(excluded_blocks)}개)")
    for i, block in enumerate(final_blocks, 1):
        print(f"  {i}. {block.finding_id} - {block.item} (score: {block.score:.3f}, chunks: {len(block.chunks)})")
    
    if keyword_block_counts:
        print(f"[PromoteToBlocks] 키워드별 블록 매칭 건수:")
        for kw, count in keyword_block_counts.items():
            print(f"  - '{kw}': {count}건")
    
    if excluded_blocks and must_keywords:
        print(f"[PromoteToBlocks] 제외된 블록 (키워드 불일치):")
        for i, block in enumerate(excluded_blocks[:5], 1):
            print(f"  {i}. {block.finding_id} - {block.item}")
    
    return state

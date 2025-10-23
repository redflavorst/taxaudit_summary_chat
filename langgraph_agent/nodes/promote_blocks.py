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


def get_block_filter_keywords(expansion: Dict) -> tuple[List[str], List[str]]:
    """
    역할 기반 블록 필터링 키워드 추출

    전략:
    - context_keywords: 문서 레벨 (이미 retrieval.py에서 필터링됨)
    - target_keywords: 블록 레벨 필터링 (OR 관계)

    Args:
        expansion: 쿼리 확장 결과

    Returns:
        (context_keywords, target_keywords)
    """
    keyword_roles = expansion.get("keyword_roles", {})

    context_kws = keyword_roles.get("context_keywords", [])
    target_kws = keyword_roles.get("target_keywords", [])

    # Fallback: 역할 분류 실패 시 must_have를 모두 target으로 사용
    if not context_kws and not target_kws:
        must_have = expansion.get("must_have", [])
        target_kws = must_have

    return context_kws, target_kws


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
    
    # 역할 기반 키워드 추출
    slots = state.get("slots", {})
    expansion = slots.get("expansion", {})
    context_keywords, target_keywords = get_block_filter_keywords(expansion)

    # 모든 키워드 (로깅 및 카운팅용)
    all_keywords = context_keywords + target_keywords

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

    # 블록 필터링 활성화 여부: target_keywords가 있을 때만
    enable_filtering = len(target_keywords) > 0

    print(f"[PromoteToBlocks] 키워드 전략 (역할 기반):")
    if context_keywords:
        print(f"  - 조사 대상/배경 (문서 레벨): {context_keywords}")
    if target_keywords:
        print(f"  - 적출 항목 (블록 필터링, OR): {target_keywords}")
        print(f"  - 블록 필터링 활성화: {enable_filtering}")
    else:
        print(f"  - 블록 필터링 없음 (target_keywords 없음)")
    
    # 블록 레벨 키워드 필터링
    doc_counts = defaultdict(int)
    final_blocks = []
    excluded_blocks = []

    # 키워드별 블록 매칭 건수 추적 (모든 키워드 포함)
    keyword_block_counts = {kw: 0 for kw in all_keywords} if all_keywords else {}
    
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
        
        # 키워드 매칭 확인 (all_keywords)
        block_text = " ".join([c.text for c in chunks])
        matched_keywords = []

        if all_keywords:
            for kw in all_keywords:
                if kw in block_text:
                    matched_keywords.append(kw)
                    # 키워드별 블록 매칭 건수 증가
                    keyword_block_counts[kw] += 1
        
        # 전략: 역할 기반 블록 필터링
        if not enable_filtering:
            # target_keywords 없음: 필터링 없이 모든 블록 포함
            if doc_counts[doc_id] >= config.max_blocks_per_doc:
                continue

            doc_counts[doc_id] += 1
            final_blocks.append(block)

            if len(final_blocks) >= config.block_final_top_n:
                break
        else:
            # target_keywords 있음: 블록에 최소 1개 이상 target 매칭 필요 (OR 관계)
            matched_target_kws = [kw for kw in target_keywords if kw in matched_keywords]
            is_full_match = len(matched_target_kws) > 0

            # 디버깅 로그
            match_status = "완전매칭" if is_full_match else "불일치"
            print(f"    [필터링] {fid}: target필수={target_keywords}, 매칭={matched_target_kws} ({match_status})")

            if is_full_match:
                # 완전 매칭: 메인 답변에 포함
                if doc_counts[doc_id] >= config.max_blocks_per_doc:
                    excluded_blocks.append(block)
                    continue

                doc_counts[doc_id] += 1
                final_blocks.append(block)

                if len(final_blocks) >= config.block_final_top_n:
                    break
            else:
                # 불일치: 제외 블록에 포함
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

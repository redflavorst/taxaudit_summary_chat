from typing import Dict, List
import json
import re
from datetime import datetime

MIN_CHUNK_TOKENS = 400
MAX_CHUNK_TOKENS = 800
OVERLAP_RATIO = 0.12
MIN_OVERLAP_TOKENS = 50
EXTRACTION_VERSION = "v0.5.0"


def _extract_text_by_lines(md_content: str, start_line: int, end_line: int) -> str:
    """Extract substring between the given (1-based) line numbers."""
    lines = md_content.split("\n")
    return "\n".join(lines[start_line - 1 : end_line])


def _token_count(text: str) -> int:
    """Very rough token estimator based on whitespace segmentation."""
    return len(text.split())


def _normalize_segments(paragraphs: List[str]) -> List[str]:
    """Flatten paragraphs into manageable segments, splitting very long ones."""
    segments: List[str] = []
    for para in paragraphs:
        cleaned = para.strip()
        if not cleaned:
            continue

        tokens = _token_count(cleaned)
        if tokens <= MAX_CHUNK_TOKENS:
            segments.append(cleaned)
            continue

        words = cleaned.split()
        step = MAX_CHUNK_TOKENS
        for i in range(0, len(words), step):
            segment = " ".join(words[i : i + step])
            segments.append(segment)
    return segments


def _slice_with_overlap(paragraphs: List[str]) -> List[str]:
    """Split a list of paragraphs into balanced chunks with overlap."""
    segments = _normalize_segments(paragraphs)
    if not segments:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_tokens = 0
    has_fresh_content = False

    def finalize() -> None:
        nonlocal current, current_tokens, has_fresh_content
        if not current or not has_fresh_content:
            return

        chunk_text = "\n\n".join(current).strip()
        if not chunk_text:
            current = []
            current_tokens = 0
            has_fresh_content = False
            return

        chunks.append(chunk_text)

        overlap_target = max(int(current_tokens * OVERLAP_RATIO), MIN_OVERLAP_TOKENS)
        tail: List[str] = []
        tail_tokens = 0
        for seg in reversed(current):
            tail.insert(0, seg)
            tail_tokens += _token_count(seg)
            if tail_tokens >= overlap_target:
                break

        current = tail.copy()
        current_tokens = sum(_token_count(seg) for seg in current)
        has_fresh_content = False

    for seg in segments:
        seg_tokens = _token_count(seg)
        if current and current_tokens + seg_tokens > MAX_CHUNK_TOKENS and current_tokens >= MIN_CHUNK_TOKENS:
            finalize()

        current.append(seg)
        current_tokens += seg_tokens
        has_fresh_content = True

        if current_tokens >= MAX_CHUNK_TOKENS:
            finalize()

    if has_fresh_content:
        finalize()

    return chunks or []


def _normalize_item(item: str | None) -> str | None:
    if not item:
        return None
    normalized = re.sub(r"^\s*\d+[\.\)]\s*", "", item).strip()
    return normalized or item.strip()


def _normalize_text(text: str) -> str:
    """
    검색용 텍스트 정규화:
    - 페이지 표식 제거 (- N -)
    - 마크다운 헤더 제거 (####)
    - 다중 공백 정규화
    - 불필요한 특수문자 제거
    """
    text = re.sub(r'-\s*\d+\s*-', '', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[\u200b-\u200f\ufeff]', '', text)
    return text.strip()


def make_chunks_for_finding(finding: Dict, md_content: str) -> List[Dict]:
    """
    Slice finding sections from the original markdown using section_spans and build chunk payloads.
    Falls back to the full finding span when section info is missing.
    """
    chunks: List[Dict] = []

    section_spans = finding.get("section_spans", [])
    if isinstance(section_spans, str):
        try:
            section_spans = json.loads(section_spans)
        except json.JSONDecodeError:
            section_spans = []

    normalized_item = _normalize_item(finding.get("item"))
    finding_code = finding.get("code")

    def append_chunk(
        section_order: int,
        chunk_order: int,
        section_name: str,
        text: str,
        start_line: int,
        end_line: int,
    ) -> None:
        chunk_id = f'{finding["finding_id"]}@{section_order:02d}-{chunk_order:02d}'
        meta = (
            f'[META] doc:{finding["doc_id"]} | finding:{finding["finding_id"]} | '
            f'code:{finding_code or ""} | item:{normalized_item or finding.get("item", "")} | section:{section_name}'
        )
        text_raw = text.strip()
        text_norm = _normalize_text(text_raw)
        
        chunks.append(
            dict(
                chunk_id=chunk_id,
                finding_id=finding["finding_id"],
                doc_id=finding["doc_id"],
                section=section_name,
                section_order=section_order,
                chunk_order=chunk_order,
                code=finding_code,
                item=finding.get("item"),
                item_norm=normalized_item,
                page=None,
                start_line=start_line,
                end_line=end_line,
                text=text_raw,
                text_norm=text_norm,
                text_raw=text_raw,
                meta_line=meta,
                extraction_version=EXTRACTION_VERSION,
                created_at=datetime.utcnow().isoformat() + "Z",
            )
        )

    for section_order, section_info in enumerate(section_spans):
        section_name = section_info["name"]
        start_line = section_info["start_line"]
        end_line = section_info["end_line"]
        section_text = _extract_text_by_lines(md_content, start_line, end_line)
        paragraphs = [p for p in section_text.split("\n\n") if p.strip()]

        if not paragraphs:
            continue

        sliced = _slice_with_overlap(paragraphs)
        for chunk_order, text in enumerate(sliced):
            append_chunk(section_order, chunk_order, section_name, text, start_line, end_line)

    if not chunks and finding.get("start_line") and finding.get("end_line"):
        full_text = _extract_text_by_lines(md_content, finding["start_line"], finding["end_line"])
        append_chunk(
            section_order=0,
            chunk_order=0,
            section_name="전체",
            text=full_text,
            start_line=finding["start_line"],
            end_line=finding["end_line"],
        )

    return chunks

# ==============================
# pdf_layout/exporter.py
# ==============================
from typing import Dict, List, Any
import json
import os
import re
from collections import defaultdict

from .utils import BBox

TYPE_TITLES = {
    "red_box": "Red Region",
    "blue_table": "Table",
    "yellow_table": "Special Table",
    "law_table": "Law Table",
    "purple_text": "Text Block",
}

TABLE_TYPES = {"yellow_table"}  # law_table은 제외 (placeholder로 처리)


def export_json(pages: Dict[int, List[dict]], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # Convert page index to page_N keys with sorted by y0
    payload: dict[str, list] = {}
    for pno, items in pages.items():
        items_sorted = sorted(items, key=lambda x: (x.get("y0", 0.0), x["bbox"][0]))
        payload[f"page_{pno}"] = items_sorted

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _format_law_table(raw_text: str) -> str:
    """Format law table as markdown table.
    
    Args:
        raw_text: Raw text containing law title and content
    
    Returns:
        Markdown table with '법령' and '내용' columns
    """
    lines = raw_text.strip().split('\n')
    if not lines:
        return raw_text
    
    # Remove '법령' header if present
    if lines[0].strip() == "법령":
        lines = lines[1:]
    
    if not lines:
        return raw_text
    
    # First line is the law title
    title = lines[0].strip()
    # Rest is content
    content = '\n'.join(lines[1:]).strip()
    
    if not title:
        return raw_text
    
    # Create 2-column table
    table_lines = [
        "| 법령 | 내용 |",
        "|------|------|",
        f"| {title} | {content} |"
    ]
    
    return '\n'.join(table_lines)


def _format_markdown_table(raw_text: str, doc_id: str = None) -> str:
    raw_lines = raw_text.splitlines()
    rows: List[List[str]] = []
    for line in raw_lines:
        cells = [c.strip() for c in re.split(r"\s{2,}|\t", line) if c.strip()]
        if not cells:
            if line.strip():
                cells = [line.strip()]
            else:
                continue
        rows.append(cells)

    if not rows:
        return raw_text.strip()

    def _format_extraction(rows: List[List[str]]) -> str:
        if not rows or not rows[0]:
            return ""
        header_cell = rows[0][0]
        if "적출" not in header_cell:
            return ""
        # 항상 "적출"로 통일 (번호 제거)
        base_label = '적출'

        content_rows: List[str] = []
        for row in rows[1:]:
            left = row[0].strip() if len(row) > 0 else ""
            right = row[1].strip() if len(row) > 1 else ""
            
            # 왼쪽 셀이 순수 숫자만 있는 경우 건너뛰기
            if left and not left.isdigit():
                clean_left = left
                if clean_left.lower().startswith('v'):
                    clean_left = clean_left[1:].strip()
                if not clean_left.startswith('❖'):
                    clean_left = f"{clean_left}"
                content_rows.append(clean_left)
                
            # 오른쪽 셀 처리
            if right:
                # 왼쪽 셀이 숫자여서 건너뛴 경우, right만 추가
                if left.isdigit() or not left:
                    content_rows.append(right)
                elif content_rows:
                    content_rows[-1] = content_rows[-1] + ' ' + right
        if not content_rows:
            return ""
        body = "<br>".join(content_rows)
        return "\n".join([
            "| | |",
            "|---|---|",
            f"| {base_label} | {body} |",
        ])

    extraction = _format_extraction(rows)
    if extraction:
        return extraction

    if all(len(r) == 1 for r in rows):
        flat = [r[0] for r in rows if r[0]]
        length = len(flat)

        roman_pattern = re.compile(r"^[\u2460-\u2473]+$")
        code_pattern = re.compile(r"^\d{3,6}$")
        roman_positions = [idx for idx, token in enumerate(flat) if roman_pattern.match(token)]

        if roman_positions:
            header_tokens = flat[:roman_positions[0]]
            data_tokens = flat[roman_positions[0]:]

            default_header = ["연번", "조사항목", "코드", "적출요지(결정/경정 사유)"]
            header = default_header
            if len(header_tokens) >= 4:
                header = header_tokens[:4]

            rows_data: List[List[str]] = []
            i = 0
            while i < len(data_tokens):
                token = data_tokens[i]
                if not roman_pattern.match(token):
                    i += 1
                    continue
                label = token
                i += 1

                second_parts: List[str] = []
                while i < len(data_tokens) and not code_pattern.match(data_tokens[i]) and not roman_pattern.match(data_tokens[i]):
                    second_parts.append(data_tokens[i])
                    i += 1

                code = ""
                if i < len(data_tokens) and code_pattern.match(data_tokens[i]):
                    code = data_tokens[i]
                    i += 1

                fourth_parts: List[str] = []
                while i < len(data_tokens) and not roman_pattern.match(data_tokens[i]):
                    fourth_parts.append(data_tokens[i])
                    i += 1

                rows_data.append([
                    label,
                    " ".join(second_parts).strip(),
                    code,
                    " ".join(fourth_parts).strip(),
                ])

            if rows_data:
                lines = [
                    "| " + " | ".join(header) + " |",
                    "| " + " | ".join(["---"] * len(header)) + " |",
                ]
                
                # 주요적출내역 테이블인지 확인
                is_main_taxing = False
                if len(header) >= 4:
                    h0 = header[0].strip() if len(header) > 0 else ""
                    h1 = header[1].strip() if len(header) > 1 else ""
                    h2 = header[2].strip() if len(header) > 2 else ""
                    if h0 == "연번" and h1 == "조사항목" and h2 == "코드":
                        is_main_taxing = True
                
                row_counter = 1
                for row in rows_data:
                    row_line = "| " + " | ".join(row) + " |"
                    # 주요적출내역 테이블이고 doc_id가 있고, 조사항목(2번째 컬럼)에 내용이 있으면 row_id 추가
                    if is_main_taxing and doc_id and len(row) > 1 and row[1].strip():
                        row_line += f" <!-- row_id: {doc_id}#R{row_counter} -->"
                        row_counter += 1
                    lines.append(row_line)
                return "\n".join(lines)

        best_cols = None
        best_layout: List[List[str]] = []
        best_score = -1
        for cols in range(2, min(12, length) + 1):
            if length % cols != 0:
                continue
            total_rows = length // cols
            if total_rows < 2:
                continue
            layout = [flat[i * cols:(i + 1) * cols] for i in range(total_rows)]
            header = layout[0]
            data_cells = sum(layout[1:], [])
            header_score = sum(1 for cell in header if not re.search(r"\d{2,}", cell))
            data_score = sum(1 for cell in data_cells if re.search(r"\d", cell))
            score = total_rows * cols + header_score + data_score
            if score > best_score:
                best_score = score
                best_cols = cols
                best_layout = layout
        if best_cols:
            rows = best_layout
        else:
            return raw_text.strip()

    num_cols = max(len(r) for r in rows)
    padded = [r + [""] * (num_cols - len(r)) for r in rows]
    header = padded[0]
    body = padded[1:] if len(padded) > 1 else []

    # 주요적출내역 테이블인지 확인 (연번, 조사항목, 코드 헤더 포함)
    is_main_taxing = False
    
    # 헤더가 4개 컬럼이고 첫 3개가 연번, 조사항목, 코드를 포함하는지 확인
    if len(header) >= 4:
        # 공백 제거하고 비교
        h0 = header[0].strip() if len(header) > 0 else ""
        h1 = header[1].strip() if len(header) > 1 else ""
        h2 = header[2].strip() if len(header) > 2 else ""
        
        if h0 == "연번" and h1 == "조사항목" and h2 == "코드":
            is_main_taxing = True
    
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * num_cols) + " |",
    ]
    
    row_counter = 1
    for row in body:
        row_line = "| " + " | ".join(row) + " |"
        # 주요적출내역 테이블이고 doc_id가 있고, 조사항목(2번째 컬럼)에 내용이 있으면 row_id 추가
        if is_main_taxing and doc_id and len(row) > 1 and row[1].strip():
            row_line += f" <!-- row_id: {doc_id}#R{row_counter} -->"
            row_counter += 1
        # 디버그
        # elif is_main_taxing and not doc_id:
        #     print(f"DEBUG: Main taxing table found but no doc_id provided")
        lines.append(row_line)
    return "\n".join(lines)


def _extract_major_items(all_items: List[dict], doc_id: str = None) -> List[tuple]:
    """주요적출내역 테이블에서 조사항목과 코드를 추출"""
    major_items = []
    
    for i, item in enumerate(all_items):
        text = (item.get("content") or "").strip()
        
        # 테이블 타입이고 마크다운 테이블로 변환
        if item.get("type") in TABLE_TYPES:
            table_text = _format_markdown_table(text, doc_id)
            lines = table_text.split('\n')
            
            # 헤더에 "연번", "조사항목", "코드"가 포함된 테이블 찾기
            if len(lines) > 0:
                header = lines[0]
                if "연번" in header and "조사항목" in header and "코드" in header:
                    # 주요적출내역 테이블 발견
                    for line in lines[2:]:  # 헤더와 구분선 제외
                        if '|' in line and '---' not in line:
                            cells = [cell.strip() for cell in line.split('|')]
                            # 보통 3번째 셀이 조사항목, 4번째 셀이 코드 (0: 빈칸, 1: 연번, 2: 조사항목, 3: 코드)
                            if len(cells) >= 5:  # 최소 5개 셀 (빈칸, 연번, 조사항목, 코드, 적출요지)
                                item_name = cells[2].strip()
                                code = cells[3].strip()
                                # 조사항목이 있고 유효한지 확인
                                if item_name and not item_name.isdigit() and len(item_name) > 1 and item_name != "조사항목":
                                    # 특수문자 제거
                                    for char in ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩']:
                                        item_name = item_name.replace(char, '').strip()
                                    if item_name:
                                        major_items.append((item_name, code))
                    if major_items:  # 찾았으면 중단
                        break
    
    return major_items


def _extract_doc_id(filename: str) -> str:
    """파일명에서 doc_id 추출
    예: 2025(s)-1-(24)_layout -> 2025S-001-24
    """
    import re
    
    # 파일명에서 확장자와 _layout 제거
    base_name = os.path.basename(filename)
    base_name = base_name.replace('_layout', '').replace('.md', '')
    
    # 패턴 매칭: 연도(s/h)-숫자-(숫자)
    pattern = r'(\d{4})\(([sh])\)-(\d+)-\((\d+)\)'
    match = re.match(pattern, base_name)
    
    if match:
        year = match.group(1)
        semester = 'S' if match.group(2) == 's' else 'H'
        middle_num = match.group(3).zfill(3)  # 3자리로 패딩
        last_num = match.group(4)
        
        return f"{year}{semester}-{middle_num}-{last_num}"
    
    # 매칭 실패시 파일명 그대로 반환
    return base_name

def export_markdown(pages: Dict[int, List[dict]], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    lines: List[str] = []
    
    # doc_id를 frontmatter로 추가
    doc_id = _extract_doc_id(out_path)
    lines.append("---")
    lines.append(f'doc_id: "{doc_id}"')
    lines.append("---")
    lines.append("")
    
    # law_table 카운터 (전체 문서에서 순차적으로 번호 부여)
    law_table_counter = 0
    
    # 모든 아이템을 먼저 수집
    all_items = []
    for pno in sorted(pages.keys()):
        items = sorted(pages[pno], key=lambda x: (x.get("y0", 0.0), x["bbox"][0]))
        for item in items:
            # law_table은 content가 없어도 추가
            if item.get("type") == "law_table":
                all_items.append(item)
            else:
                text = (item.get("content") or "").strip()
                if text:
                    all_items.append(item)
    
    # 주요적출내역 테이블에서 조사항목 추출
    major_items = _extract_major_items(all_items, doc_id)
    
    # 조사노하우 섹션 여부와 적출테이블 카운터
    in_josa_tip = False
    josa_jeokchul_count = 0
    
    # 텍스트 병합을 위한 버퍼
    text_buffer = []
    
    def _is_list_item(text: str) -> bool:
        """리스트 아이템인지 확인"""
        list_markers = ['-', '•', '○', '◦', '▪', '▫', '※', '◎', '●', '◆', '◇', '■', '□', '▲', '△', '▶', '▷', '*']
        return any(text.startswith(marker) for marker in list_markers)
    
    def _is_caption(text: str) -> bool:
        """캡션(이미지 설명 등)인지 확인"""
        return text.startswith('<') and '>' in text
    
    def _flush_buffer(lines: List[str], buffer: List[str]) -> None:
        """버퍼에 있는 텍스트를 합쳐서 lines에 추가"""
        if buffer:
            merged_text = ' '.join(buffer)
            lines.append(merged_text)
            lines.append("")
            buffer.clear()
    
    i = 0
    while i < len(all_items):
        item = all_items[i]
        text = (item.get("content") or "").strip()
        
        # 로마 숫자와 제목 처리 (더 일반적인 방식)
        roman_nums = ["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ"]
        
        # 첫 번째 글자가 로마 숫자이고 다음 줄을 확인
        if text in roman_nums and i + 1 < len(all_items):
            next_text = (all_items[i + 1].get("content") or "").strip()
            
            # Ⅰ + 조사성과(결과)
            if text == "Ⅰ" and ("조사성과" in next_text or "결과" in next_text):
                _flush_buffer(lines, text_buffer)
                lines.append("## Ⅰ.조사성과(결과)")
                lines.append("")
                in_josa_tip = False
                i += 2
                continue
            # Ⅱ + 조사노하우
            elif text == "Ⅱ" and "조사노하우" in next_text:
                _flush_buffer(lines, text_buffer)
                lines.append("## Ⅱ.조사노하우")
                lines.append("")
                in_josa_tip = True
                josa_jeokchul_count = 0
                i += 2
                continue
        
        # 합쳐진 경우 처리
        elif "Ⅰ" in text and ("조사성과" in text or "결과" in text):
            _flush_buffer(lines, text_buffer)
            lines.append("## Ⅰ.조사성과(결과)")
            lines.append("")
            in_josa_tip = False
            i += 1
            continue
        elif "Ⅱ" in text and "조사노하우" in text:
            _flush_buffer(lines, text_buffer)
            lines.append("## Ⅱ.조사노하우")
            lines.append("")
            in_josa_tip = True
            josa_jeokchul_count = 0
            i += 1
            continue
        
        # 가. 조사대상개요가 합쳐진 경우
        elif "가. 조사대상개요" in text or "가.조사대상개요" in text or text == "가. 조사대상개요":
            _flush_buffer(lines, text_buffer)
            lines.append("### 가. 조사대상개요")
            lines.append("")
            i += 1
            continue
        
        # 가 다음에 조사대상개요가 오는 경우 (분리된 경우)
        elif text in ["가", "가."] and i + 1 < len(all_items):
            next_text = (all_items[i + 1].get("content") or "").strip()
            if "조사대상개요" in next_text:
                _flush_buffer(lines, text_buffer)
                lines.append("### 가. 조사대상개요")
                lines.append("")
                i += 2
                continue
        
        # 나. 적출성과가 합쳐진 경우
        elif "나. 적출성과" in text or "나.적출성과" in text or text == "나. 적출성과":
            _flush_buffer(lines, text_buffer)
            lines.append("### 나. 적출성과")
            lines.append("")
            i += 1
            continue
        
        # 나 다음에 적출성과가 오는 경우 (분리된 경우)
        elif text in ["나", "나."] and i + 1 < len(all_items):
            next_text = (all_items[i + 1].get("content") or "").strip()
            if "적출성과" in next_text:
                _flush_buffer(lines, text_buffer)
                lines.append("### 나. 적출성과")
                lines.append("")
                i += 2
                continue
        
        # 조사노하우 섹션에서 적출테이블 처리
        if in_josa_tip and item.get("type") in TABLE_TYPES:
            _flush_buffer(lines, text_buffer)  # 테이블 전에 버퍼 비우기
            table_content = _format_markdown_table(text, doc_id)
            # 적출테이블인지 확인
            if "| 적출 |" in table_content:
                # 주요적출내역이 있으면 헤더 추가
                if josa_jeokchul_count < len(major_items):
                    item_name, code = major_items[josa_jeokchul_count]
                    finding_id = f"{doc_id}#F{code}#F{josa_jeokchul_count + 1}"
                    lines.append(f"### 적출 {josa_jeokchul_count + 1}. {item_name} <!-- finding_id: {finding_id} -->")
                    lines.append("")
                    josa_jeokchul_count += 1
                lines.append(table_content)
            else:
                lines.append(table_content)
            lines.append("")
        # 헤더가 아닌 일반 콘텐츠 처리
        elif item.get("type") == "law_table":
            _flush_buffer(lines, text_buffer)  # 테이블 전에 버퍼 비우기
            law_table_counter += 1
            # JSON에 law_id 추가 (나중에 DB에서 참조)
            item["law_id"] = law_table_counter
            # Markdown에는 placeholder만 추가
            lines.append(f"[law_table#{law_table_counter}]")
            lines.append("")
        elif item.get("type") in TABLE_TYPES:
            _flush_buffer(lines, text_buffer)  # 테이블 전에 버퍼 비우기
            lines.append(_format_markdown_table(text, doc_id))
            lines.append("")
        else:
            # 조사착안, 조사기법 헤더 처리
            if text.startswith("1. 조사착안") or text.startswith("1.조사착안"):
                _flush_buffer(lines, text_buffer)  # 헤더 전에 버퍼 비우기
                lines.append("#### 1. 조사착안")
                lines.append("")
            elif text.startswith("2. 조사기법") or text.startswith("2.조사기법"):
                _flush_buffer(lines, text_buffer)  # 헤더 전에 버퍼 비우기
                lines.append("#### 2. 조사기법")
                lines.append("")
            # 캡션(이미지 설명)인 경우
            elif _is_caption(text):
                _flush_buffer(lines, text_buffer)  # 캡션 전에 버퍼 비우기
                lines.append(text)
                lines.append("")
            # 리스트 아이템인 경우
            elif _is_list_item(text):
                # 버퍼에 내용이 있으면 먼저 처리
                _flush_buffer(lines, text_buffer)
                
                # 문장이 완료되었는지 확인
                if text.endswith(('.', '!', '?', '임', '음', '함')):
                    lines.append(text)
                    lines.append("")
                else:
                    # 문장이 완료되지 않았으면 버퍼에 추가
                    text_buffer.append(text)
            # 일반 텍스트인 경우
            else:
                # 버퍼가 있으면 계속 합치기
                if text_buffer:
                    text_buffer.append(text)
                    # 문장이 끝났으면 플러시
                    if text.endswith(('.', '!', '?', '임', '음', '함')):
                        _flush_buffer(lines, text_buffer)
                else:
                    # 버퍼가 없는 경우
                    if text.endswith(('.', '!', '?', '임', '음', '함')):
                        lines.append(text)
                        lines.append("")
                    else:
                        text_buffer.append(text)
        i += 1
    
    # 마지막에 버퍼 비우기
    _flush_buffer(lines, text_buffer)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
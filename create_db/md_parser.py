# create_db/md_parser.py
import re
from typing import Dict, List, Tuple
import json
from extract_meta import extract_reason_kw_norm

ROW_RE = re.compile(r"\<\!\-\-\s*row_id:\s*([^\s]+)\s*\-\-\>")
FINDING_RE = re.compile(r"\<\!\-\-\s*finding_id:\s*([^\s]+)\s*\-\-\>")
CODE_IN_HEADER_RE = re.compile(r"코드\s*[:：]?\s*(\d{5})")
CODE_INLINE_RE = re.compile(r"\b(\d{5})\b")

def parse_doc_id(md: str) -> str:
    m = re.search(r'doc_id:\s*"([^"]+)"', md)
    if m: return m.group(1)
    raise ValueError("doc_id not found in frontmatter")

def get_line_number(text: str, position: int) -> int:
    """텍스트 내 위치에서 라인 번호 계산 (1-based)"""
    return text[:position].count('\n') + 1

def parse_overview_content(md: str) -> str:
    """
    조사대상개요 부터 적출성과 전까지의 내용 추출
    - 시작: "가.", "나.", "1.", "2." 등 + "조사대상개요" 또는 "조사법인업황"
    - 끝: 아무 위치의 "적출성과" 또는 다음 섹션
    - 헤더 레벨(###) 있거나 없음
    - 모든 단어 사이 띄어쓰기 허용
    """
    # 패턴 1: ### [가-하]/[1-9]. 조사대상개요/조사법인업황 (헤더 레벨 있음)
    pattern1 = r'###\s*(?:[가-하]|\d)\.\s*(?:조사\s*대상\s*개요|조사\s*법인\s*업황)(.*?)(?=###\s*[가-하]\.\s*적출\s*성과|###\s*\d\.\s*적출\s*성과|$)'
    match = re.search(pattern1, md, re.DOTALL | re.IGNORECASE)
    
    if match:
        content = match.group(1).strip()
        return content
    
    # 패턴 2: [가-하]/[1-9]. 조사대상개요/조사법인업황 (헤더 레벨 없음)
    pattern2 = r'(?:[가-하]|\d)\.\s*(?:조사\s*대상\s*개요|조사\s*법인\s*업황)(.*?)(?=###\s*[가-하]\.\s*적출\s*성과|[가-하]\.\s*적출\s*성과|###\s*\d\.\s*적출\s*성과|\d\.\s*적출\s*성과|$)'
    match = re.search(pattern2, md, re.DOTALL | re.IGNORECASE)
    
    if match:
        content = match.group(1).strip()
        return content
    
    return None

def parse_overview_table(md: str) -> Dict:
    """
    조사대상개요 테이블 파싱
    | 개인·법인 | 업종(코드) | 조사유형 | 외형구간 | 조사청 |
    또는 텍스트 형식:
    개인·법인
    업종(코드)
    ...
    """
    overview_data = {
        "entity_type": None,
        "industry_name": None,
        "industry_code": None,
        "audit_type": None,
        "revenue_bracket": None,
        "audit_office": None,
        "overview_raw": None,
        "overview_content": None
    }
    
    overview_section = md.split("## 적출")[0] if "## 적출" in md else ""
    if not overview_section:
        overview_section = md.split("## Ⅰ.조사성과")[0] if "## Ⅰ.조사성과" in md else md[:3000]
    
    lines = overview_section.split('\n')
    
    # 패턴 1: 테이블 형식
    for i, line in enumerate(lines):
        if '개인·법인' in line or '개인법인' in line:
            if i + 2 < len(lines) and '|' in lines[i + 2]:
                data_line = lines[i + 2]
                cols = [c.strip() for c in data_line.strip('|').split('|')]
                
                if len(cols) >= 5:
                    overview_data["entity_type"] = cols[0] if cols[0] else None
                    
                    industry_col = cols[1]
                    code_match = re.search(r'\((\d+)\)', industry_col)
                    if code_match:
                        overview_data["industry_code"] = code_match.group(1)
                        overview_data["industry_name"] = industry_col.split('(')[0].strip()
                    elif re.match(r'^\d+$', industry_col.strip()):
                        overview_data["industry_code"] = industry_col.strip()
                    else:
                        overview_data["industry_name"] = industry_col.strip()
                    
                    overview_data["audit_type"] = cols[2] if cols[2] else None
                    overview_data["revenue_bracket"] = cols[3] if cols[3] else None
                    overview_data["audit_office"] = cols[4] if cols[4] else None
                    overview_data["overview_raw"] = data_line.strip()
                break
    
    # 패턴 2: 텍스트 형식 (테이블로 추출 안 된 경우)
    if not overview_data["entity_type"]:
        for i, line in enumerate(lines):
            if '개인·법인' in line:
                # 다음 5줄 읽기
                if i + 5 < len(lines):
                    header_line = line
                    if '업종(코드)' in lines[i+1] and '조사유형' in lines[i+2]:
                        # 헤더 다음 데이터 찾기
                        data_start = i + 5
                        if data_start < len(lines):
                            entity = lines[data_start].strip()
                            industry_line = lines[data_start+1].strip() if data_start+1 < len(lines) else ""
                            industry_code_line = lines[data_start+2].strip() if data_start+2 < len(lines) else ""
                            audit_type = lines[data_start+3].strip() if data_start+3 < len(lines) else ""
                            revenue = lines[data_start+4].strip() if data_start+4 < len(lines) else ""
                            office = lines[data_start+5].strip() if data_start+5 < len(lines) else ""
                            
                            overview_data["entity_type"] = entity if entity else None
                            overview_data["industry_name"] = industry_line if industry_line else None
                            
                            # 업종코드 추출
                            code_match = re.search(r'\((\d+)\)', industry_code_line)
                            if code_match:
                                overview_data["industry_code"] = code_match.group(1)
                            
                            overview_data["audit_type"] = audit_type if audit_type else None
                            overview_data["revenue_bracket"] = revenue if revenue else None
                            overview_data["audit_office"] = office if office else None
                            overview_data["overview_raw"] = f"{entity}|{industry_line}|{audit_type}|{revenue}|{office}"
                        break
    
    overview_data["overview_content"] = parse_overview_content(md)
    
    return overview_data

def parse_table_rows(md: str, doc_id: str):
    rows = []
    for m in ROW_RE.finditer(md):
        row_id = m.group(1)
        line_number = get_line_number(md, m.start())
        
        # row_id가 있는 라인을 찾음
        line_start = md.rfind("\n", 0, m.start()) + 1
        line_end = md.find("\n", m.end())
        if line_end == -1:
            line_end = len(md)
        current_line = md[line_start:line_end]
        
        # 현재 라인에서 테이블 데이터 추출 (row_id 주석 제거)
        table_line = current_line.split("<!--")[0].strip()
        
        if "|" in table_line:
            cols = [c.strip() for c in table_line.strip("|").split("|")]
            row_no, item, code, reason = None, None, None, None
            
            if len(cols) >= 4:
                try:
                    row_no_str = cols[0].replace("①","1").replace("②","2").replace("③","3").replace("④","4").strip()
                    row_no = int(row_no_str) if row_no_str.isdigit() else None
                except: 
                    pass
                    
                item = cols[1] if len(cols) > 1 else ""
                code = re.search(r"\d{5}", cols[2]).group(0) if len(cols) > 2 and re.search(r"\d{5}", cols[2]) else None
                reason = cols[3] if len(cols) > 3 else ""
                
                rows.append(dict(
                    row_id=row_id, doc_id=doc_id, row_no=row_no,
                    item=item, code=code, reason_kw_raw=reason, 
                    line_number=line_number
                ))
    return rows

def parse_sections(md: str, finding_start_pos: int, finding_end_pos: int) -> Tuple[List[str], List[Dict]]:
    """
    finding 블록 내의 섹션들을 파싱
    Returns: (sections_present, section_spans)
    """
    sections_present = []
    section_spans = []
    
    # finding 블록 추출
    block = md[finding_start_pos:finding_end_pos]
    
    # 섹션 헤더 패턴들
    section_patterns = [
        (r"####?\s*\d+\.\s*조사착안", "조사착안"),
        (r"####?\s*\d+\.\s*조사기법", "조사기법"),
        (r"####?\s*조사착안", "조사착안"),
        (r"####?\s*조사기법", "조사기법"),
        #(r"####?\s*과세논리", "과세논리"),
        #(r"####?\s*증빙.*리스크", "증빙·리스크")
    ]
    
    # 모든 섹션 매치를 찾아서 위치별로 정렬
    all_sections = []
    for pattern, section_name in section_patterns:
        for match in re.finditer(pattern, block, re.IGNORECASE):
            all_sections.append({
                "name": section_name,
                "start": match.start(),
                "start_line": get_line_number(md, finding_start_pos + match.start())
            })
    
    # 위치순으로 정렬
    all_sections.sort(key=lambda x: x["start"])
    
    # 각 섹션의 end_line 계산 (다음 섹션 시작 직전 또는 finding 끝)
    for i, section in enumerate(all_sections):
        sections_present.append(section["name"])
        
        # 끝 라인 계산: 다음 섹션 시작 직전 또는 finding 끝
        if i + 1 < len(all_sections):
            # 다음 섹션 시작 직전
            end_line = all_sections[i + 1]["start_line"] - 1
        else:
            # finding 끝
            end_line = get_line_number(md, finding_end_pos) - 1
        
        section_spans.append({
            "name": section["name"],
            "start_line": section["start_line"],
            "end_line": end_line
        })
    
    # 중복 제거 (같은 섹션이 여러 번 매치된 경우)
    seen = set()
    unique_spans = []
    unique_present = []
    for span in section_spans:
        if span["name"] not in seen:
            seen.add(span["name"])
            unique_spans.append(span)
            unique_present.append(span["name"])
    
    return unique_present, unique_spans

def parse_finding_table(md: str, finding_start_pos: int, first_section_pos: int) -> str:
    """
    적출 헤더와 첫 번째 섹션(보통 조사착안) 사이에 있는 테이블에서 item_detail 추출
    """
    # 적출 헤더부터 첫 섹션까지의 텍스트
    block = md[finding_start_pos:first_section_pos]
    
    # 테이블 찾기 (| 적출 | ... | 형식)
    table_lines = [line for line in block.split('\n') if '|' in line and '적출' in line]
    
    if table_lines:
        for line in table_lines:
            # 테이블 행 파싱
            cols = [col.strip() for col in line.split('|')]
            # "적출" 컬럼 다음의 내용 찾기
            for i, col in enumerate(cols):
                if '적출' in col and i + 1 < len(cols):
                    detail = cols[i + 1]
                    # <br> 태그를 줄바꿈으로 변환
                    detail = detail.replace('<br>', '\n')
                    # HTML 태그 제거 (간단한 처리)
                    detail = re.sub(r'<[^>]+>', '', detail)
                    return detail.strip()
    
    return None

def parse_findings(md: str, doc_id: str):
    findings = []
    lines = md.split('\n')
    
    all_matches = list(FINDING_RE.finditer(md))
    
    for i, m in enumerate(all_matches):
        finding_id = m.group(1)
        
        # finding의 시작 라인
        start_line = get_line_number(md, m.start())
        
        # finding_id 주석이 있는 줄 찾기
        line_start = md.rfind("\n", 0, m.start()) + 1
        line_end = md.find("\n", m.end())
        if line_end == -1:
            line_end = len(md)
        header_line = md[line_start:line_end]
        
        # 헤더에서 제목 추출 (주석 제거)
        item = header_line.split("<!--")[0].strip()
        if "적출" in item:
            item = item.split("적출", 1)[-1].strip()
        item = item.strip("#").strip()
        
        # finding 블록의 끝 찾기 (다음 finding 또는 문서 끝)
        if i + 1 < len(all_matches):
            end_pos = all_matches[i + 1].start()
            # 다음 finding 헤더의 시작 라인 직전까지만 포함
            end_line = get_line_number(md, end_pos) - 1
        else:
            end_pos = len(md)
            end_line = get_line_number(md, end_pos)
        
        # 블록 내에서 코드 찾기
        block = md[m.start():end_pos]
        mcode = CODE_IN_HEADER_RE.search(block) or CODE_INLINE_RE.search(block)
        code = mcode.group(1) if mcode else None
        
        # 섹션 파싱
        sections_present, section_spans = parse_sections(md, m.start(), end_pos)
        
        # item_detail 추출 (적출 헤더와 첫 섹션 사이의 테이블에서)
        item_detail = None
        if section_spans:
            # 첫 섹션의 시작 위치 찾기
            first_section_line = section_spans[0]["start_line"]
            # 라인 번호를 position으로 변환
            first_section_pos = 0
            for line_num, line in enumerate(md.split('\n'), 1):
                if line_num == first_section_line:
                    break
                first_section_pos += len(line) + 1  # +1 for newline
            
            item_detail = parse_finding_table(md, m.end(), first_section_pos)
        
        reason_keywords = []
        if "적출요지" in block:
            reason_match = re.search(r"적출요지[^|]*\|([^|]+)", block)
            if reason_match:
                reason_text = reason_match.group(1)
                reason_keywords = extract_reason_kw_norm(reason_text)
        elif item_detail:
            reason_keywords = extract_reason_kw_norm(item_detail)
        
        findings.append(dict(
            finding_id=finding_id, 
            doc_id=doc_id,
            item=item,
            item_detail=item_detail,  # 새로 추가
            code=code,
            reason_kw_norm=reason_keywords,
            sections_present=sections_present,
            section_spans=section_spans,  # JSONB로 저장될 예정
            start_line=start_line,
            end_line=end_line
        ))
    
    return findings


def parse_law_references(md: str, json_path: str, doc_id: str) -> List[Dict]:
    """
    JSON에서 law_table 데이터를 추출하고 Markdown에서 finding_id와 line_number를 찾아 연결
    
    Args:
        md: Markdown 내용
        json_path: layout JSON 파일 경로
        doc_id: 문서 ID
    
    Returns:
        law_reference 딕셔너리 리스트
    """
    import json
    from pathlib import Path
    
    # 1. JSON 파일 로드
    json_file = Path(json_path)
    if not json_file.exists():
        print(f"Warning: JSON file not found: {json_path}")
        return []
    
    with open(json_file, 'r', encoding='utf-8') as f:
        layout_data = json.load(f)
    
    # 2. law_table 추출 (페이지별 순서대로)
    law_tables = []
    law_counter = 1
    for page_key in sorted(layout_data.keys(), key=lambda x: int(x.split('_')[1])):
        for item in layout_data[page_key]:
            if item.get('type') == 'law_table':
                item['law_global_id'] = law_counter
                law_tables.append(item)
                law_counter += 1
    
    if not law_tables:
        return []
    
    # 3. Markdown에서 placeholder와 finding_id 찾기
    lines = md.split('\n')
    current_finding_id = None
    law_order_in_finding = {}
    
    law_references = []
    
    for line_num, line in enumerate(lines, 1):
        # finding_id 추적
        if '<!-- finding_id:' in line:
            match = re.search(r'finding_id:\s*([^\s]+)\s*-->', line)
            if match:
                current_finding_id = match.group(1)
                law_order_in_finding[current_finding_id] = 0
        
        # law_table placeholder 발견
        match = re.match(r'\[law_table#(\d+)\]', line.strip())
        if match:
            law_num = int(match.group(1))
            
            # JSON에서 해당 law_table 찾기
            law_data = next((lt for lt in law_tables if lt['law_global_id'] == law_num), None)
            if not law_data:
                print(f"Warning: law_table#{law_num} not found in JSON")
                continue
            
            # finding 내 순서 증가
            if current_finding_id:
                law_order_in_finding[current_finding_id] += 1
                order = law_order_in_finding[current_finding_id]
            else:
                order = 0  # finding 밖 (개요 섹션 등)
            
            # 페이지 번호 추출 (path에서)
            page_num = None
            path = law_data.get('path', '')
            if 'page_' in path:
                try:
                    page_str = path.split('page_')[1].split('/')[0].split('\\')[0]
                    page_num = int(page_str)
                except:
                    pass
            
            # law_reference 생성
            law_id = f"{doc_id}#L{law_num}"
            law_ref = {
                'law_id': law_id,
                'finding_id': current_finding_id,  # None 가능 (finding 밖)
                'doc_id': doc_id,
                'law_type': law_data.get('law_type'),
                'law_name': law_data.get('law_name'),
                'law_content': law_data.get('law_content'),
                'page': page_num,
                'line_number': line_num,
                'bbox': law_data.get('bbox'),
                'law_order': order
            }
            law_references.append(law_ref)
    
    return law_references
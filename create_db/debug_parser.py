import re
from md_loader import load_markdown
from md_parser import FINDING_RE, parse_findings

def debug_findings_parser(md_path):
    print(f"\n=== DEBUGGING: {md_path} ===\n")
    
    md = load_markdown(md_path)
    
    # 1. 먼저 모든 finding_id 찾기
    print("1. Searching for all finding_id patterns in the file:")
    print("-" * 50)
    
    all_findings = FINDING_RE.findall(md)
    print(f"Total finding_id occurrences found: {len(all_findings)}")
    for i, fid in enumerate(all_findings, 1):
        print(f"  {i}. {fid}")
    
    # 2. 각 finding이 어디에 있는지 확인
    print("\n2. Location of each finding_id:")
    print("-" * 50)
    
    for m in FINDING_RE.finditer(md):
        finding_id = m.group(1)
        
        # 주변 텍스트 확인
        start_pos = max(0, m.start() - 100)
        end_pos = min(len(md), m.end() + 100)
        context = md[start_pos:end_pos]
        context = context.replace('\n', '\\n')
        
        print(f"\nFinding ID: {finding_id}")
        print(f"Position: {m.start()}-{m.end()}")
        # print(f"Context: ...{context}...")  # 인코딩 문제로 스킵
        
        # 해당 라인 추출
        line_start = md.rfind("\n", 0, m.start()) + 1
        line_end = md.find("\n", m.end())
        if line_end == -1:
            line_end = len(md)
        line = md[line_start:line_end]
        print(f"Full line length: {len(line)} chars")
        print(f"Line starts with: {line[:50] if len(line) > 50 else line}")
        
        # item 추출 테스트
        item = line.split("<!--")[0].strip()
        if "적출" in item:
            item = item.split("적출", 1)[-1].strip()
        item = item.strip("#").strip()
        print(f"Extracted item length: {len(item)} chars")
    
    # 3. parse_findings 함수 실행
    print("\n3. Running parse_findings function:")
    print("-" * 50)
    
    # doc_id 추출
    doc_id_match = re.search(r'doc_id:\s*"([^"]+)"', md)
    doc_id = doc_id_match.group(1) if doc_id_match else "UNKNOWN"
    
    findings = parse_findings(md, doc_id)
    print(f"Total findings parsed: {len(findings)}")
    
    for f in findings:
        print(f"\n  Finding ID: {f['finding_id']}")
        print(f"  Item length: {len(f['item'])} chars")
        print(f"  Code: {f['code']}")
        print(f"  Keywords count: {len(f['reason_kw_norm'])}")
    
    # 4. 누락된 finding 확인
    print("\n4. Checking for missing findings:")
    print("-" * 50)
    
    parsed_ids = [f['finding_id'] for f in findings]
    for fid in all_findings:
        full_id = f"{doc_id}#{fid}"
        if full_id not in parsed_ids:
            print(f"  MISSING: {full_id}")
    
    if len(all_findings) == len(findings):
        print("  All findings were successfully parsed!")
    else:
        print(f"  WARNING: Expected {len(all_findings)}, got {len(findings)}")

if __name__ == "__main__":
    # 첫 번째 파일 디버깅
    debug_findings_parser("D:\\PythonProject\\llm\\taxaudit_summary_chat\\output\\2024(하)-2-(328)\\2024(하)-2-(328)_layout.md")
    
    # 두 번째 파일도 확인
    # debug_findings_parser("D:\\PythonProject\\llm\\taxaudit_summary_chat\\output\\2025(상)-1-(14)\\2025(상)-1-(14)_layout.md")
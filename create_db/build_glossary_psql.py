"""
용어 사전 구축 - psql subprocess 방식
psycopg2 연결 문제 우회를 위해 psql 명령행 도구 사용
"""

import sys
import io
import subprocess
import json
import re
from collections import Counter
from typing import List, Dict

# UTF-8 출력 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# PostgreSQL 연결 정보
PG_CONN = "postgresql://postgres:postgres@localhost:5432/ragdb"

def run_query(query: str) -> List[tuple]:
    """psql을 통해 쿼리 실행"""
    try:
        result = subprocess.run(
            ['psql', PG_CONN, '-t', '-A', '-F', '\t', '-c', query],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        
        if result.returncode != 0:
            print(f"Query error: {result.stderr}")
            return []
        
        lines = result.stdout.strip().split('\n')
        rows = []
        for line in lines:
            if line.strip():
                rows.append(tuple(line.split('\t')))
        return rows
        
    except Exception as e:
        print(f"Error running query: {e}")
        return []

def extract_korean_nouns(text: str, min_length: int = 2) -> List[str]:
    """한글 명사 추출"""
    if not text:
        return []
    
    stopwords = {
        '조사', '대상', '법인', '사항', '내용', '관련', '경우', '등', '및', 
        '통해', '따라', '위해', '통한', '의해', '있는', '있음', '하는', '되는',
        '이는', '그', '것', '수', '때', '곳', '년', '월', '일', '개', '명'
    }
    
    korean_pattern = re.compile(r'[가-힣]{2,}')
    words = korean_pattern.findall(text)
    
    filtered = [
        w for w in words 
        if len(w) >= min_length and w not in stopwords
    ]
    
    return filtered

def build_industry_terms() -> Dict:
    """업종명/업종코드 추출"""
    print("\n=== 1. 업종명/업종코드 추출 ===")
    
    query = """
        SELECT DISTINCT
            industry_name,
            industry_code,
            COUNT(*) OVER (PARTITION BY industry_name, industry_code) as doc_count
        FROM documents
        WHERE industry_name IS NOT NULL
        ORDER BY doc_count DESC, industry_name
    """
    
    rows = run_query(query)
    
    industry_terms = []
    seen = set()
    for row in rows:
        if len(row) >= 3:
            industry_name, industry_code, doc_count = row[0], row[1], int(row[2])
            key = (industry_name, industry_code)
            if key not in seen:
                seen.add(key)
                industry_terms.append({
                    'name': industry_name,
                    'code': industry_code,
                    'doc_count': doc_count,
                    'category': '업종'
                })
                print(f"  {industry_name} ({industry_code}): {doc_count}건")
    
    print(f"총 {len(industry_terms)}개 업종")
    return {'industries': industry_terms}

def build_overview_keywords() -> Dict:
    """조사대상개요 키워드 추출"""
    print("\n=== 2. 조사대상개요 키워드 추출 ===")
    
    query = """
        SELECT doc_id, overview_content
        FROM documents
        WHERE overview_content IS NOT NULL
        ORDER BY doc_id
    """
    
    rows = run_query(query)
    
    all_keywords = []
    for row in rows:
        if len(row) >= 2:
            overview_content = row[1]
            keywords = extract_korean_nouns(overview_content, min_length=2)
            all_keywords.extend(keywords)
    
    keyword_counts = Counter(all_keywords)
    
    significant_keywords = [
        {'keyword': k, 'frequency': v, 'category': '조사대상개요'}
        for k, v in keyword_counts.items()
        if v >= 2
    ]
    
    significant_keywords.sort(key=lambda x: x['frequency'], reverse=True)
    
    print(f"총 {len(significant_keywords)}개 키워드 (빈도 2 이상)")
    print("상위 20개:")
    for kw in significant_keywords[:20]:
        print(f"  {kw['keyword']}: {kw['frequency']}회")
    
    return {'overview_keywords': significant_keywords}

def build_finding_terms() -> Dict:
    """적출항목 용어 추출"""
    print("\n=== 3. 적출항목 용어 추출 ===")
    
    # 3-1. 적출 item
    print("\n3-1. 적출 item")
    query_items = """
        SELECT DISTINCT
            item,
            COUNT(*) as frequency
        FROM findings
        WHERE item IS NOT NULL
        GROUP BY item
        ORDER BY frequency DESC
    """
    
    rows = run_query(query_items)
    items = []
    for row in rows:
        if len(row) >= 2:
            item, frequency = row[0], int(row[1])
            items.append({
                'term': item,
                'frequency': frequency,
                'category': '적출항목'
            })
            print(f"  {item}: {frequency}회")
    
    # 3-2. 적출 코드
    print("\n3-2. 적출 코드")
    query_codes = """
        SELECT DISTINCT
            code,
            item,
            COUNT(*) as frequency
        FROM findings
        WHERE code IS NOT NULL
        GROUP BY code, item
        ORDER BY code
    """
    
    rows = run_query(query_codes)
    codes = []
    for row in rows:
        if len(row) >= 3:
            code, item, frequency = row[0], row[1], int(row[2])
            codes.append({
                'code': code,
                'item': item,
                'frequency': frequency,
                'category': '항목코드'
            })
            print(f"  {code} - {item}: {frequency}회")
    
    # 3-3. reason 키워드
    print("\n3-3. reason 키워드")
    query_reasons = """
        SELECT finding_id, reason_kw_norm::text
        FROM findings
        WHERE reason_kw_norm IS NOT NULL 
            AND jsonb_array_length(reason_kw_norm) > 0
    """
    
    rows = run_query(query_reasons)
    all_reason_keywords = []
    for row in rows:
        if len(row) >= 2:
            reason_kw_str = row[1]
            try:
                keywords = json.loads(reason_kw_str)
                if isinstance(keywords, list):
                    all_reason_keywords.extend(keywords)
            except:
                pass
    
    reason_counts = Counter(all_reason_keywords)
    reason_keywords = [
        {'keyword': k, 'frequency': v, 'category': '적출사유'}
        for k, v in reason_counts.items()
    ]
    reason_keywords.sort(key=lambda x: x['frequency'], reverse=True)
    
    print(f"총 {len(reason_keywords)}개 키워드")
    print("상위 20개:")
    for kw in reason_keywords[:20]:
        print(f"  {kw['keyword']}: {kw['frequency']}회")
    
    return {
        'finding_items': items,
        'finding_codes': codes,
        'reason_keywords': reason_keywords
    }

def main():
    """용어 사전 구축 메인 함수"""
    print("=" * 60)
    print("용어 사전 구축 시작 (psql 방식)")
    print("=" * 60)
    
    try:
        # 1. 업종 용어
        industry_data = build_industry_terms()
        
        # 2. 조사대상개요 키워드
        overview_data = build_overview_keywords()
        
        # 3. 적출항목 용어
        finding_data = build_finding_terms()
        
        # 통합
        glossary = {
            'metadata': {
                'description': '세무조사 용어 사전',
                'categories': [
                    '업종',
                    '조사대상개요',
                    '적출항목',
                    '항목코드',
                    '적출사유'
                ]
            },
            **industry_data,
            **overview_data,
            **finding_data
        }
        
        # JSON 파일로 저장
        output_path = 'create_db/vocab/glossary.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(glossary, f, ensure_ascii=False, indent=2)
        
        print("\n" + "=" * 60)
        print(f"용어 사전 저장 완료: {output_path}")
        print("=" * 60)
        
        # 요약 출력
        print("\n=== 용어 사전 요약 ===")
        print(f"업종: {len(glossary['industries'])}개")
        print(f"조사대상개요 키워드: {len(glossary['overview_keywords'])}개")
        print(f"적출항목: {len(glossary['finding_items'])}개")
        print(f"항목코드: {len(glossary['finding_codes'])}개")
        print(f"적출사유 키워드: {len(glossary['reason_keywords'])}개")
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()

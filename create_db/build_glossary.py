"""
용어 사전 구축 스크립트

DB에서 다음 카테고리별로 용어를 추출:
1. 조사대상/배경: 업종명, 업종코드, 조사대상개요 키워드
2. 적출항목: item, code, reason 키워드
"""

import sys
import io
import os

# Windows-safe PostgreSQL 연결을 위한 환경 변수 설정 (psycopg2 import 전에)
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PGPASSFILE"] = "NUL"
os.environ.pop("PGSERVICEFILE", None)
os.environ.pop("PGSERVICE", None)

import psycopg2
import json
import re
from collections import defaultdict, Counter
from typing import Dict, List, Set

# UTF-8 출력 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# PostgreSQL 연결 설정
PG_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'ragdb',
    'user': 'postgres',
    'password': 'postgres',
    'client_encoding': 'UTF8'
}


def extract_korean_nouns(text: str, min_length: int = 2) -> List[str]:
    """
    간단한 한글 명사 추출 (형태소 분석 없이)
    - 한글 2글자 이상 연속된 단어 추출
    - 조사, 부수적 단어 제외
    """
    if not text:
        return []
    
    # 제외할 단어들 (조사, 부수적 단어)
    stopwords = {
        '조사', '대상', '법인', '사항', '내용', '관련', '경우', '등', '및', 
        '통해', '따라', '위해', '통한', '의해', '있는', '있음', '하는', '되는',
        '이는', '그', '것', '수', '때', '곳', '년', '월', '일', '개', '명'
    }
    
    # 한글만 추출 (2글자 이상)
    korean_pattern = re.compile(r'[가-힣]{2,}')
    words = korean_pattern.findall(text)
    
    # 불용어 제거 및 최소 길이 필터
    filtered = [
        w for w in words 
        if len(w) >= min_length and w not in stopwords
    ]
    
    return filtered


def build_industry_terms(cursor) -> Dict[str, List[Dict]]:
    """업종명/업종코드 용어 추출"""
    print("\n=== 1. 업종명/업종코드 추출 ===")
    
    cursor.execute("""
        SELECT DISTINCT
            industry_name,
            industry_code,
            COUNT(*) as doc_count
        FROM documents
        WHERE industry_name IS NOT NULL
        GROUP BY industry_name, industry_code
        ORDER BY doc_count DESC, industry_name
    """)
    
    results = cursor.fetchall()
    
    industry_terms = []
    for row in results:
        industry_name, industry_code, doc_count = row
        industry_terms.append({
            'name': industry_name,
            'code': industry_code,
            'doc_count': doc_count,
            'category': '업종'
        })
        print(f"  {industry_name} ({industry_code}): {doc_count}건")
    
    print(f"총 {len(industry_terms)}개 업종")
    return {'industries': industry_terms}


def build_overview_keywords(cursor) -> Dict[str, List[str]]:
    """조사대상개요 키워드 추출"""
    print("\n=== 2. 조사대상개요 키워드 추출 ===")
    
    cursor.execute("""
        SELECT 
            doc_id,
            overview_content
        FROM documents
        WHERE overview_content IS NOT NULL
        ORDER BY doc_id
    """)
    
    results = cursor.fetchall()
    
    # 모든 overview_content에서 키워드 추출
    all_keywords = []
    for doc_id, overview_content in results:
        keywords = extract_korean_nouns(overview_content, min_length=2)
        all_keywords.extend(keywords)
    
    # 빈도수 계산
    keyword_counts = Counter(all_keywords)
    
    # 빈도수 2 이상인 키워드만 (여러 문서에 등장)
    significant_keywords = [
        {'keyword': k, 'frequency': v, 'category': '조사대상개요'}
        for k, v in keyword_counts.items()
        if v >= 2  # 최소 2번 이상 등장
    ]
    
    # 빈도수 내림차순 정렬
    significant_keywords.sort(key=lambda x: x['frequency'], reverse=True)
    
    print(f"총 {len(significant_keywords)}개 키워드 (빈도 2 이상)")
    print("상위 20개:")
    for kw in significant_keywords[:20]:
        print(f"  {kw['keyword']}: {kw['frequency']}회")
    
    return {'overview_keywords': significant_keywords}


def build_finding_terms(cursor) -> Dict[str, List]:
    """적출항목 용어 추출"""
    print("\n=== 3. 적출항목 용어 추출 ===")
    
    # 3-1. 적출 item
    print("\n3-1. 적출 item")
    cursor.execute("""
        SELECT DISTINCT
            item,
            COUNT(*) as frequency
        FROM findings
        WHERE item IS NOT NULL
        GROUP BY item
        ORDER BY frequency DESC
    """)
    
    items = []
    for row in cursor.fetchall():
        item, frequency = row
        items.append({
            'term': item,
            'frequency': frequency,
            'category': '적출항목'
        })
        print(f"  {item}: {frequency}회")
    
    # 3-2. 적출 코드
    print("\n3-2. 적출 코드")
    cursor.execute("""
        SELECT DISTINCT
            code,
            item,
            COUNT(*) as frequency
        FROM findings
        WHERE code IS NOT NULL
        GROUP BY code, item
        ORDER BY code
    """)
    
    codes = []
    for row in cursor.fetchall():
        code, item, frequency = row
        codes.append({
            'code': code,
            'item': item,
            'frequency': frequency,
            'category': '항목코드'
        })
        print(f"  {code} - {item}: {frequency}회")
    
    # 3-3. reason 키워드 (JSONB 배열)
    print("\n3-3. reason 키워드")
    cursor.execute("""
        SELECT 
            finding_id,
            reason_kw_norm
        FROM findings
        WHERE reason_kw_norm IS NOT NULL 
            AND jsonb_array_length(reason_kw_norm) > 0
    """)
    
    all_reason_keywords = []
    for row in cursor.fetchall():
        finding_id, reason_kw_norm = row
        # JSONB를 Python list로 변환
        keywords = json.loads(reason_kw_norm) if isinstance(reason_kw_norm, str) else reason_kw_norm
        all_reason_keywords.extend(keywords)
    
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
    print("용어 사전 구축 시작")
    print("=" * 60)
    
    # PostgreSQL 연결
    PG_CONFIG['options'] = "-c client_encoding=UTF8"
    conn = psycopg2.connect(**PG_CONFIG)
    cursor = conn.cursor()
    
    try:
        # 1. 업종 용어
        industry_data = build_industry_terms(cursor)
        
        # 2. 조사대상개요 키워드
        overview_data = build_overview_keywords(cursor)
        
        # 3. 적출항목 용어
        finding_data = build_finding_terms(cursor)
        
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
        
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    main()

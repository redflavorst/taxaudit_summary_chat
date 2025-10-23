"""
용어 사전 구축 - SQL 출력 방식
PostgreSQL 연결 문제 우회를 위해 SQL 쿼리를 파일로 출력하고 수동 실행
"""

import sys
import io

# UTF-8 출력 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def generate_sql_queries():
    """용어 추출을 위한 SQL 쿼리 생성"""
    
    queries = {
        'industries': """
-- 1. 업종명/업종코드
SELECT 
    json_build_object(
        'name', industry_name,
        'code', industry_code,
        'doc_count', COUNT(*),
        'category', '업종'
    ) as term_json
FROM documents
WHERE industry_name IS NOT NULL
GROUP BY industry_name, industry_code
ORDER BY COUNT(*) DESC, industry_name;
""",
        
        'finding_items': """
-- 2. 적출 item
SELECT 
    json_build_object(
        'term', item,
        'frequency', COUNT(*),
        'category', '적출항목'
    ) as term_json
FROM findings
WHERE item IS NOT NULL
GROUP BY item
ORDER BY COUNT(*) DESC;
""",
        
        'finding_codes': """
-- 3. 적출 코드
SELECT 
    json_build_object(
        'code', code,
        'item', item,
        'frequency', COUNT(*),
        'category', '항목코드'
    ) as term_json
FROM findings
WHERE code IS NOT NULL
GROUP BY code, item
ORDER BY code;
""",
        
        'reason_keywords': """
-- 4. reason 키워드
SELECT 
    json_build_object(
        'keyword', keyword,
        'frequency', COUNT(*),
        'category', '적출사유'
    ) as term_json
FROM (
    SELECT jsonb_array_elements_text(reason_kw_norm) as keyword
    FROM findings
    WHERE reason_kw_norm IS NOT NULL 
        AND jsonb_array_length(reason_kw_norm) > 0
) as kw
GROUP BY keyword
ORDER BY COUNT(*) DESC;
"""
    }
    
    return queries

def main():
    print("=" * 60)
    print("용어 사전 SQL 쿼리 생성")
    print("=" * 60)
    
    queries = generate_sql_queries()
    
    # SQL 파일로 저장
    sql_file = 'create_db/vocab/extract_terms.sql'
    with open(sql_file, 'w', encoding='utf-8') as f:
        f.write("-- 용어 사전 추출 SQL\n")
        f.write("-- PostgreSQL에서 실행 후 결과를 JSON으로 저장\n\n")
        
        for category, query in queries.items():
            f.write(f"\n-- {category}\n")
            f.write(f"\\o create_db/vocab/{category}.json\n")
            f.write(query)
            f.write("\n\\o\n")
    
    print(f"\nSQL 쿼리 저장 완료: {sql_file}")
    print("\n다음 단계:")
    print("1. PostgreSQL에 접속:")
    print("   psql -h localhost -p 5432 -U postgres -d ragdb")
    print(f"2. SQL 파일 실행:")
    print(f"   \\i {sql_file}")
    print("3. 생성된 JSON 파일들을 통합하여 glossary.json 생성")

if __name__ == '__main__':
    main()

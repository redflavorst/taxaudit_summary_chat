import psycopg2
import json

def check_data():
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="ragdb",
        user="postgres",
        password="root"
    )
    cur = conn.cursor()
    
    # findings 테이블 확인
    print("\n=== FINDINGS TABLE ===")
    cur.execute("SELECT * FROM findings LIMIT 10")
    findings = cur.fetchall()
    
    # 컬럼명 가져오기
    columns = [desc[0] for desc in cur.description]
    print(f"Columns: {columns}")
    print(f"Total findings: {len(findings)}")
    
    for finding in findings:
        print("\n---")
        for col, val in zip(columns, finding):
            if val and not (isinstance(val, list) and len(val) == 0):
                print(f"{col}: {val}")
    
    # table_rows 테이블 확인
    print("\n\n=== TABLE_ROWS TABLE ===")
    cur.execute("SELECT * FROM table_rows LIMIT 10")
    rows = cur.fetchall()
    
    columns = [desc[0] for desc in cur.description]
    print(f"Columns: {columns}")
    print(f"Total rows: {len(rows)}")
    
    for row in rows[:2]:  # 처음 2개만
        print("\n---")
        for col, val in zip(columns, row):
            if val:
                print(f"{col}: {val}")
    
    # row_finding_map 확인
    print("\n\n=== ROW_FINDING_MAP TABLE ===")
    cur.execute("SELECT * FROM row_finding_map LIMIT 10")
    maps = cur.fetchall()
    
    columns = [desc[0] for desc in cur.description]
    print(f"Total mappings: {len(maps)}")
    
    for m in maps[:3]:  # 처음 3개만
        print(f"Map: {m[0]} -> Score: {m[3]}")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    check_data()
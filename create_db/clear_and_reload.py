import psycopg2
from run_ingest import main

def clear_tables():
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="ragdb",
        user="postgres",
        password="root"
    )
    cur = conn.cursor()
    
    # 테이블 비우기 (역순으로 삭제)
    tables = ["chunks", "row_finding_map", "findings", "table_rows", "documents"]
    for table in tables:
        cur.execute(f"DELETE FROM {table}")
        print(f"Cleared {table} table")
    
    conn.commit()
    cur.close()
    conn.close()
    print("\nAll tables cleared!")

if __name__ == "__main__":
    print("Clearing existing data...")
    clear_tables()
    
    print("\nReloading data with improved parser...")
    main([
        "D:\\PythonProject\\llm\\taxaudit_summary_chat\\output\\2024(하)-2-(328)\\2024(하)-2-(328)_layout.md",
        "D:\\PythonProject\\llm\\taxaudit_summary_chat\\output\\2025(상)-1-(14)\\2025(상)-1-(14)_layout.md"
    ])
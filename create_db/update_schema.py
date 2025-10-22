import psycopg2

def update_schema():
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="ragdb",
        user="postgres",
        password="root"
    )
    cur = conn.cursor()
    
    try:
        # 기존 테이블 백업
        print("Creating backup of existing tables...")
        cur.execute("DROP TABLE IF EXISTS findings_backup")
        cur.execute("CREATE TABLE findings_backup AS SELECT * FROM findings")
        
        # findings 테이블 스키마 수정
        print("Updating findings table schema...")
        
        # 기존 sections 컬럼 삭제하고 새로운 컬럼들 추가
        cur.execute("""
            ALTER TABLE findings 
            DROP COLUMN IF EXISTS sections,
            DROP COLUMN IF EXISTS start_page,
            DROP COLUMN IF EXISTS end_page,
            ADD COLUMN IF NOT EXISTS item_detail TEXT,
            ADD COLUMN IF NOT EXISTS sections_present TEXT[],
            ADD COLUMN IF NOT EXISTS section_spans JSONB,
            ADD COLUMN IF NOT EXISTS start_line INTEGER,
            ADD COLUMN IF NOT EXISTS end_line INTEGER
        """)
        
        # chunks 테이블에도 라인 정보 개선
        print("Updating chunks table schema...")
        cur.execute("""
            ALTER TABLE chunks
            DROP COLUMN IF EXISTS line_start,
            DROP COLUMN IF EXISTS line_end,
            ADD COLUMN IF NOT EXISTS start_line INTEGER,
            ADD COLUMN IF NOT EXISTS end_line INTEGER,
            ADD COLUMN IF NOT EXISTS section_order INTEGER,
            ADD COLUMN IF NOT EXISTS chunk_order INTEGER,
            ADD COLUMN IF NOT EXISTS code VARCHAR(10),
            ADD COLUMN IF NOT EXISTS item TEXT,
            ADD COLUMN IF NOT EXISTS item_norm TEXT
        """)
        
        # table_rows 테이블에 라인 정보 추가
        print("Updating table_rows table schema...")
        cur.execute("""
            ALTER TABLE table_rows
            DROP COLUMN IF EXISTS page,
            ADD COLUMN IF NOT EXISTS line_number INTEGER
        """)
        
        conn.commit()
        print("Schema update completed successfully!")
        
    except Exception as e:
        print(f"Error updating schema: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    update_schema()

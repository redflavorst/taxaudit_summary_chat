import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def create_database():
    try:
        # postgres 기본 DB에 먼저 연결
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="postgres",  # 기본 DB
            user="postgres",
            password="root"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        cur = conn.cursor()
        
        # DB 존재 여부 확인
        cur.execute("SELECT 1 FROM pg_database WHERE datname = 'ragdb'")
        exists = cur.fetchone()
        
        if not exists:
            cur.execute("CREATE DATABASE ragdb")
            print("ragdb database created successfully!")
        else:
            print("ragdb database already exists.")
            
        cur.close()
        conn.close()
        
        # 테이블 생성
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="ragdb",
            user="postgres",
            password="root"
        )
        cur = conn.cursor()
        
        # 필요한 테이블들 생성
        tables = [
            """CREATE TABLE IF NOT EXISTS documents (
                doc_id VARCHAR(50) PRIMARY KEY,
                title TEXT,
                source_path TEXT
            )""",
            
            """CREATE TABLE IF NOT EXISTS table_rows (
                row_id VARCHAR(50) PRIMARY KEY,
                doc_id VARCHAR(50),
                row_no INTEGER,
                item TEXT,
                code VARCHAR(10),
                reason_kw_raw TEXT,
                line_number INTEGER
            )""",
            
            """CREATE TABLE IF NOT EXISTS findings (
                finding_id VARCHAR(50) PRIMARY KEY,
                doc_id VARCHAR(50),
                item TEXT,
                item_detail TEXT,
                code VARCHAR(10),
                reason_kw_norm TEXT[],
                sections_present TEXT[],
                section_spans JSONB,
                start_line INTEGER,
                end_line INTEGER
            )""",
            
            """CREATE TABLE IF NOT EXISTS row_finding_map (
                map_id VARCHAR(100) PRIMARY KEY,
                row_id VARCHAR(50),
                finding_id VARCHAR(50),
                score NUMERIC,
                code_mismatch BOOLEAN,
                needs_review BOOLEAN
            )""",
            
            """CREATE TABLE IF NOT EXISTS chunks (
                chunk_id VARCHAR(100) PRIMARY KEY,
                finding_id VARCHAR(50),
                doc_id VARCHAR(50),
                section TEXT,
                section_order INTEGER,
                chunk_order INTEGER,
                code VARCHAR(10),
                item TEXT,
                item_norm TEXT,
                page INTEGER,
                start_line INTEGER,
                end_line INTEGER,
                text TEXT,
                text_norm TEXT,
                text_raw TEXT,
                meta_line TEXT,
                extraction_version VARCHAR(20),
                created_at TIMESTAMP
            )""",
            
            """CREATE TABLE IF NOT EXISTS law_references (
                law_id VARCHAR(100) PRIMARY KEY,
                finding_id VARCHAR(50),
                doc_id VARCHAR(50) NOT NULL,
                law_type VARCHAR(20),
                law_name TEXT,
                law_content TEXT,
                page INTEGER,
                line_number INTEGER,
                bbox JSONB,
                law_order INTEGER,
                extraction_version VARCHAR(20),
                created_at TIMESTAMP DEFAULT NOW()
            )"""
        ]
        
        for table_sql in tables:
            cur.execute(table_sql)
            
        conn.commit()
        print("All tables created successfully!")
        
        cur.close()
        conn.close()
        
    except psycopg2.OperationalError as e:
        print(f"PostgreSQL connection failed: {e}")
        print("\nSolution:")
        print("1. Check if PostgreSQL is installed")
        print("2. Check if PostgreSQL service is running")
        print("3. Check if username/password is correct")
        
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    create_database()

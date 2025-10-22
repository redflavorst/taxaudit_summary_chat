import psycopg2
from config import settings

def update_chunks_schema():
    conn = psycopg2.connect(settings.PG_DSN)
    cur = conn.cursor()
    
    try:
        print("Updating chunks table schema...")
        
        cur.execute("""
            ALTER TABLE chunks 
            ADD COLUMN IF NOT EXISTS text_norm TEXT,
            ADD COLUMN IF NOT EXISTS text_raw TEXT,
            ADD COLUMN IF NOT EXISTS extraction_version VARCHAR(20),
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMP
        """)
        
        conn.commit()
        print("OK: chunks table schema updated")
        print("   - text_norm (TEXT)")
        print("   - text_raw (TEXT)")
        print("   - extraction_version (VARCHAR(20))")
        print("   - created_at (TIMESTAMP)")
        
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    update_chunks_schema()

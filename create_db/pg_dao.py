# create_db/pg_dao.py
import psycopg2
import psycopg2.extras
import json

def upsert_many(conn, table, rows, conflict_key):
    if not rows: return
    cols = list(rows[0].keys())
    
    # 중복 제거
    seen_keys = set()
    unique_rows = []
    for row in rows:
        key_value = row.get(conflict_key)
        if key_value not in seen_keys:
            seen_keys.add(key_value)
            unique_rows.append(row)
    
    if not unique_rows: return
    
    with conn.cursor() as cur:
        try:
            # JSONB 필드 처리
            values = []
            for row in unique_rows:
                row_values = []
                for col in cols:
                    val = row.get(col)
                    # JSONB 타입 필드는 Json wrapper 사용
                    if col in ['section_spans', 'section_summaries', 'meta', 'bbox'] and val is not None:
                        row_values.append(psycopg2.extras.Json(val))
                    else:
                        row_values.append(val)
                values.append(tuple(row_values))
            
            psycopg2.extras.execute_values(
                cur,
                f"""
                INSERT INTO {table} ({",".join(cols)})
                VALUES %s
                ON CONFLICT ({conflict_key}) DO UPDATE SET
                {",".join([f"{c}=excluded.{c}" for c in cols if c!=conflict_key])}
                """,
                values,
                page_size=200
            )
            conn.commit()
            
            if len(rows) != len(unique_rows):
                print(f"  Note: Removed {len(rows) - len(unique_rows)} duplicate {table} entries")
                
        except Exception as e:
            print(f"Error inserting into {table}: {e}")
            conn.rollback()
            raise
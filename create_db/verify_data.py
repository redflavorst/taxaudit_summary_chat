import psycopg2
import json

def verify_data():
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="ragdb",
        user="postgres",
        password="root"
    )
    cur = conn.cursor()
    
    print("\n=== FINDINGS TABLE WITH LINE NUMBERS AND SECTIONS ===")
    cur.execute("""
        SELECT finding_id, item, code, start_line, end_line, 
               sections_present, section_spans
        FROM findings 
        ORDER BY doc_id, finding_id
    """)
    
    for row in cur.fetchall():
        print(f"\nFinding: {row[0]}")
        print(f"  Item: {row[1]}")
        print(f"  Code: {row[2]}")
        print(f"  Lines: {row[3]}-{row[4]}")
        print(f"  Sections present: {row[5]}")
        if row[6]:  # section_spans (JSONB)
            print(f"  Section details:")
            for section in row[6]:
                print(f"    - {section['name']}: lines {section['start_line']}-{section['end_line']}")
    
    print("\n\n=== TABLE_ROWS WITH LINE NUMBERS ===")
    cur.execute("""
        SELECT row_id, item, code, line_number
        FROM table_rows 
        LIMIT 3
    """)
    
    for row in cur.fetchall():
        print(f"Row {row[0]}: Line {row[3]} - {row[1]} (Code: {row[2]})")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    verify_data()
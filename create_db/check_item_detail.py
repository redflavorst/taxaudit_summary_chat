import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="ragdb",
    user="postgres",
    password="root"
)
cur = conn.cursor()

print("=== FINDINGS WITH ITEM_DETAIL ===\n")
cur.execute("""
    SELECT finding_id, item, item_detail, code
    FROM findings 
    ORDER BY finding_id
""")

for row in cur.fetchall():
    print(f"Finding: {row[0]}")
    print(f"  Item: {row[1]}")
    print(f"  Code: {row[3]}")
    if row[2]:
        detail = row[2].replace('\n', ' ')[:80]
        print(f"  Item Detail: {len(row[2])} chars")
        # 첫 줄만 출력
        first_line = row[2].split('\n')[0] if '\n' in row[2] else row[2][:50]
        print(f"  First line: {first_line[:50]}")
    else:
        print(f"  Item Detail: None")
    print()

cur.close()
conn.close()
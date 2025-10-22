import psycopg2
from collections import Counter
from config import settings
from extract_meta import vocab_loader
import re

def analyze_coverage():
    """DB의 실제 데이터와 사전 커버리지 분석"""
    conn = psycopg2.connect(settings.PG_DSN)
    cur = conn.cursor()
    
    cur.execute("SELECT reason_kw_raw FROM table_rows WHERE reason_kw_raw IS NOT NULL")
    reasons = [r[0] for r in cur.fetchall()]
    
    cur.execute("SELECT item FROM findings WHERE item IS NOT NULL")
    items = [r[0] for r in cur.fetchall()]
    
    print("=== 적출요지 키워드 빈도 (Top 30) ===")
    all_words = []
    for reason in reasons:
        words = re.findall(r'[가-힣]{2,}', reason)
        all_words.extend(words)
    
    word_freq = Counter(all_words)
    for word, count in word_freq.most_common(30):
        in_vocab = any(word in syn or word == key 
                      for key, meta in vocab_loader.actions_vocab.items() 
                      for syn in [key] + meta.get('synonyms', []))
        marker = "Y" if in_vocab else "N"
        print(f"{marker} {word}: {count}")
    
    print("\n=== 적출 항목 키워드 빈도 (Top 20) ===")
    item_words = []
    for item in items:
        words = re.findall(r'[가-힣]{2,}', item)
        item_words.extend(words)
    
    item_freq = Counter(item_words)
    for word, count in item_freq.most_common(20):
        print(f"{word}: {count}")
    
    print("\n=== 현재 사전 통계 ===")
    print(f"업종: {len(vocab_loader.industry_vocab)}개")
    print(f"도메인 태그: {len(vocab_loader.domain_tags_vocab)}개")
    print(f"행위: {len(vocab_loader.actions_vocab)}개")
    
    missing_actions = []
    for word, count in word_freq.most_common(50):
        if count >= 2:
            in_vocab = any(word in syn or word == key 
                          for key, meta in vocab_loader.actions_vocab.items() 
                          for syn in [key] + meta.get('synonyms', []))
            if not in_vocab:
                missing_actions.append((word, count))
    
    print(f"\n=== 사전에 없는 고빈도 단어 (2회 이상) ===")
    for word, count in missing_actions[:20]:
        print(f"  - {word}: {count}회")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    analyze_coverage()

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from elasticsearch import Elasticsearch
from config import settings

def compare_chunks():
    es_kwargs = {}
    if settings.ES_USER and settings.ES_PASSWORD:
        es_kwargs["basic_auth"] = (settings.ES_USER, settings.ES_PASSWORD)
    if settings.ES_VERIFY_CERTS is not None:
        es_kwargs["verify_certs"] = settings.ES_VERIFY_CERTS
    
    es = Elasticsearch(settings.ES_URL, **es_kwargs)
    
    chunk1_id = "2024H-002-328#F11209@01-00"
    chunk2_id = "2024H-002-328#F11209@00-00"
    
    r1 = es.get(index="chunks", id=chunk1_id)
    r2 = es.get(index="chunks", id=chunk2_id)
    
    print("=== Chunk 1: 조사기법 (Score: 0.5611) ===")
    print(f"Section: {r1['_source']['section']}")
    print(f"Lines: {r1['_source']['start_line']}-{r1['_source']['end_line']}")
    print(f"\nText (first 500 chars):")
    print(r1['_source']['text_norm'][:500])
    
    print("\n" + "="*70)
    print("\n=== Chunk 2: 조사착안 (Score: 0.4643) ===")
    print(f"Section: {r2['_source']['section']}")
    print(f"Lines: {r2['_source']['start_line']}-{r2['_source']['end_line']}")
    print(f"\nText (first 500 chars):")
    print(r2['_source']['text_norm'][:500])
    
    print("\n" + "="*70)
    print("\n키워드 분석:")
    
    text1 = r1['_source']['text_norm']
    text2 = r2['_source']['text_norm']
    
    keywords = ['손금', '부인', '보증수수료', '대납']
    
    for kw in keywords:
        count1 = text1.count(kw)
        count2 = text2.count(kw)
        print(f"  '{kw}': 조사기법={count1}회, 조사착안={count2}회")

if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    compare_chunks()

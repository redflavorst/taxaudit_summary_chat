"""
Elasticsearch 인덱스 초기화 및 매핑 적용 스크립트

사용법:
1. 인덱스 생성 (없을 때만): python init_es_indices.py --create
2. 인덱스 재생성 (기존 삭제): python init_es_indices.py --recreate
"""

from elasticsearch import Elasticsearch
from es_mappings import (
    FINDINGS_MAPPING,
    CHUNKS_MAPPING,
    create_index_if_not_exists,
    delete_and_recreate_index
)
from config import settings
import argparse


def main():
    parser = argparse.ArgumentParser(description="Elasticsearch 인덱스 초기화")
    parser.add_argument(
        "--create",
        action="store_true",
        help="인덱스가 없을 때만 생성 (기존 데이터 보존)"
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="기존 인덱스 삭제 후 재생성 (주의: 데이터 손실)"
    )
    parser.add_argument(
        "--host",
        default="http://localhost:9200",
        help="Elasticsearch 호스트 (기본값: http://localhost:9200)"
    )
    
    args = parser.parse_args()
    
    if not args.create and not args.recreate:
        print("❌ --create 또는 --recreate 옵션을 선택해주세요")
        return
    
    # ES 연결 (config.py 설정 사용)
    es_kwargs = {}
    if settings.ES_USER and settings.ES_PASSWORD:
        es_kwargs["basic_auth"] = (settings.ES_USER, settings.ES_PASSWORD)
    if settings.ES_VERIFY_CERTS is not None:
        es_kwargs["verify_certs"] = settings.ES_VERIFY_CERTS
    if settings.ES_CA_CERTS:
        es_kwargs["ca_certs"] = settings.ES_CA_CERTS
    
    es_host = args.host if args.host != "http://localhost:9200" else settings.ES_URL
    es = Elasticsearch([es_host], **es_kwargs)
    
    if not es.ping():
        print(f"❌ Elasticsearch 연결 실패: {es_host}")
        print(f"  설정: user={settings.ES_USER}, verify_certs={settings.ES_VERIFY_CERTS}")
        return
    
    print(f"✅ Elasticsearch 연결 성공: {es_host}")
    
    # findings 인덱스
    print("\n📂 findings 인덱스 처리 중...")
    if args.recreate:
        delete_and_recreate_index(es, "findings", FINDINGS_MAPPING)
    else:
        create_index_if_not_exists(es, "findings", FINDINGS_MAPPING)
    
    # chunks 인덱스
    print("\n📂 chunks 인덱스 처리 중...")
    if args.recreate:
        delete_and_recreate_index(es, "chunks", CHUNKS_MAPPING)
    else:
        create_index_if_not_exists(es, "chunks", CHUNKS_MAPPING)
    
    print("\n✅ 모든 인덱스 처리 완료!")
    
    # 인덱스 정보 출력
    print("\n📊 현재 인덱스 정보:")
    for index_name in ["findings", "chunks"]:
        info = es.cat.indices(index=index_name, format="json")[0]
        print(f"  - {index_name}: {info['docs.count']}개 문서, {info['store.size']} 크기")


if __name__ == "__main__":
    main()

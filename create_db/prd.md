create_db/
├── config.py                 # DB/ES/Qdrant 접속, 임베딩 설정
├── md_loader.py              # 파일 로더(경로 스캔, MD 읽기)
├── md_parser.py              # 앵커/표/헤더/본문 파싱(행, finding, 섹션 텍스트)
├── normalizer.py             # 키워드 정규화(선택)
├── linker.py                 # row ↔ finding 매칭(스코어링)
├── chunker.py                # finding 내부 청킹(400–800토큰)
├── pg_dao.py                 # Postgres upsert
├── es_indexer.py             # ES 색인(findings/chunks)
├── qdrant_indexer.py         # (선택) Qdrant 색인
├── run_ingest.py             # end-to-end 실행 진입점
└── utils.py                  # 공통(토큰화, 정규식, 해시 등)

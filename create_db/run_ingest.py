from pathlib import Path
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Set
from urllib.parse import parse_qsl, unquote, urlparse
import re
import os
import locale
import sys

# Windows cp949 encoding workaround
if sys.platform == "win32":
    try:
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
    except Exception:
        try:
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        except Exception:
            pass

from elasticsearch import Elasticsearch
import psycopg2
from psycopg2 import sql

from md_loader import load_markdown
from md_parser import parse_doc_id, parse_table_rows, parse_findings, parse_law_references, parse_overview_table
from linker import link_rows_findings
from chunker import make_chunks_for_finding
from pg_dao import upsert_many
from es_indexer import index_findings, index_chunks, index_laws
from config import settings
from extract_meta import extract_all_meta


def _normalize_item(item: str | None) -> str | None:
    if not item:
        return None
    normalized = re.sub(r"^\s*\d+[\.\)]\s*", "", item).strip()
    return normalized or item.strip()

def _parse_pg_dsn(dsn: str) -> Dict[str, Any]:
    parsed = urlparse(dsn)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError("PG_DSN must start with postgresql://")
    database = (parsed.path or "").lstrip("/")
    if not database:
        raise ValueError("PG_DSN must include a database name")

    connect_kwargs: Dict[str, Any] = {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "dbname": database,
    }

    if parsed.username:
        connect_kwargs["user"] = unquote(parsed.username)
    if parsed.password:
        connect_kwargs["password"] = unquote(parsed.password)

    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        connect_kwargs[key] = value

    return connect_kwargs


def _ensure_database_exists(connect_kwargs: Dict[str, Any]) -> None:
    target_db = connect_kwargs.get("dbname")
    admin_db = getattr(settings, "PG_ADMIN_DB", "postgres") or "postgres"

    if not target_db or target_db == admin_db:
        return

    admin_kwargs = dict(connect_kwargs)
    admin_kwargs["dbname"] = admin_db

    try:
        admin_conn = psycopg2.connect(**admin_kwargs)
        admin_conn.autocommit = True
        cur = admin_conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
        if not cur.fetchone():
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db)))
            print(f"  - PostgreSQL: created database {target_db}")
        cur.close()
        admin_conn.close()
    except UnicodeDecodeError:
        raise
    except Exception as exc:
        print(f"  - Warning: could not ensure database '{target_db}': {exc}")


def _decode_backend_error(err: UnicodeDecodeError) -> str:
    raw = err.object if isinstance(err.object, (bytes, bytearray)) else None
    if raw is None:
        return str(err)

    for codec in ("utf-8", "cp949", locale.getpreferredencoding(False), "latin1"):
        if not codec:
            continue
        try:
            return raw.decode(codec)
        except Exception:
            continue

    return repr(raw)


def make_pg_conn():
    """Create a PostgreSQL connection with Windows-safe encoding handling."""
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PGPASSFILE"] = "NUL"
    os.environ.pop("PGSERVICEFILE", None)
    os.environ.pop("PGSERVICE", None)

    try:
        connect_kwargs = _parse_pg_dsn(settings.PG_DSN)
        _ensure_database_exists(connect_kwargs)

        existing_options = connect_kwargs.get("options", "").strip()
        ingest_options = "-c client_encoding=UTF8 -c application_name=taxaudit_ingest"
        connect_kwargs["options"] = f"{existing_options} {ingest_options}".strip()

        return psycopg2.connect(**connect_kwargs)
    except UnicodeDecodeError as err:
        decoded = _decode_backend_error(err).strip()
        dbg = {
            k: os.environ.get(k)
            for k in ["PGPASSFILE", "PGSERVICE", "PGSERVICEFILE", "PGHOST", "PGDATABASE", "PGUSER"]
        }
        print("PG ENV DEBUG:", dbg)
        print("DSN:", settings.PG_DSN)
        raise RuntimeError(decoded or "PostgreSQL connection failed") from None
    except Exception:
        dbg = {
            k: os.environ.get(k)
            for k in ["PGPASSFILE", "PGSERVICE", "PGSERVICEFILE", "PGHOST", "PGDATABASE", "PGUSER"]
        }
        print("PG ENV DEBUG:", dbg)
        print("DSN:", settings.PG_DSN)
        raise

def main(md_paths):
    conn = make_pg_conn()

    es_kwargs: Dict = {}
    api_key_id = getattr(settings, "ES_API_KEY_ID", None)
    api_key_secret = getattr(settings, "ES_API_KEY_SECRET", None)
    if api_key_id and api_key_secret:
        es_kwargs["api_key"] = (api_key_id, api_key_secret)
    elif settings.ES_USER and settings.ES_PASSWORD:
        es_kwargs["basic_auth"] = (settings.ES_USER, settings.ES_PASSWORD)
    if getattr(settings, "ES_VERIFY_CERTS", None) is not None:
        es_kwargs["verify_certs"] = settings.ES_VERIFY_CERTS
    if getattr(settings, "ES_CA_CERTS", None):
        es_kwargs["ca_certs"] = settings.ES_CA_CERTS
    es = Elasticsearch(settings.ES_URL, **es_kwargs)

    for mp in md_paths:
        print(f"\nProcessing: {mp}")
        md = load_markdown(mp)
        doc_id = parse_doc_id(md)
        print(f"  - Document ID: {doc_id}")

        overview_data = parse_overview_table(md)
        rows = parse_table_rows(md, doc_id)
        findings = parse_findings(md, doc_id)
        
        # Parse law_references from JSON + Markdown
        json_path = mp.replace('_layout.md', '_layout.json')
        law_refs = parse_law_references(md, json_path, doc_id)
        
        overview_section = md.split("## 적출")[0] if "## 적출" in md else md[:2000]
        findings_text = "\n".join([f.get("item", "") + " " + str(f.get("reason_kw_norm", [])) for f in findings])
        reason_rows_text = [r.get("reason_kw_raw", "") for r in rows]
        code_list = [r.get("code") for r in rows if r.get("code")]
        
        meta_extracted = extract_all_meta(
            overview_text=overview_section,
            reason_rows=reason_rows_text,
            findings_text=findings_text,
            code_list=code_list
        )

        print(f"  - Parsed: {len(rows)} rows, {len(findings)} findings, {len(law_refs)} law_references")
        print(f"  - Overview: entity={overview_data.get('entity_type')}, "
              f"industry={overview_data.get('industry_name')}({overview_data.get('industry_code')}), "
              f"audit_type={overview_data.get('audit_type')}")
        print(f"  - Meta: industry_sub={meta_extracted.get('industry_sub')}, "
              f"tags={meta_extracted.get('domain_tags')}, actions={meta_extracted.get('actions')}")
        for f in findings:
            print(
                f"    Finding {f['finding_id']}: Lines {f['start_line']}-{f['end_line']}, "
                f"Sections: {f['sections_present']}"
            )

        maps = link_rows_findings(rows, findings)

        row_ids_by_finding: DefaultDict[str, Set[str]] = defaultdict(set)
        code_mismatch_by_finding: DefaultDict[str, bool] = defaultdict(bool)
        for mp_entry in maps:
            row_ids_by_finding[mp_entry["finding_id"]].add(mp_entry["row_id"])
            if mp_entry.get("code_mismatch"):
                code_mismatch_by_finding[mp_entry["finding_id"]] = True

        findings_for_index: List[Dict] = []
        for f in findings:
            f_idx = dict(f)
            f_idx["row_ids"] = sorted(row_ids_by_finding.get(f["finding_id"], []))
            f_idx["item_norm"] = _normalize_item(f.get("item"))
            f_idx["code_mismatch"] = code_mismatch_by_finding.get(f["finding_id"], False)
            
            # chunk_count 계산 (나중에 추가될 예정)
            f_idx["chunk_count"] = 0  # 임시로 0 설정
            
            findings_for_index.append(f_idx)

        all_chunks: List[Dict] = []
        chunk_count_by_finding: DefaultDict[str, int] = defaultdict(int)
        for f in findings:
            chunks = make_chunks_for_finding(f, md_content=md)
            all_chunks.extend(chunks)
            chunk_count_by_finding[f["finding_id"]] = len(chunks)
        
        # findings_for_index에 chunk_count 업데이트
        for f_idx in findings_for_index:
            f_idx["chunk_count"] = chunk_count_by_finding.get(f_idx["finding_id"], 0)

        doc_record = {
            "doc_id": doc_id,
            "title": Path(mp).name,
            "source_path": str(mp),
            "entity_type": overview_data.get("entity_type"),
            "industry_name": overview_data.get("industry_name"),
            "industry_code": overview_data.get("industry_code"),
            "audit_type": overview_data.get("audit_type"),
            "revenue_bracket": overview_data.get("revenue_bracket"),
            "audit_office": overview_data.get("audit_office"),
            "overview_raw": overview_data.get("overview_raw"),
            "overview_content": overview_data.get("overview_content")
        }
        upsert_many(conn, "documents", [doc_record], "doc_id")
        upsert_many(conn, "table_rows", rows, "row_id")
        upsert_many(conn, "findings", findings, "finding_id")
        upsert_many(conn, "row_finding_map", maps, "map_id")
        upsert_many(conn, "chunks", all_chunks, "chunk_id")
        upsert_many(conn, "law_references", law_refs, "law_id")

        print(
            f"  - PostgreSQL: Inserted {len(rows)} rows, {len(findings)} findings, "
            f"{len(all_chunks)} chunks, {len(law_refs)} law_references"
        )

        try:
            doc_meta = {
                doc_id: {
                    "doc_title": Path(mp).name,
                    "entity_type": overview_data.get("entity_type"),
                    "industry_name": overview_data.get("industry_name"),
                    "industry_code": overview_data.get("industry_code"),
                    "audit_type": overview_data.get("audit_type"),
                    "revenue_bracket": overview_data.get("revenue_bracket"),
                    "audit_office": overview_data.get("audit_office"),
                    "overview_content": overview_data.get("overview_content"),
                    "overview_keywords_norm": meta_extracted.get("overview_keywords_norm", []),
                }
            }
            # row_finding_maps 전달하여 codes_from_rows 추출 가능하게
            index_findings(
                es, 
                "findings", 
                findings_for_index, 
                doc_meta_by_docid=doc_meta,
                row_finding_maps=maps
            )
            index_chunks(es, "chunks", all_chunks)
            index_laws(es, "law_references", law_refs)
            print(f"  - Elasticsearch indexing completed for {doc_id}")
        except Exception as e:
            print(f"  - Elasticsearch indexing skipped (ES not available): {type(e).__name__}")
    
    if settings.USE_QDRANT:
        try:
            # vectorstore 모듈 import를 위한 경로 추가
            current_dir = Path(__file__).parent.resolve()
            if str(current_dir) not in sys.path:
                sys.path.insert(0, str(current_dir))
            
            # 동적 import로 모듈 로드
            import importlib.util
            upsert_module_path = current_dir / "vectorstore" / "upsert_vectors.py"
            
            spec = importlib.util.spec_from_file_location("vectorstore.upsert_vectors", upsert_module_path)
            upsert_module = importlib.util.module_from_spec(spec)
            sys.modules["vectorstore.upsert_vectors"] = upsert_module
            spec.loader.exec_module(upsert_module)
            
            print("\nUpserting to Qdrant vectorstore...")
            upsert_module.run_all()
        except ImportError as e:
            print(f"  - Qdrant upsert skipped (module not found): {e}")
        except Exception as e:
            print(f"  - Qdrant upsert skipped: {type(e).__name__}: {e}")


if __name__ == "__main__":
    # output 폴더의 모든 _layout.md 파일 자동 검색
    output_dir = Path(__file__).parent.parent / "output"
    md_files = sorted(output_dir.glob("**/*_layout.md"))
    md_paths = [str(p) for p in md_files]
    
    if not md_paths:
        print("No markdown files found in output directory")
    else:
        print(f"Found {len(md_paths)} markdown files to process")
        main(md_paths)

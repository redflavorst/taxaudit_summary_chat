"""
Full Pipeline: PDF → Markdown → PostgreSQL → Elasticsearch → Qdrant

Usage:
    python pipeline_full.py                    # data_test 폴더의 모든 PDF 처리
    python pipeline_full.py --dir custom_dir   # 특정 폴더의 PDF 처리
    python pipeline_full.py --skip-pdf         # PDF 변환 스킵, 기존 markdown만 인제스트
"""

import argparse
import os
import sys
from pathlib import Path

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PGCLIENTENCODING'] = 'UTF8'

# PDF 처리
from pdf_layout import process_pdf, PipelineConfig

# DB 인제스트
sys.path.append(str(Path(__file__).parent / "create_db"))
from create_db.run_ingest import main as run_ingest
from create_db.config import settings


def process_pdfs_to_markdown(input_dir: str, output_dir: str) -> list[Path]:
    """
    PDF 파일들을 markdown으로 변환
    
    Returns:
        생성된 markdown 파일 경로 리스트
    """
    indir = Path(input_dir)
    if not indir.exists() or not indir.is_dir():
        raise SystemExit(f"Input directory not found: {indir}")
    
    pdf_paths = sorted([p for p in indir.glob("**/*.pdf") if p.is_file()])
    if not pdf_paths:
        print(f"No PDFs found in directory: {indir}")
        return []
    
    print(f"\n{'='*70}")
    print(f"Step 1/3: PDF → Markdown")
    print(f"{'='*70}")
    print(f"Found {len(pdf_paths)} PDF(s) in {indir}")
    
    markdown_paths = []
    
    for pdf_path in pdf_paths:
        stem = pdf_path.stem
        out_root = os.path.join(output_dir, stem)
        cfg = PipelineConfig(output_root=out_root)
        
        print(f"\nProcessing: {pdf_path.name}")
        outputs = process_pdf(str(pdf_path), cfg)
        
        # markdown 파일 경로 (.md)
        layout_md = Path(outputs["layout_md"])
        if layout_md.exists():
            markdown_paths.append(layout_md)
            print(f"  OK: {layout_md}")
        else:
            print(f"  Warning: Markdown not found: {layout_md}")
    
    return markdown_paths


def collect_existing_markdowns(output_dir: str) -> list[Path]:
    """
    output 폴더에서 기존 markdown 파일 수집
    """
    output_path = Path(output_dir)
    if not output_path.exists():
        return []
    
    markdown_paths = sorted(output_path.glob("**/*_layout.md"))
    return markdown_paths


def ingest_to_databases(markdown_paths: list[Path]):
    """
    Markdown 파일들을 PostgreSQL + Elasticsearch + Qdrant에 인제스트
    """
    if not markdown_paths:
        print("\nNo markdown files to ingest")
        return
    
    print(f"\n{'='*70}")
    print(f"Step 2/3: Markdown → PostgreSQL + Elasticsearch")
    print(f"{'='*70}")
    print(f"Ingesting {len(markdown_paths)} markdown file(s)")
    
    # DB 존재 확인 및 생성
    from create_db.create_database import create_database
    create_database()
    
    # run_ingest.py의 main 함수 호출
    md_path_strings = [str(p) for p in markdown_paths]
    run_ingest(md_path_strings)
    
    # Qdrant 업서트
    if settings.USE_QDRANT:
        print(f"\n{'='*70}")
        print(f"Step 3/3: Elasticsearch → Qdrant")
        print(f"{'='*70}")
        
        from create_db.vectorstore.upsert_vectors import run_all as upsert_vectorstore
        upsert_vectorstore()
    else:
        print(f"\n{'='*70}")
        print(f"Step 3/3: Qdrant (SKIPPED)")
        print(f"{'='*70}")
        print("USE_QDRANT=False in config.py")
        print("To enable: set USE_QDRANT=True in create_db/config.py")


def main():
    parser = argparse.ArgumentParser(
        description="Full pipeline: PDF → Markdown → PostgreSQL → Elasticsearch → Qdrant"
    )
    parser.add_argument(
        "--dir",
        dest="input_dir",
        default="data_test",
        help="Input directory containing PDFs (default: data_test)"
    )
    parser.add_argument(
        "--out",
        dest="output_dir",
        default="output",
        help="Output directory for markdowns (default: output)"
    )
    parser.add_argument(
        "--skip-pdf",
        action="store_true",
        help="Skip PDF conversion, only ingest existing markdowns"
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*70}")
    print(f"Full Pipeline Started")
    print(f"{'='*70}")
    print(f"Input dir: {args.input_dir}")
    print(f"Output dir: {args.output_dir}")
    print(f"Skip PDF conversion: {args.skip_pdf}")
    
    # Step 1: PDF → Markdown
    if args.skip_pdf:
        print("\nSkipping PDF conversion...")
        markdown_paths = collect_existing_markdowns(args.output_dir)
        print(f"Found {len(markdown_paths)} existing markdown files")
    else:
        markdown_paths = process_pdfs_to_markdown(args.input_dir, args.output_dir)
    
    # Step 2-3: Markdown → Databases
    ingest_to_databases(markdown_paths)
    
    print(f"\n{'='*70}")
    print(f"Full Pipeline Completed!")
    print(f"{'='*70}")
    print(f"Processed: {len(markdown_paths)} documents")
    print(f"PostgreSQL: OK")
    print(f"Elasticsearch: OK")
    print(f"Qdrant: {'OK' if settings.USE_QDRANT else 'SKIPPED'}")


if __name__ == "__main__":
    main()

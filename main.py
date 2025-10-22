# ==============================
# main.py
# ==============================
import argparse
import os
from pathlib import Path
from pdf_layout import process_pdf, PipelineConfig




def main():
    parser = argparse.ArgumentParser(description="PDF Layout Visualizer & Extractor")
    # Single-file mode remains supported, but optional
    parser.add_argument("pdf", nargs="?", help="Path to input PDF (optional if using --dir)")
    parser.add_argument("--dir", dest="indir", default="data_test", help="Directory containing PDFs to process")
    parser.add_argument("--out", dest="out", default="output", help="Output root directory (for batch: per-file subdirs)")
    args = parser.parse_args()

    # If a specific PDF is provided, run single-file mode
    if args.pdf:
        cfg = PipelineConfig(output_root=args.out)
        outputs = process_pdf(args.pdf, cfg)
        print("Input PDF:", args.pdf)
        print("Annotated PDF:", outputs["annotated_pdf"])
        print("Layout JSON:", outputs["layout_json"])
        print("Crops dir:", outputs["crops_dir"])
        return

    # Otherwise, batch process all PDFs in the directory (default: data_test)
    indir = Path(args.indir)
    if not indir.exists() or not indir.is_dir():
        raise SystemExit(f"Input directory not found: {indir}")

    pdf_paths = sorted([p for p in indir.glob("**/*.pdf") if p.is_file()])
    if not pdf_paths:
        raise SystemExit(f"No PDFs found in directory: {indir}")

    print(f"Found {len(pdf_paths)} PDF(s) in {indir}. Processing...")
    for pdf_path in pdf_paths:
        stem = pdf_path.stem
        out_root = os.path.join(args.out, stem)
        cfg = PipelineConfig(output_root=out_root)
        outputs = process_pdf(str(pdf_path), cfg)
        print("- Input PDF:", str(pdf_path))
        print("  Annotated PDF:", outputs["annotated_pdf"])
        print("  Layout JSON:", outputs["layout_json"])
        print("  Crops dir:", outputs["crops_dir"])




if __name__ == "__main__":
    main()

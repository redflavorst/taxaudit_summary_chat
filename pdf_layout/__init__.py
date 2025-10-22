# Project structure (all code in one canvas for convenience)
# ├─ main.py
# ├─ pdf_layout/
# │  ├─ __init__.py
# │  ├─ config.py
# │  ├─ utils.py
# │  ├─ detector.py
# │  ├─ cropper.py
# │  ├─ annotator.py
# │  ├─ exporter.py
# │  └─ pipeline.py
#
# Requirements: PyMuPDF (fitz), opencv-python, numpy, Pillow

# ==============================
# pdf_layout/__init__.py
# ==============================

from .pipeline import process_pdf
from .config import PipelineConfig

__all__ = ["process_pdf", "PipelineConfig"]










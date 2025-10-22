# ==============================
# pdf_layout/cropper.py
# ==============================
from typing import List, Tuple
import os
import cv2
import numpy as np
from PIL import Image

from .utils import BBox


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def crop_regions(image: np.ndarray, scale: float, pdf_bboxes: List[BBox], out_dir: str, prefix: str, fmt: str = "png") -> List[str]:
    """Crop regions from raster image using PDF coordinates scaled by `scale`. Returns list of saved paths (relative)."""
    ensure_dir(out_dir)
    paths: List[str] = []
    for idx, (x0p, y0p, x1p, y1p) in enumerate(pdf_bboxes):
        # map PDF → raster coordinates
        x0 = int(round(x0p * scale))
        y0 = int(round(y0p * scale))
        x1 = int(round(x1p * scale))
        y1 = int(round(y1p * scale))
        h, w = image.shape[:2]
        x0 = max(0, min(x0, w - 1))
        x1 = max(0, min(x1, w))
        y0 = max(0, min(y0, h - 1))
        y1 = max(0, min(y1, h))
        if x1 <= x0 or y1 <= y0:
            paths.append("")
            continue
        crop = image[y0:y1, x0:x1]
        rel = f"{prefix}_{idx:03d}.{fmt}"
        abspath = os.path.join(out_dir, rel)
        Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)).save(abspath)
        paths.append(rel)
    return paths


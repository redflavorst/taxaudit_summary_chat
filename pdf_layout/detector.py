# ==============================
# pdf_layout/detector.py
# ==============================
from typing import Dict, List, Tuple
import fitz  # PyMuPDF
import cv2
import numpy as np
from .utils import BBox, merge_overlapping


def page_to_image(page: fitz.Page, scale: float = 2.0) -> np.ndarray:
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return img


def detect_boxes(image: np.ndarray, min_height_threshold: float = 0.0) -> List[BBox]:
    """Detect large rectangular boxes (red_box candidates). Simple contour-based heuristic.
    
    Args:
        image: Input raster image
        min_height_threshold: Minimum height in raster pixels (0 = no filtering)
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 30, 120)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(edges, kernel, iterations=1)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: List[BBox] = []
    h, w = gray.shape
    min_area = (w * h) * 0.005
    max_area = (w * h) * 0.95
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch
        if min_area <= area <= max_area:
            aspect_ratio = max(cw, ch) / max(min(cw, ch), 1)
            if aspect_ratio < 50:
                if min_height_threshold > 0 and ch < min_height_threshold:
                    continue
                boxes.append((x, y, x + cw, y + ch))
    return boxes


def detect_table_candidates(image: np.ndarray) -> List[BBox]:
    """Detect table-like regions via line morphology. Returns all table candidates (to be classified)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 8)
    # Morphological line detection
    horizontalkernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    verticalkernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    horizontal = cv2.morphologyEx(thr, cv2.MORPH_OPEN, horizontalkernel, iterations=1)
    vertical = cv2.morphologyEx(thr, cv2.MORPH_OPEN, verticalkernel, iterations=1)
    tablemask = cv2.add(horizontal, vertical)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(tablemask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: List[BBox] = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w * h > 2000:  # heuristic
            boxes.append((x, y, x + w, y + h))
    return boxes


def expand_narrow_tables(boxes: List[BBox], image_width: int, max_width: int = 200) -> List[BBox]:
    """Expand narrow table boxes (likely header-only detection) to include right content.
    
    Args:
        boxes: List of table bounding boxes
        image_width: Width of the page image
        max_width: Maximum width to consider as "narrow" (default 200 pixels)
    
    Returns:
        List of expanded boxes
    """
    expanded = []
    for (x0, y0, x1, y1) in boxes:
        width = x1 - x0
        
        # If box is narrow (likely only header cell detected)
        if width < max_width:
            # Expand to right edge or 80% of page width
            new_x1 = min(image_width - 10, int(image_width * 0.8))
            expanded.append((x0, y0, new_x1, y1))
        else:
            expanded.append((x0, y0, x1, y1))
    
    return expanded


YELLOW_CONTAINS_ALL = ("적출", "항목코드")
YELLOW_PREFIX_KEYWORDS = ("개인", "법인", "개인·", "법인·")
YELLOW_HEADER_KEYWORDS = ("연번", "조사항목", "코드")


def classify_tables(page: fitz.Page, scale: float, tables: List[BBox]) -> Tuple[List[BBox], List[BBox], List[BBox]]:
    """Classify table candidates into blue_table (general) vs yellow_table vs law_table according to domain heuristics.
    
    Returns:
        (blue_tables, yellow_tables, law_tables)
    """
    blue: List[BBox] = []
    yellow: List[BBox] = []
    law: List[BBox] = []
    inv_scale = 1.0 / scale
    for (x0, y0, x1, y1) in tables:
        # map raster bbox back to PDF coordinates
        pdf_bbox = (x0 * inv_scale, y0 * inv_scale, x1 * inv_scale, y1 * inv_scale)
        text = page.get_textbox(pdf_bbox) or ""
        compact = "".join(text.split())
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        header = lines[0] if lines else ""
        header_compact = "".join(header.split())

        if header and header[0] in "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ":
            continue

        # Skip tables containing '조사우수사례 평가 보고서'
        if "조사우수사례평가보고서" in compact or ("조사우수사례" in compact and "평가보고서" in compact):
            continue

        # Check if it's a law table (법령, 예규, 판례)
        if compact.startswith("법령") or compact.startswith("예규") or compact.startswith("판례"):
            law.append((x0, y0, x1, y1))
            continue

        has_required_terms = all(keyword in compact for keyword in YELLOW_CONTAINS_ALL)
        header_startswith_personal = header_compact.startswith(YELLOW_PREFIX_KEYWORDS)
        header_has_keywords = all(keyword in header_compact for keyword in YELLOW_HEADER_KEYWORDS)

        if has_required_terms or header_startswith_personal or header_has_keywords:
            yellow.append((x0, y0, x1, y1))
        else:
            blue.append((x0, y0, x1, y1))
    return blue, yellow, law


def get_text_blocks(page: fitz.Page) -> List[Tuple[BBox, str]]:
    blocks = page.get_text("blocks")
    results: List[Tuple[BBox, str]] = []
    for b in blocks:
        if len(b) >= 5:
            x0, y0, x1, y1, txt = b[0], b[1], b[2], b[3], b[4]
            if txt and txt.strip():
                results.append(((x0, y0, x1, y1), txt))
    return results


def should_exclude_text_block(bbox: BBox, text: str, page_height: float, page_width: float = 595.0, 
                               table_boxes: List[BBox] = None) -> bool:
    """Check if a text block should be excluded from extraction.
    
    This is the main exclusion function. Add additional exclusion rules here.
    
    Args:
        bbox: Text block bounding box
        text: Text content
        page_height: Page height in PDF coordinates
        page_width: Page width in PDF coordinates (default A4: 595)
        table_boxes: List of table bounding boxes for proximity check
    
    Returns:
        True if the text block should be excluded
    """
    # Check footer (page numbers, etc.)
    if is_footer(bbox, text, page_height):
        return True
    
    # Check unit labels (e.g., "(백만원)", "단위:")
    if is_unit_label(bbox, text, page_width, table_boxes):
        return True
    
    # Add more exclusion rules here as needed
    # Example: if is_header(bbox, text, page_height): return True
    # Example: if is_watermark(bbox, text): return True
    
    return False


def is_footer(bbox: BBox, text: str, page_height: float) -> bool:
    """Check if a text block is a footer (page number, etc.).
    
    Footer criteria:
    - Located in bottom 10% of page
    - Short text (< 10 characters)
    - Contains digits
    
    Args:
        bbox: Text block bounding box
        text: Text content
        page_height: Page height in PDF coordinates
    
    Returns:
        True if the text block is likely a footer
    """
    import re
    
    x0, y0, x1, y1 = bbox
    text_stripped = text.strip()
    
    # Bottom 10% of page
    in_footer_area = y1 > page_height * 0.90
    
    # Short text
    is_short = len(text_stripped) < 10
    
    # Contains digits
    has_digits = bool(re.search(r'\d', text_stripped))
    
    return in_footer_area and is_short and has_digits


def is_unit_label(bbox: BBox, text: str, page_width: float, table_boxes: List[BBox] = None) -> bool:
    """Check if a text block is a unit label (e.g., '(백만원)', '단위:').
    
    Unit label criteria (hybrid approach):
    1. Keyword-based: Contains explicit unit keywords → always exclude
    2. Position-based: Right-aligned + short text + parentheses → exclude
    3. Proximity: Located just above a table (optional check)
    
    Args:
        bbox: Text block bounding box
        text: Text content
        page_width: Page width in PDF coordinates
        table_boxes: Optional list of table boxes for proximity check
    
    Returns:
        True if the text block is likely a unit label
    """
    x0, y0, x1, y1 = bbox
    text_stripped = text.strip()
    text_compact = "".join(text.split())
    
    # Criterion 1: Explicit unit keywords (highest priority)
    UNIT_KEYWORDS = ("단위:", "(단위", "백만원)", "천원)", "억원)", "원)", "(백만원", "(천원", "(억원")
    if any(keyword in text_compact for keyword in UNIT_KEYWORDS):
        return True
    
    # Criterion 2: Right-aligned + short + parentheses
    is_right_aligned = x0 > page_width * 0.70
    is_short = len(text_stripped) < 15
    has_parenthesis = "(" in text or ")" in text
    
    if is_right_aligned and is_short and has_parenthesis:
        # Optional: Check if above a table (within 30px)
        if table_boxes:
            for table_bbox in table_boxes:
                table_y0 = table_bbox[1]
                if y1 >= (table_y0 - 30) and y1 <= table_y0:
                    return True
        else:
            return True
    
    return False


def estimate_normal_text_height(doc: fitz.Document) -> float:
    """Estimate typical text height across all pages using histogram.
    
    Returns:
        Most common text height in PDF coordinates, or 12.0 as fallback
    """
    from collections import Counter
    
    heights = []
    for page in doc:
        blocks = page.get_text("blocks")
        for b in blocks:
            if len(b) >= 5:
                y0, y1, txt = b[1], b[3], b[4]
                if txt and txt.strip():
                    height = y1 - y0
                    if 5.0 <= height <= 50.0:
                        heights.append(round(height, 1))
    
    if not heights:
        return 12.0
    
    counter = Counter(heights)
    most_common_height = counter.most_common(1)[0][0]
    return most_common_height











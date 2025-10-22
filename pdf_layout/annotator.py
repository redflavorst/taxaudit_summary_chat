# ==============================
# pdf_layout/annotator.py
# ==============================
from typing import List, Sequence
import fitz

from .utils import BBox

COLOR_RGB = {
    "red": (1, 0, 0),
    "blue": (0, 0, 1),
    "yellow": (1, 1, 0),
    "purple": (0.5, 0, 0.5),
    "orange": (1, 0.5, 0),
}


def draw_rectangles(page: fitz.Page, items: List[Sequence], scale: float = 1.0, width: float = 1.5, font_size: float = 9.0) -> None:
    """Draw rectangles and optional labels. items: (pdf_bbox, color_name[, label])."""
    for item in items:
        if len(item) >= 3:
            (x0, y0, x1, y1), cname, label = item[0], item[1], item[2]
        else:
            (x0, y0, x1, y1), cname = item[:2]
            label = ""

        color = COLOR_RGB.get(cname, (0, 0, 0))
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(x0, y0, x1, y1))
        shape.finish(color=color, fill=None, width=width)
        shape.commit()

        if label:
            # Use darker text for readability on bright rectangles
            text_color = (0, 0, 0) if cname == "yellow" else color
            try:
                text_width = page.get_text_length(label, fontname="helv", fontsize=font_size)
            except AttributeError:
                # Fallback if get_text_length is unavailable
                text_width = len(label) * font_size * 0.5

            baseline_x = max(1.0, x0 - text_width - 4.0)
            baseline_y = max(font_size + 1.0, y0 + font_size)
            baseline = fitz.Point(baseline_x, baseline_y)
            page.insert_text(
                baseline,
                label,
                fontsize=font_size,
                fontname="helv",
                color=text_color,
                render_mode=0,
            )


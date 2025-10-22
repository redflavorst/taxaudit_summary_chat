# ==============================
# pdf_layout/pipeline.py
# ==============================
from typing import Dict, List, Tuple
import os
import fitz
import numpy as np

from .config import PipelineConfig
from .utils import BBox, iou, overlap_ratio, merge_overlapping, resolve_containment, remove_contained_boxes
from .detector import page_to_image, detect_boxes, detect_table_candidates, classify_tables, get_text_blocks, estimate_normal_text_height, should_exclude_text_block, expand_narrow_tables
from .cropper import crop_regions, ensure_dir
from .annotator import draw_rectangles
from .exporter import export_json, export_markdown

ANNOTATION_LABELS = {
    "red": "Region",
    "blue": "Table",
    "yellow": "Special",
    "purple": "Text",
    "orange": "Law",
}


def process_pdf(pdf_path: str, config: PipelineConfig = PipelineConfig()) -> Dict[str, str]:
    """Run full pipeline. Returns paths of outputs.
    Outputs:
      - annotated_pdf
      - layout_json
      - crops_dir
    """
    doc = fitz.open(pdf_path)
    out_root = config.output_root
    ensure_dir(out_root)

    # Prepare outputs
    annotated_path = os.path.join(out_root, os.path.splitext(os.path.basename(pdf_path))[0] + "_annotated.pdf")
    json_path = os.path.join(out_root, os.path.splitext(os.path.basename(pdf_path))[0] + "_layout.json")
    crops_root = os.path.join(out_root, "crops")
    ensure_dir(crops_root)

    # Estimate normal text height across all pages
    normal_text_height_pdf = estimate_normal_text_height(doc)
    min_box_height_pdf = normal_text_height_pdf * config.detection.text_height_multiplier
    scale = config.raster.scale
    min_box_height_raster = min_box_height_pdf * scale

    # Result aggregation for JSON
    json_pages: Dict[int, List[dict]] = {}

    # Work on a copy of the PDF for annotation (preserve vector content)
    adoc = fitz.open()
    adoc.insert_pdf(doc)

    for pidx in range(len(doc)):
        page = doc[pidx]
        # Raster for detection/crop
        raster = page_to_image(page, scale=scale)
        # --- Detect regions on raster ---
        red_raster_boxes = detect_boxes(raster, min_height_threshold=min_box_height_raster)
        table_candidates = detect_table_candidates(raster)
        
        # Expand narrow tables (likely header-only detections)
        image_width = raster.shape[1]
        table_candidates = expand_narrow_tables(table_candidates, image_width, max_width=200)

        # Merge duplicates on raster
        red_raster_boxes = merge_overlapping(red_raster_boxes, config.merge.iou)
        table_candidates = merge_overlapping(table_candidates, config.merge.iou)
        
        # Remove contained boxes within same type
        print(f"\n=== Page {pidx+1}: Before remove_contained_boxes ===")
        print(f"Red boxes: {len(red_raster_boxes)}, Table candidates: {len(table_candidates)}")
        
        red_raster_boxes = remove_contained_boxes(
            red_raster_boxes, 
            config.detection.containment_threshold,
            config.detection.size_ratio_threshold,
            debug=True
        )
        table_candidates = remove_contained_boxes(
            table_candidates, 
            config.detection.containment_threshold,
            config.detection.size_ratio_threshold,
            debug=True
        )
        
        print(f"=== Page {pidx+1}: After remove_contained_boxes ===")
        print(f"Red boxes: {len(red_raster_boxes)}, Table candidates: {len(table_candidates)}")

        # Classify tables using PDF text (map raster→PDF for sniffing)
        blue_raster, yellow_raster, law_from_tables = classify_tables(page, scale, table_candidates)
        print(f"\n=== Page {pidx+1}: After classify_tables ===")
        print(f"Blue tables: {len(blue_raster)}, Yellow tables: {len(yellow_raster)}, Law tables (from tables): {len(law_from_tables)}")

        # Prepare PDF-space bboxes
        inv = 1.0 / scale
        red_pdf = [(x0*inv, y0*inv, x1*inv, y1*inv) for (x0,y0,x1,y1) in red_raster_boxes]
        blue_pdf = [(x0*inv, y0*inv, x1*inv, y1*inv) for (x0,y0,x1,y1) in blue_raster]
        yellow_pdf = [(x0*inv, y0*inv, x1*inv, y1*inv) for (x0,y0,x1,y1) in yellow_raster]
        law_from_tables_pdf = [(x0*inv, y0*inv, x1*inv, y1*inv) for (x0,y0,x1,y1) in law_from_tables]

        min_table_height = max(0.0, config.detection.min_table_height)

        def _filter_shallow_tables(boxes: List[BBox]) -> List[BBox]:
            if min_table_height <= 0:
                return boxes
            filtered: List[BBox] = []
            for (x0, y0, x1, y1) in boxes:
                if (y1 - y0) >= min_table_height:
                    filtered.append((x0, y0, x1, y1))
            return filtered

        blue_pdf = _filter_shallow_tables(blue_pdf)
        yellow_pdf = _filter_shallow_tables(yellow_pdf)

        if yellow_pdf:
            def _filter_overlaps(boxes: List[BBox]) -> List[BBox]:
                filtered: List[BBox] = []
                for b in boxes:
                    if any(iou(b, yb) >= config.merge.iou for yb in yellow_pdf):
                        continue
                    filtered.append(b)
                return filtered

            red_pdf = _filter_overlaps(red_pdf)
            blue_pdf = _filter_overlaps(blue_pdf)

        # --- Resolve containment: red vs blue/yellow tables ---
        print(f"\n=== Page {pidx+1}: Before resolve_containment ===")
        print(f"Red (PDF): {len(red_pdf)}, Blue (PDF): {len(blue_pdf)}, Yellow (PDF): {len(yellow_pdf)}")
        
        all_tables = blue_pdf + yellow_pdf
        red_pdf, all_tables = resolve_containment(red_pdf, all_tables, config.detection.containment_threshold)
        
        # Split back into blue and yellow
        blue_pdf = [t for t in all_tables if t in blue_pdf]
        yellow_pdf = [t for t in all_tables if t in yellow_pdf]
        
        print(f"=== Page {pidx+1}: After resolve_containment ===")
        print(f"Red (PDF): {len(red_pdf)}, Blue (PDF): {len(blue_pdf)}, Yellow (PDF): {len(yellow_pdf)}")

        # --- Process law tables from both red boxes and table classification ---
        # Start with law tables detected from table classification
        law_pdf = list(law_from_tables_pdf)
        law_metadata = []  # Store (bbox, law_type, law_name, law_content)
        
        # Reclassify red boxes containing "법령" as law_table (orange) and split by '법령' keyword
        remaining_red_pdf = []
        
        def _detect_law_type(text: str) -> str:
            """법령 타입 감지: 법령, 예규, 판례"""
            first_line = text.strip().split('\n')[0] if text.strip() else ""
            if "예규" in first_line:
                return "예규"
            elif "판례" in first_line:
                return "판례"
            else:
                return "법령"
        
        def _parse_law_info(text: str):
            """법령 텍스트에서 law_name, law_content 추출"""
            lines = text.strip().split('\n')
            if not lines:
                return "", ""
            
            # 첫 줄이 "법령"/"예규"/"판례"이면 제거
            if lines[0].strip() in ["법령", "예규", "판례"]:
                lines = lines[1:]
            
            if not lines:
                return "", ""
            
            # 첫 줄: law_name (법령명)
            law_name = lines[0].strip()
            
            # 나머지 전부: law_content
            law_content = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ""
            
            return law_name, law_content
        
        # Process law tables from table classification first
        for bbox in law_from_tables_pdf:
            text = page.get_textbox(bbox) or ""
            law_type = _detect_law_type(text)
            law_name, law_content = _parse_law_info(text)
            law_metadata.append((bbox, law_type, law_name, law_content))
        
        # Then process red boxes
        for bbox in red_pdf:
            text = page.get_textbox(bbox) or ""
            text_compact = "".join(text.split())
            if text_compact.startswith("법령") or text_compact.startswith("예규") or text_compact.startswith("판례"):
                # Split by '법령\n' pattern to separate multiple laws
                import re
                law_parts = re.split(r'\n법령\n', text)
                
                if len(law_parts) == 1:
                    # Single law in this box
                    law_type = _detect_law_type(text)
                    law_name, law_content = _parse_law_info(text)
                    law_pdf.append(bbox)
                    law_metadata.append((bbox, law_type, law_name, law_content))
                else:
                    # Multiple laws - need to split bbox by text blocks
                    text_blocks = page.get_text("blocks", clip=fitz.Rect(*bbox))
                    
                    # Find '법령' blocks to determine split points
                    law_indices = []
                    for idx, block in enumerate(text_blocks):
                        if len(block) >= 5:
                            block_text = block[4].strip()
                            if block_text == "법령":
                                law_indices.append(idx)
                    
                    # Create bbox for each law section
                    if law_indices:
                        x0, y0, x1, y1 = bbox
                        for i, start_idx in enumerate(law_indices):
                            # Find y-coordinates for this law section
                            start_y = text_blocks[start_idx][1]  # y0 of '법령' block
                            
                            # End y is either next '법령' or bbox bottom
                            if i + 1 < len(law_indices):
                                end_y = text_blocks[law_indices[i + 1]][1]
                            else:
                                end_y = y1
                            
                            split_bbox = (x0, start_y, x1, end_y)
                            split_text = page.get_textbox(fitz.Rect(*split_bbox)) or ""
                            law_type = _detect_law_type(split_text)
                            law_name, law_content = _parse_law_info(split_text)
                            law_pdf.append(split_bbox)
                            law_metadata.append((split_bbox, law_type, law_name, law_content))
                    else:
                        # Fallback: treat as single law
                        law_type = _detect_law_type(text)
                        law_name, law_content = _parse_law_info(text)
                        law_pdf.append(bbox)
                        law_metadata.append((bbox, law_type, law_name, law_content))
            else:
                remaining_red_pdf.append(bbox)
        red_pdf = remaining_red_pdf
        
        print(f"\n=== Page {pidx+1}: After law_table reclassification ===")
        print(f"Red (PDF): {len(red_pdf)}, Law (PDF): {len(law_pdf)}, Blue (PDF): {len(blue_pdf)}, Yellow (PDF): {len(yellow_pdf)}")

        # --- Crop images for red, blue, and law ---
        page_crop_dir = os.path.join(crops_root, f"page_{pidx+1:03d}")
        ensure_dir(page_crop_dir)
        red_paths_rel = crop_regions(raster, scale, red_pdf, page_crop_dir, prefix="red", fmt=config.raster.crop_format)
        blue_paths_rel = crop_regions(raster, scale, blue_pdf, page_crop_dir, prefix="blue", fmt=config.raster.crop_format)
        law_paths_rel = crop_regions(raster, scale, law_pdf, page_crop_dir, prefix="law", fmt=config.raster.crop_format)

        # --- Text blocks (PDF space) ---
        blocks = get_text_blocks(page)
        page_height = page.rect.height
        page_width = page.rect.width

        # Exclude blocks overlapping red/blue/yellow (already captured elsewhere)
        keep_blocks: List[Tuple[BBox, str]] = []
        all_table_boxes = blue_pdf + yellow_pdf
        for (bb, txt) in blocks:
            # Check if should be excluded (footer, header, unit labels, etc.)
            if should_exclude_text_block(bb, txt, page_height, page_width, all_table_boxes):
                continue
            
            # Compute overlap ratios versus red & blue
            drop = False
            for rb in red_pdf:
                if overlap_ratio(bb, rb) >= config.exclude.overlap_threshold or iou(bb, rb) >= config.exclude.iou_threshold:
                    drop = True
                    break
            if drop:
                continue
            for bbx in blue_pdf:
                if overlap_ratio(bb, bbx) >= config.exclude.overlap_threshold or iou(bb, bbx) >= config.exclude.iou_threshold:
                    drop = True
                    break
            if drop:
                continue
            for yb in yellow_pdf:
                if overlap_ratio(bb, yb) >= config.exclude.overlap_threshold or iou(bb, yb) >= config.exclude.iou_threshold:
                    drop = True
                    break
            if drop:
                continue
            for lb in law_pdf:
                if overlap_ratio(bb, lb) >= config.exclude.overlap_threshold or iou(bb, lb) >= config.exclude.iou_threshold:
                    drop = True
                    break
            if not drop:
                keep_blocks.append((bb, txt))

        # Build annotation items
        ann_items = []
        for b in red_pdf:
            ann_items.append((b, "red", ANNOTATION_LABELS["red"]))
        for b in blue_pdf:
            ann_items.append((b, "blue", ANNOTATION_LABELS["blue"]))
        for b in yellow_pdf:
            ann_items.append((b, "yellow", ANNOTATION_LABELS["yellow"]))
        for b in law_pdf:
            ann_items.append((b, "orange", ANNOTATION_LABELS["orange"]))
        for (b, _) in keep_blocks:
            ann_items.append((b, "purple", ANNOTATION_LABELS["purple"]))

        # Draw overlays directly on copied original page to retain PDF fidelity
        apage = adoc[pidx]
        draw_rectangles(apage, ann_items, scale=1.0, width=1.5)

        # --- JSON collect ---
        page_items: List[dict] = []
        # red
        for bbox, rel in zip(red_pdf, red_paths_rel):
            item = {
                "type": "red_box",
                "color": "red",
                "bbox": [round(bbox[0],2), round(bbox[1],2), round(bbox[2],2), round(bbox[3],2)],
                "y0": round(bbox[1],2),
                "path": os.path.join(f"crops/page_{pidx+1:03d}", rel) if rel else ""
            }
            page_items.append(item)
        # blue
        for bbox, rel in zip(blue_pdf, blue_paths_rel):
            item = {
                "type": "blue_table",
                "color": "blue",
                "bbox": [round(bbox[0],2), round(bbox[1],2), round(bbox[2],2), round(bbox[3],2)],
                "y0": round(bbox[1],2),
                "path": os.path.join(f"crops/page_{pidx+1:03d}", rel) if rel else ""
            }
            page_items.append(item)
        # yellow
        for bbox in yellow_pdf:
            text = page.get_textbox(fitz.Rect(*bbox)) or ""
            item = {
                "type": "yellow_table",
                "color": "yellow",
                "bbox": [round(bbox[0],2), round(bbox[1],2), round(bbox[2],2), round(bbox[3],2)],
                "y0": round(bbox[1],2),
                "content": text.strip()
            }
            page_items.append(item)
        # law (orange) - with law_type, law_name, law_content
        for (bbox, law_type, law_name, law_content), rel in zip(law_metadata, law_paths_rel):
            item = {
                "type": "law_table",
                "color": "orange",
                "bbox": [round(bbox[0],2), round(bbox[1],2), round(bbox[2],2), round(bbox[3],2)],
                "y0": round(bbox[1],2),
                "path": os.path.join(f"crops/page_{pidx+1:03d}", rel) if rel else "",
                "law_type": law_type,
                "law_name": law_name,
                "law_content": law_content
            }
            page_items.append(item)
        # purple texts
        for bbox, txt in keep_blocks:
            item = {
                "type": "purple_text",
                "color": "purple",
                "bbox": [round(bbox[0],2), round(bbox[1],2), round(bbox[2],2), round(bbox[3],2)],
                "y0": round(bbox[1],2),
                "content": txt.strip()
            }
            page_items.append(item)

        json_pages[pidx + 1] = page_items

    # Save annotated PDF
    adoc.save(annotated_path)
    adoc.close()
    # Save JSON
    export_json(json_pages, json_path)
    markdown_path = os.path.splitext(json_path)[0] + ".md"
    export_markdown(json_pages, markdown_path)

    doc.close()

    return {
        "annotated_pdf": annotated_path,
        "layout_json": json_path,
        "layout_md": markdown_path,
        "crops_dir": crops_root
    }


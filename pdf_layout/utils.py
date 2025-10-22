# ==============================
# pdf_layout/utils.py
# ==============================
from typing import List, Tuple
import math

BBox = Tuple[float, float, float, float]  # x0, y0, x1, y1


def area(b: BBox) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def intersect(a: BBox, b: BBox) -> float:
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def iou(a: BBox, b: BBox) -> float:
    inter = intersect(a, b)
    denom = area(a) + area(b) - inter
    return inter / denom if denom > 0 else 0.0


def overlap_ratio(block: BBox, mask: BBox) -> float:
    inter = intersect(block, mask)
    a = area(block)
    return inter / a if a > 0 else 0.0


def merge_overlapping(bboxes: List[BBox], thr: float) -> List[BBox]:
    """Greedy merge for highly overlapping boxes (IoU > thr)."""
    boxes = bboxes[:]
    merged = []
    while boxes:
        base = boxes.pop(0)
        has_merged = False
        for i, other in enumerate(boxes):
            if iou(base, other) > thr:
                x0 = min(base[0], other[0])
                y0 = min(base[1], other[1])
                x1 = max(base[2], other[2])
                y1 = max(base[3], other[3])
                boxes[i] = (x0, y0, x1, y1)
                has_merged = True
                break
        if not has_merged:
            merged.append(base)
    return merged


def contains(outer: BBox, inner: BBox, threshold: float = 0.8) -> bool:
    """Check if inner is contained within outer by threshold ratio.
    
    Args:
        outer: The potentially containing box
        inner: The potentially contained box
        threshold: Minimum ratio of inner's area inside outer (default 0.8 = 80%)
    
    Returns:
        True if inner is contained in outer by at least threshold ratio
    """
    inter = intersect(outer, inner)
    inner_area = area(inner)
    if inner_area == 0:
        return False
    return (inter / inner_area) >= threshold


def remove_contained_boxes(boxes: List[BBox], threshold: float = 0.5, size_ratio: float = 0.2, debug: bool = False) -> List[BBox]:
    """Remove smaller boxes that are contained within larger boxes of the same type.
    
    Two removal criteria:
    1. Containment: Small box is contained in large box by threshold ratio (default 50%)
    2. Size ratio: Small box area < 20% of large box area
    
    Args:
        boxes: List of boxes to filter
        threshold: Containment threshold (default 0.5 = 50%)
        size_ratio: Maximum size ratio for automatic removal (default 0.2 = 20%)
        debug: Print debug information
    
    Returns:
        Filtered list with contained boxes removed
    """
    if len(boxes) <= 1:
        return boxes
    
    # Sort by area (largest first)
    sorted_boxes = sorted(boxes, key=lambda b: area(b), reverse=True)
    filtered = []
    
    if debug:
        print(f"\n[remove_contained_boxes] Processing {len(boxes)} boxes")
        for i, b in enumerate(sorted_boxes):
            print(f"  Box {i}: area={area(b):.1f}, bbox={[round(x,1) for x in b]}")
    
    for idx, box in enumerate(sorted_boxes):
        should_remove = False
        removal_reason = ""
        box_area = area(box)
        
        # Check against all larger boxes already in filtered
        for larger_idx, larger_box in enumerate(filtered):
            larger_area = area(larger_box)
            inter = intersect(larger_box, box)
            
            containment_ratio = (inter / box_area) if box_area > 0 else 0
            size_ratio_actual = (box_area / larger_area) if larger_area > 0 else 1
            overlap_ratio = (inter / box_area) if box_area > 0 else 0
            
            # Criterion 1: Containment ratio
            if contains(larger_box, box, threshold):
                should_remove = True
                removal_reason = f"Containment: {containment_ratio:.2%} >= {threshold:.2%}"
                break
            
            # Criterion 2: Size ratio (box is much smaller than larger_box)
            if box_area > 0 and larger_area > 0:
                if box_area < larger_area * size_ratio:
                    # Additional check: boxes should overlap significantly
                    if inter > box_area * 0.5:
                        should_remove = True
                        removal_reason = f"Size ratio: {size_ratio_actual:.2%} < {size_ratio:.2%}, Overlap: {overlap_ratio:.2%}"
                        break
            
            if debug:
                if inter > 0:
                    print(f"  Box {idx} vs Larger {larger_idx}: contain={containment_ratio:.2%}, size={size_ratio_actual:.2%}, overlap={overlap_ratio:.2%}")
                else:
                    print(f"  Box {idx} vs Larger {larger_idx}: NO OVERLAP")
        
        if should_remove:
            if debug:
                print(f"  [X] Box {idx} REMOVED: {removal_reason}")
        else:
            filtered.append(box)
            if debug:
                print(f"  [OK] Box {idx} KEPT (area={box_area:.1f})")
    
    if debug:
        print(f"[remove_contained_boxes] Result: {len(filtered)}/{len(boxes)} boxes kept")
        print()
    
    return filtered


def resolve_containment(red_boxes: List[BBox], table_boxes: List[BBox], 
                        threshold: float = 0.8) -> Tuple[List[BBox], List[BBox]]:
    """Resolve containment conflicts between red boxes and tables.
    
    Priority: Larger structure wins
    - If red is contained in table → remove red
    - If table is contained in red → remove table
    
    Args:
        red_boxes: List of red region boxes
        table_boxes: List of table boxes (blue/yellow)
        threshold: Containment threshold (default 0.8 = 80%)
    
    Returns:
        Tuple of (filtered_red_boxes, filtered_table_boxes)
    """
    filtered_red = []
    filtered_tables = list(table_boxes)
    
    for red in red_boxes:
        contained_in_table = False
        tables_to_remove = []
        
        for i, table in enumerate(filtered_tables):
            if contains(table, red, threshold):
                contained_in_table = True
                break
            elif contains(red, table, threshold):
                tables_to_remove.append(i)
        
        if not contained_in_table:
            filtered_red.append(red)
            for idx in reversed(tables_to_remove):
                filtered_tables.pop(idx)
    
    return filtered_red, filtered_tables

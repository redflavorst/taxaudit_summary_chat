# ==============================
# pdf_layout/config.py
# ==============================
from dataclasses import dataclass, field
from typing import Tuple, Dict


@dataclass
class ColorMap:
    red_box: str = "red"
    blue_table: str = "blue"
    yellow_table: str = "yellow"
    purple_text: str = "purple"


@dataclass
class ExcludeThreshold:
    overlap_threshold: float = 0.08  # block ?��?겹침 비율
    iou_threshold: float = 0.10      # 보조 기�?


@dataclass
class RasterConfig:
    scale: float = 2.0               # 2x raster
    dpi: int = 288                   # optional: not used when scale given
    crop_format: str = "png"


@dataclass
class MergeConfig:
    iou: float = 0.90                # 같�? ?�형 중복 병합 기�?


@dataclass
class DetectionConfig:
    min_table_height: float = 24.0
    text_height_multiplier: float = 1.5
    containment_threshold: float = 0.5
    size_ratio_threshold: float = 0.2


@dataclass
class PipelineConfig:
    output_root: str = "output"
    color_map: ColorMap = field(default_factory=ColorMap)
    exclude: ExcludeThreshold = field(default_factory=ExcludeThreshold)
    raster: RasterConfig = field(default_factory=RasterConfig)
    merge: MergeConfig = field(default_factory=MergeConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)


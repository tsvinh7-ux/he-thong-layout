"""Đọc mẫu layout (template) và bảng ánh xạ style."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

MM = 72 / 25.4  # 1 mm = 2.8346 pt

DATA_DIR = Path(__file__).parent / "data"

DEFAULTS: dict = {
    "name": "",
    "indt": None,
    "page": {"width_mm": 190, "height_mm": 270, "bleed_mm": 3, "facing_pages": True},
    "margins_mm": {"top": 20, "bottom": 22, "inside": 22, "outside": 16},
    "columns": {"count": 1, "gutter_mm": 5},
    "chapter_start": "recto",
    "color": {
        "cmyk_profile": "Coated FOGRA39 (ISO 12647-2:2004)",
        "rgb_profile": "sRGB IEC61966-2.1",
        "icc_file": None,
        "rendering_intent": "perceptual",
        "black_point_compensation": True,
        "gray_images": "keep",
        "tac_limit": 300,
    },
    "images": {
        "min_ppi": 300,
        "error_ppi": 200,
        "sizing": "natural_max_column",
        "max_height_ratio": 0.85,
    },
    "pdf": {
        "standard": "PDFX4",
        "preset_name": "HTL Offset PDF-X4",
        "crop_marks": True,
        "registration_marks": True,
        "page_information_marks": True,
        "marks_offset_mm": 4.5,
    },
    "roles": {},
    "character_styles": {"bold": "Bold", "italic": "Italic", "bold_italic": "Bold Italic"},
    "table_style": "HTL Table",
    "fonts": {},
    "paragraph_styles": {},
    "swatches": {},
    "style_map": None,
    "caption_patterns": {
        "figure": r"^\s*(Hình|Figure|Fig\.?|Ảnh|Sơ đồ|Biểu đồ)\s*[\dIVXivx]",
        "table": r"^\s*(Bảng|Table)\s*[\dIVXivx]",
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class Template:
    path: Path
    data: dict

    def __getitem__(self, key):
        return self.data[key]

    # --- Kích thước tính sẵn (pt) -------------------------------------------
    @property
    def page_w(self) -> float:
        return self.data["page"]["width_mm"] * MM

    @property
    def page_h(self) -> float:
        return self.data["page"]["height_mm"] * MM

    @property
    def text_w(self) -> float:
        m = self.data["margins_mm"]
        return self.page_w - (m["inside"] + m["outside"]) * MM

    @property
    def text_h(self) -> float:
        m = self.data["margins_mm"]
        return self.page_h - (m["top"] + m["bottom"]) * MM

    @property
    def column_w(self) -> float:
        c = self.data["columns"]
        n = max(1, int(c["count"]))
        return (self.text_w - (n - 1) * c["gutter_mm"] * MM) / n

    def style_for(self, role: str) -> str:
        roles = self.data["roles"]
        if role in roles:
            return roles[role]
        # role chưa khai báo: dùng tên role làm tên style
        return role

    def to_job(self) -> dict:
        """Phần cấu hình chuyển cho script InDesign."""
        d = copy.deepcopy(self.data)
        d["computed"] = {
            "page_w": self.page_w,
            "page_h": self.page_h,
            "text_w": self.text_w,
            "text_h": self.text_h,
            "column_w": self.column_w,
        }
        if d.get("indt"):
            d["indt"] = str((self.path.parent / d["indt"]).resolve())
        return d


def load_template(path: str | Path) -> Template:
    path = Path(path)
    if path.is_dir():
        path = path / "template.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Template(path=path, data=_merge(DEFAULTS, data))


# ---------------------------------------------------------------------------
# Bảng ánh xạ style Word -> role
# ---------------------------------------------------------------------------

@dataclass
class StyleMap:
    rules: list[tuple[re.Pattern, str]]

    def role(self, style_name: str) -> str | None:
        name = (style_name or "").strip()
        for pat, role in self.rules:
            if pat.fullmatch(name):
                return role
        return None


def _load_rules(path: Path) -> list[tuple[re.Pattern, str]]:
    with open(path, encoding="utf-8") as f:
        items = yaml.safe_load(f) or []
    return [(re.compile(i["pattern"], re.IGNORECASE), i["role"]) for i in items]


def load_style_map(*extra: str | Path | None) -> StyleMap:
    rules: list = []
    for p in extra:
        if p:
            rules += _load_rules(Path(p))
    rules += _load_rules(DATA_DIR / "default_style_map.yaml")
    return StyleMap(rules)

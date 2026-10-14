"""Xử lý ảnh cho in offset.

- Ghép ảnh gốc độ phân giải cao (nếu có) thay cho ảnh nhúng trong Word.
- Tính kích thước đặt ảnh và độ phân giải hiệu dụng (effective ppi).
- Chuyển RGB -> CMYK bằng ICC profile của nhà in (nếu được cung cấp).
- KHÔNG BAO GIỜ phóng to (upscale) ảnh: ảnh thiếu độ phân giải chỉ được cảnh báo.
"""
from __future__ import annotations

import csv
import io
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageCms

from .config import Template
from .ir import Book, Figure, Paragraph, iter_blocks
from .report import Report

Image.MAX_IMAGE_PIXELS = 400_000_000

RASTER_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".psd", ".webp"}
PLACEABLE_AS_IS = {".eps", ".ai", ".pdf", ".psd"}  # InDesign đặt trực tiếp, giữ nguyên vector/lớp
_INTENTS = {
    "perceptual": ImageCms.Intent.PERCEPTUAL,
    "relative": ImageCms.Intent.RELATIVE_COLORIMETRIC,
    "saturation": ImageCms.Intent.SATURATION,
    "absolute": ImageCms.Intent.ABSOLUTE_COLORIMETRIC,
}


@dataclass
class PlacedImage:
    id: str
    file: str  # tên file trong thư mục images/ của bản dựng
    source: str
    px_w: int
    px_h: int
    w_pt: float
    h_pt: float
    ppi: float
    color: str
    caption: str = ""

    def to_job(self) -> dict:
        return self.__dict__.copy()


# ---------------------------------------------------------------------------
# Ghép ảnh gốc
# ---------------------------------------------------------------------------

def _num_key(text: str) -> tuple[int, ...] | None:
    """'Hình 3.12. Siêu âm ...' -> (3, 12);  'Fig03-12_hires.tif' -> (3, 12)."""
    m = re.search(r"(\d+)(?:\s*[.\-_–]\s*(\d+))?", text)
    if not m:
        return None
    return tuple(int(x) for x in m.groups() if x is not None)


def _file_key(name: str) -> tuple[int, ...] | None:
    nums = [int(x) for x in re.findall(r"\d+", Path(name).stem)]
    if not nums:
        return None
    return tuple(nums[-2:]) if len(nums) >= 2 else (nums[0],)


def match_hires(book: Book, hires_dir: Path | None, map_csv: Path | None, report: Report) -> None:
    """Thay ảnh nhúng bằng ảnh gốc. Ưu tiên: file CSV ánh xạ > khớp theo số hình trong chú thích."""
    explicit: dict[str, str] = {}
    if map_csv:
        with open(map_csv, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("figure_id") and row.get("file"):
                    explicit[row["figure_id"].strip()] = row["file"].strip()
    files: list[Path] = []
    if hires_dir:
        files = [p for p in Path(hires_dir).rglob("*") if p.is_file() and not p.name.startswith(".")]
    by_key: dict[tuple, list[Path]] = {}
    for p in files:
        k = _file_key(p.name)
        if k:
            by_key.setdefault(k, []).append(p)

    for ch in book.chapters:
        flat = list(iter_blocks(ch.blocks))
        for i, b in enumerate(flat):
            if not isinstance(b, Figure):
                continue
            if b.id in explicit:
                p = Path(explicit[b.id])
                if not p.is_absolute() and hires_dir:
                    p = Path(hires_dir) / p
                if p.exists():
                    b.image = str(p)
                    continue
                report.error(f"{b.id}: file ảnh trong bảng ánh xạ không tồn tại: {p}")
                continue
            if not hires_dir:
                continue
            cap = ""
            for j in (i + 1, i - 1):
                if 0 <= j < len(flat) and isinstance(flat[j], Paragraph) and flat[j].role == "caption":
                    cap = flat[j].text
                    break
            k = _num_key(cap) if cap else None
            cands = by_key.get(k, []) if k else []
            if len(cands) == 1:
                b.image = str(cands[0])
                report.info(f"{b.id}: dùng ảnh gốc {cands[0].name} (khớp '{cap[:40]}').")
            elif len(cands) > 1:
                report.error(f"{b.id}: nhiều ảnh gốc cùng khớp '{cap[:40]}': "
                             f"{', '.join(c.name for c in cands)} — chỉ định trong file ánh xạ CSV.")
            else:
                report.warn(f"{b.id}: không tìm thấy ảnh gốc cho '{cap[:40] or '(không có chú thích)'}' — dùng ảnh nhúng trong Word.")


# ---------------------------------------------------------------------------
# Kích thước và màu
# ---------------------------------------------------------------------------

def target_size(px_w: int, px_h: int, tpl: Template) -> tuple[float, float]:
    """Kích thước đặt ảnh (pt). Không vượt quá cột chữ và chiều cao tối đa."""
    cfg = tpl["images"]
    col_w = tpl.column_w
    max_h = tpl.text_h * cfg["max_height_ratio"]
    if cfg["sizing"] == "column":
        w = col_w
    else:  # natural_max_column: không đặt lớn hơn kích thước đạt min_ppi
        w = min(col_w, px_w / cfg["min_ppi"] * 72)
    h = w * px_h / px_w
    if h > max_h:
        h = max_h
        w = h * px_w / px_h
    return w, h


def _to_cmyk(im: Image.Image, dest_icc: Path, intent: str, bpc: bool) -> Image.Image:
    src_bytes = im.info.get("icc_profile")
    src = ImageCms.ImageCmsProfile(io.BytesIO(src_bytes)) if src_bytes else ImageCms.createProfile("sRGB")
    if im.mode in ("RGBA", "LA", "P", "PA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")
    flags = ImageCms.Flags.BLACKPOINTCOMPENSATION if bpc else ImageCms.Flags.NONE
    dst = ImageCms.ImageCmsProfile(str(dest_icc))
    tr = ImageCms.buildTransform(src, dst, "RGB", "CMYK", renderingIntent=_INTENTS[intent], flags=flags)
    out = ImageCms.applyTransform(im, tr)
    out.info["icc_profile"] = dst.tobytes()
    return out


def process_images(book: Book, tpl: Template, out_dir: Path, report: Report) -> dict[str, PlacedImage]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg_c = tpl["color"]
    cfg_i = tpl["images"]
    icc = cfg_c.get("icc_file")
    icc_path = None
    if icc:
        icc_path = Path(icc)
        if not icc_path.is_absolute():
            icc_path = tpl.path.parent / icc_path
        if not icc_path.exists():
            report.error(f"Không tìm thấy ICC profile: {icc_path}")
            icc_path = None
    if not icc_path:
        report.info("Không có ICC profile CMYK của nhà in: ảnh RGB giữ nguyên, InDesign sẽ chuyển sang CMYK "
                    f"('{cfg_c['cmyk_profile']}') khi xuất PDF/X.")

    placed: dict[str, PlacedImage] = {}
    for ch in book.chapters:
        flat = list(iter_blocks(ch.blocks))
        for i, fig in enumerate(flat):
            if not isinstance(fig, Figure):
                continue
            cap = ""
            for j in (i + 1, i - 1):
                if 0 <= j < len(flat) and isinstance(flat[j], Paragraph) and flat[j].role == "caption":
                    cap = flat[j].text
                    break
            if not fig.image:
                report.error(f"{fig.id} ({ch.id}): thiếu ảnh — {fig.source_name}.")
                continue
            src = Path(fig.image)
            if not src.exists():
                report.error(f"{fig.id} ({ch.id}): không tìm thấy file ảnh {src}.")
                continue
            ext = src.suffix.lower()
            if ext in (".emf", ".wmf"):
                report.error(f"{fig.id}: ảnh {src.name} là Windows Metafile — InDesign trên Mac không đặt được và "
                             "chất lượng in không bảo đảm. Cần ảnh gốc (TIFF/PSD/EPS/PDF).")
                dst = out_dir / f"{fig.id}{ext}"
                shutil.copy2(src, dst)
                placed[fig.id] = PlacedImage(fig.id, dst.name, str(src), 0, 0, tpl.column_w,
                                             tpl.column_w * 0.6, 0, "metafile", cap)
                continue
            if ext in PLACEABLE_AS_IS - {".psd"} or ext not in RASTER_EXT:
                dst = out_dir / f"{fig.id}{ext}"
                shutil.copy2(src, dst)
                report.warn(f"{fig.id}: {src.name} được đặt nguyên trạng (vector/định dạng đặc biệt) — designer kiểm tra màu và kích thước.")
                placed[fig.id] = PlacedImage(fig.id, dst.name, str(src), 0, 0, tpl.column_w,
                                             tpl.column_w * 0.6, 0, "as-is", cap)
                continue
            with Image.open(src) as im:
                im.load()
                px_w, px_h = im.size
                w_pt, h_pt = target_size(px_w, px_h, tpl)
                ppi = px_w / (w_pt / 72)
                mode = im.mode
                if mode in ("1", "L", "LA", "I;16", "I"):
                    if cfg_c.get("gray_images") == "cmyk" and icc_path:
                        out_im = _to_cmyk(im.convert("RGB"), icc_path, cfg_c["rendering_intent"], cfg_c["black_point_compensation"])
                        color = "cmyk"
                    else:
                        out_im = im if mode in ("1", "L") else im.convert("L")
                        color = "bitmap" if mode == "1" else "gray"
                elif mode == "CMYK":
                    out_im = im
                    color = "cmyk"
                    report.info(f"{fig.id}: ảnh đã ở CMYK — giữ nguyên số liệu màu.")
                elif icc_path:
                    out_im = _to_cmyk(im, icc_path, cfg_c["rendering_intent"], cfg_c["black_point_compensation"])
                    color = "cmyk"
                else:
                    out_im = im.convert("RGBA") if mode in ("P", "PA", "RGBA", "LA") else im.convert("RGB")
                    color = "rgb"
                dst = out_dir / f"{fig.id}.tif"
                save_kw = {"compression": "tiff_lzw", "dpi": (round(ppi), round(ppi))}
                if out_im.info.get("icc_profile"):
                    save_kw["icc_profile"] = out_im.info["icc_profile"]
                elif im.info.get("icc_profile") and out_im is im:
                    save_kw["icc_profile"] = im.info["icc_profile"]
                out_im.save(dst, **save_kw)

            label = f"{fig.id} ({src.name}, {px_w}×{px_h}px, đặt {w_pt / 72 * 25.4:.0f}×{h_pt / 72 * 25.4:.0f} mm)"
            if ppi < cfg_i["error_ppi"]:
                report.error(f"{label}: độ phân giải hiệu dụng {ppi:.0f} ppi < {cfg_i['error_ppi']} — không đủ chất lượng in, cần ảnh gốc.")
            elif ppi < cfg_i["min_ppi"] - 0.5:
                report.warn(f"{label}: độ phân giải hiệu dụng {ppi:.0f} ppi < {cfg_i['min_ppi']} — nên thay ảnh gốc.")
            if w_pt < tpl.column_w * 0.5 and cfg_i["sizing"] != "column":
                report.warn(f"{label}: ảnh nhỏ (chỉ đủ {w_pt / tpl.column_w:.0%} bề rộng cột ở {cfg_i['min_ppi']} ppi) — cần ảnh gốc lớn hơn nếu muốn đặt to.")
            placed[fig.id] = PlacedImage(fig.id, dst.name, str(src), px_w, px_h, w_pt, h_pt, ppi, color, cap)
    return placed

"""Kiểm tra kỹ thuật PDF trước khi gửi nhà in (preflight).

Đây là lớp kiểm tra tự động nhanh để bắt lỗi phổ biến. Bản cuối vẫn nên
được kiểm bằng công cụ chuẩn ngành (Acrobat Preflight / callas pdfToolbox /
Enfocus PitStop) theo profile do nhà in cung cấp.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import MM, Template


@dataclass
class PreflightResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_markdown(self) -> str:
        lines = ["# Báo cáo preflight PDF", "",
                 f"**Kết quả:** {'ĐẠT' if self.ok else 'KHÔNG ĐẠT'}", ""]
        for head, items in (("Lỗi", self.errors), ("Cảnh báo", self.warnings), ("Thông tin", self.infos)):
            lines.append(f"## {head} ({len(items)})")
            lines += [f"- {m}" for m in items] or ["- (không có)"]
            lines.append("")
        return "\n".join(lines)


def _pages_str(pages: list[int], limit: int = 15) -> str:
    s = ", ".join(map(str, pages[:limit]))
    return s + (f" … (+{len(pages) - limit})" if len(pages) > limit else "")


def preflight(pdf_path: str | Path, tpl: Template | None = None, tac_dpi: int = 50) -> PreflightResult:
    import numpy as np
    import pymupdf

    res = PreflightResult()
    min_ppi = tpl["images"]["min_ppi"] if tpl else 300
    error_ppi = tpl["images"]["error_ppi"] if tpl else 200
    tac_limit = tpl["color"]["tac_limit"] if tpl else 300
    bleed_req = (tpl["page"]["bleed_mm"] if tpl else 3) * MM
    want_x = (tpl["pdf"]["standard"] if tpl else "PDFX4").upper()

    with pymupdf.open(str(pdf_path)) as doc:
        n = doc.page_count
        res.infos.append(f"Số trang: {n}")
        if n % 4:
            res.warnings.append(f"Số trang {n} không chia hết cho 4 — nhà in sẽ phải thêm trang trắng khi bình trang.")
        elif n % 16:
            res.infos.append(f"Số trang {n} không chia hết cho 16 (tay sách 16 trang) — hỏi nhà in về cách bình.")

        # --- Chuẩn PDF/X & output intent ---------------------------------
        cat = doc.pdf_catalog()
        oi = doc.xref_get_key(cat, "OutputIntents")
        trailer_info = doc.xref_get_key(-1, "Info")
        gts = ""
        if trailer_info[0] == "xref":
            info_xref = int(trailer_info[1].split()[0])
            gts = doc.xref_get_key(info_xref, "GTS_PDFXVersion")[1]
        if oi[0] == "null":
            res.errors.append("Không có Output Intent — file không phải PDF/X (nhà in không biết điều kiện in).")
        else:
            res.infos.append("Có Output Intent (ICC điều kiện in).")
        if not gts or gts == "null":
            res.errors.append(f"Thiếu khai báo GTS_PDFXVersion — cần xuất theo chuẩn {want_x}.")
        else:
            res.infos.append(f"Chuẩn: {gts}")
            if want_x == "PDFX4" and "X-4" not in gts:
                res.warnings.append(f"Mẫu yêu cầu PDF/X-4 nhưng file là {gts}.")
            if want_x == "PDFX1A" and "X-1a" not in gts:
                res.warnings.append(f"Mẫu yêu cầu PDF/X-1a nhưng file là {gts}.")

        # --- Hộp trang: TrimBox / BleedBox --------------------------------
        no_trim, small_bleed, size_bad = [], [], []
        for p in doc:
            trim = doc.xref_get_key(p.xref, "TrimBox")
            if trim[0] == "null":
                no_trim.append(p.number + 1)
                continue
            tb, bb = p.trimbox, p.bleedbox
            b = min(tb.x0 - bb.x0, tb.y0 - bb.y0, bb.x1 - tb.x1, bb.y1 - tb.y1)
            if b < bleed_req - 0.5:
                small_bleed.append(p.number + 1)
            if tpl and (abs(tb.width - tpl.page_w) > 1 or abs(tb.height - tpl.page_h) > 1):
                size_bad.append(p.number + 1)
        if no_trim:
            res.errors.append(f"Thiếu TrimBox ở trang: {_pages_str(no_trim)}")
        if small_bleed:
            res.errors.append(f"Bleed nhỏ hơn {bleed_req / MM:.1f} mm ở trang: {_pages_str(small_bleed)}")
        if size_bad and tpl:
            res.errors.append(f"Khổ thành phẩm khác {tpl['page']['width_mm']}×{tpl['page']['height_mm']} mm ở trang: {_pages_str(size_bad)}")

        # --- Font ---------------------------------------------------------
        not_embedded, type3 = set(), set()
        for p in doc:
            for xref, ext, ftype, basefont, *_ in p.get_fonts(full=True):
                if ext in ("n/a", "") and ftype != "Type3":
                    not_embedded.add(basefont)
                if ftype == "Type3":
                    type3.add(basefont)
        if not_embedded:
            res.errors.append(f"Font chưa nhúng: {', '.join(sorted(not_embedded))}")
        else:
            res.infos.append("Tất cả font đã được nhúng.")
        if type3:
            res.warnings.append(f"Font Type3 (chất lượng in kém): {', '.join(sorted(type3))}")

        # --- Ảnh: hệ màu & độ phân giải hiệu dụng --------------------------
        rgb_pages, low, very_low = set(), [], []
        seen_cs: dict[int, str] = {}
        for p in doc:
            for img in p.get_images(full=True):
                xref, cs = img[0], img[5]
                seen_cs[xref] = cs
                if cs in ("DeviceRGB", "CalRGB") or (cs == "ICCBased" and _icc_n(doc, xref) == 3):
                    rgb_pages.add(p.number + 1)
            for info in p.get_image_info(xrefs=True):
                bbox = pymupdf.Rect(info["bbox"])
                if bbox.width < 2 or bbox.height < 2:
                    continue
                ppi = min(info["width"] / (bbox.width / 72), info["height"] / (bbox.height / 72))
                if ppi < error_ppi:
                    very_low.append((p.number + 1, round(ppi)))
                elif ppi < min_ppi - 0.5:
                    low.append((p.number + 1, round(ppi)))
        if rgb_pages:
            msg = f"Ảnh RGB ở trang: {_pages_str(sorted(rgb_pages))}"
            (res.errors if want_x == "PDFX1A" else res.warnings).append(
                msg + (" (PDF/X-1a không cho phép RGB)" if want_x == "PDFX1A" else " (PDF/X-4 cho phép nhưng nên chuyển CMYK trước)"))
        if very_low:
            res.errors.append(f"Ảnh dưới {error_ppi} ppi: " + ", ".join(f"tr.{a} ({b} ppi)" for a, b in very_low[:20]))
        if low:
            res.warnings.append(f"Ảnh dưới {min_ppi} ppi: " + ", ".join(f"tr.{a} ({b} ppi)" for a, b in low[:20]))
        res.infos.append(f"Số ảnh: {len(seen_cs)}")

        # --- Chú thích/form (không được có trong file in) ------------------
        annot_pages = [p.number + 1 for p in doc if any(a.type[0] not in (1,) for a in p.annots() or [])]
        if annot_pages:
            res.warnings.append(f"Có annotation/link ở trang: {_pages_str(annot_pages)} — nên xuất không kèm.")

        # --- Tổng lượng mực (TAC), ước lượng bằng render CMYK -------------
        over: list[tuple[int, float]] = []
        max_tac = 0.0
        for p in doc:
            pix = p.get_pixmap(colorspace=pymupdf.csCMYK, dpi=tac_dpi, alpha=False)
            a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 4)
            tac = a.astype(np.uint16).sum(axis=2) / 255 * 100
            pmax = float(tac.max()) if tac.size else 0.0
            max_tac = max(max_tac, pmax)
            area = float((tac > tac_limit + 5).mean())
            if area > 0.0005:
                over.append((p.number + 1, pmax))
        res.infos.append(f"TAC lớn nhất (ước lượng ở {tac_dpi} dpi): {max_tac:.0f}%")
        if over:
            res.errors.append(
                f"Tổng lượng mực vượt {tac_limit}% ở trang: "
                + ", ".join(f"tr.{a} ({b:.0f}%)" for a, b in over[:20]))
    return res


def _icc_n(doc, xref) -> int:
    try:
        cs = doc.xref_get_key(xref, "ColorSpace")
        if cs[0] == "array" and "ICCBased" in cs[1]:
            ref = int(cs[1].split("ICCBased")[1].split()[0])
            return int(doc.xref_get_key(ref, "N")[1])
    except Exception:
        pass
    return 0

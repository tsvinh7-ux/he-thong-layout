"""PDF XEM TRƯỚC (proof) — dựng nhanh không cần InDesign.

Mục đích: biên tập viên duyệt nội dung/cấu trúc, chạy thử `htl verify` cho cả
quy trình. KHÔNG dùng để in: không phải PDF/X, chú thích chân trang dồn về
cuối chương, chất lượng dàn chữ đơn giản. File in offset luôn xuất từ InDesign.
"""
from __future__ import annotations

import html
import json
import os
import sys
from pathlib import Path

from .config import MM
from .ir import Cell, Figure, Paragraph, Table, from_dict

FONT_CANDIDATES = [
    # (thư mục, regular, bold, italic, bold-italic)
    ("C:/Windows/Fonts", "times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    ("/System/Library/Fonts/Supplemental", "Times New Roman.ttf", "Times New Roman Bold.ttf",
     "Times New Roman Italic.ttf", "Times New Roman Bold Italic.ttf"),
    ("/Library/Fonts", "Times New Roman.ttf", "Times New Roman Bold.ttf",
     "Times New Roman Italic.ttf", "Times New Roman Bold Italic.ttf"),
    ("/usr/share/fonts/truetype/liberation", "LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf",
     "LiberationSerif-Italic.ttf", "LiberationSerif-BoldItalic.ttf"),
    ("/usr/share/fonts/truetype/liberation2", "LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf",
     "LiberationSerif-Italic.ttf", "LiberationSerif-BoldItalic.ttf"),
    ("/usr/share/fonts/truetype/dejavu", "DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf",
     "DejaVuSerif-Italic.ttf", "DejaVuSerif-BoldItalic.ttf"),
]


def find_fonts(font_dir: str | None = None) -> tuple[Path, list[str]]:
    cands = list(FONT_CANDIDATES)
    if font_dir:
        cands.insert(0, (font_dir, "Regular.ttf", "Bold.ttf", "Italic.ttf", "BoldItalic.ttf"))
    if os.environ.get("WINDIR"):
        cands.insert(0, (os.path.join(os.environ["WINDIR"], "Fonts"), "times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"))
    for d, *files in cands:
        if all((Path(d) / f).exists() for f in files):
            return Path(d), files
    raise SystemExit("Không tìm thấy font có dấu tiếng Việt cho bản xem trước (Times New Roman / Liberation Serif / DejaVu Serif).")


ACCENT = "#0b4f8a"
SEP = "\x00"


def _css(fonts: list[str]) -> str:
    r, b, i, bi = fonts
    return f"""
@font-face {{font-family: F; src: url("{r}");}}
@font-face {{font-family: F; src: url("{b}"); font-weight: bold;}}
@font-face {{font-family: F; src: url("{i}"); font-style: italic;}}
@font-face {{font-family: F; src: url("{bi}"); font-weight: bold; font-style: italic;}}
body {{font-family: F; font-size: 10.5pt; line-height: 1.38; text-align: justify; margin: 0;}}
p {{margin: 0;}}
.body {{text-indent: 14pt;}}
.body_first {{text-indent: 0;}}
.chapter_number {{font-weight: bold; font-size: 13pt; color: {ACCENT}; margin-top: 30pt; text-align: left;}}
.chapter_title {{font-weight: bold; font-size: 24pt; line-height: 1.2; color: {ACCENT}; margin: 4pt 0 30pt 0; text-align: left;}}
.h1 {{font-weight: bold; font-size: 14pt; color: {ACCENT}; margin: 16pt 0 6pt 0; text-align: left;}}
.h2 {{font-weight: bold; font-size: 12pt; margin: 12pt 0 4pt 0; text-align: left;}}
.h3 {{font-weight: bold; font-size: 10.5pt; margin: 9pt 0 2pt 0; text-align: left;}}
.h4 {{font-weight: bold; font-style: italic; margin: 6pt 0 0 0; text-align: left;}}
.list_bullet, .list_number {{margin-left: 16pt; text-indent: -12pt; text-align: left;}}
.lvl2 {{margin-left: 30pt;}}
.quote {{font-style: italic; margin: 6pt 24pt;}}
.box_title {{font-weight: bold; color: {ACCENT}; margin-top: 10pt; text-align: left;}}
.box {{font-size: 9.5pt; background-color: #e8f0f8; padding: 3pt 6pt; text-align: left;}}
.figure {{text-align: center; margin-top: 10pt;}}
.caption {{font-size: 9pt; margin: 4pt 0 10pt 0; text-align: left;}}
.table_caption {{font-weight: bold; font-size: 9.5pt; margin: 10pt 0 3pt 0; text-align: left;}}
.table_note {{font-size: 8pt; margin-bottom: 8pt;}}
.reference {{font-size: 9pt; margin-left: 14pt; text-indent: -14pt; text-align: left;}}
.footnote {{font-size: 8.5pt; text-align: left;}}
.fnrule {{margin-top: 12pt; border-top: 0.5pt solid #000; width: 30%;}}
table {{border-collapse: collapse; width: 100%; margin-bottom: 10pt;}}
td, th {{border: 0.5pt solid #555; padding: 2pt 4pt; font-size: 9pt; text-align: left; vertical-align: top;}}
th {{background-color: #dbe7f3; font-weight: bold;}}
"""


class _Html:
    def __init__(self, figures: dict):
        self.figures = figures
        self.fn: list[list[Paragraph]] = []

    def runs(self, p: Paragraph) -> str:
        out = []
        if p.label:
            out.append(html.escape(p.label.replace("\t", "\u2002")))
        elif p.role == "list_bullet":
            out.append("•\u2002")
        for r in p.runs:
            if r.footnote is not None:
                self.fn.append(r.footnote)
                out.append(f"<sup>{len(self.fn)}</sup>")
                continue
            t = html.escape(r.text).replace("\t", "\u2002").replace("\u2028", "<br/>")
            if r.caps:
                t = t.upper()
            if r.sup:
                t = f"<sup>{t}</sup>"
            if r.sub:
                t = f"<sub>{t}</sub>"
            if r.bold:
                t = f"<b>{t}</b>"
            if r.italic:
                t = f"<i>{t}</i>"
            if r.underline:
                t = f"<u>{t}</u>"
            out.append(t)
        return "".join(out)

    def blocks(self, blocks, in_table=False) -> str:
        out = []
        prev = None
        for b in blocks:
            if isinstance(b, Paragraph):
                role = b.role
                if role == "body" and not in_table and not (isinstance(prev, Paragraph) and prev.role in ("body", "body_first")):
                    role = "body_first"
                cls = role + (" lvl2" if b.level > 1 and role.startswith("list_") else "")
                out.append(f'<p class="{cls}">{self.runs(b)}</p>')
            elif isinstance(b, Figure):
                if in_table:
                    out.append(self.figure_html(b.id))
                else:  # ảnh cấp trang: tách riêng để tự ngắt trang (xem render_preview)
                    out.append(f"{SEP}{b.id}{SEP}")
            elif isinstance(b, Table):
                out.append(self.table(b))
            prev = b
        return "".join(out)

    def figure_html(self, fig_id: str) -> str:
        spec = self.figures.get(f"##HTL{fig_id.upper()}##")
        if spec:
            return f'<p class="figure"><img src="images/{spec["file"]}" style="width: {spec["w_pt"]:.1f}pt"/></p>'
        return f'<p class="figure">##HTL{fig_id.upper()}##</p>'

    def figure_height(self, fig_id: str) -> float:
        spec = self.figures.get(f"##HTL{fig_id.upper()}##")
        return (spec["h_pt"] if spec else 20) + 14

    def table(self, t: Table) -> str:
        rows = []
        for ri, row in enumerate(t.rows):
            cells = []
            for c in row:
                if c.covered:
                    continue
                tag = "th" if ri < t.header_rows else "td"
                span = (f' colspan="{c.colspan}"' if c.colspan > 1 else "") + (f' rowspan="{c.rowspan}"' if c.rowspan > 1 else "")
                cells.append(f"<{tag}{span}>{self.blocks(c.blocks, in_table=True)}</{tag}>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        return "<table>" + "".join(rows) + "</table>"

    def footnotes(self) -> str:
        if not self.fn:
            return ""
        out = ['<div class="fnrule"></div>']
        for i, paras in enumerate(self.fn, 1):
            for k, p in enumerate(paras):
                lead = f"<sup>{i}</sup>\u2002" if k == 0 else ""
                out.append(f'<p class="footnote">{lead}{self.runs(p)}</p>')
        self.fn = []
        return "".join(out)


def render_preview(build_dir: str | Path, out_pdf: str | Path | None = None, font_dir: str | None = None) -> Path:
    import pymupdf

    build_dir = Path(build_dir)
    job = json.loads((build_dir / "job.json").read_text(encoding="utf-8"))
    book = from_dict(json.loads((build_dir / "book.json").read_text(encoding="utf-8")))
    tpl = job["template"]
    out_pdf = Path(out_pdf or build_dir / "output" / "xem-truoc.pdf")
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    fdir, fonts = find_fonts(font_dir)
    arch = pymupdf.Archive()
    arch.add(pymupdf.Archive(str(fdir)))
    arch.add(pymupdf.Archive(str(build_dir)))
    css = _css(fonts)

    W, H = tpl["computed"]["page_w"], tpl["computed"]["page_h"]
    m = tpl["margins_mm"]
    top, bottom, inside, outside = (m["top"] * MM, m["bottom"] * MM, m["inside"] * MM, m["outside"] * MM)

    def frame(page_no: int) -> "pymupdf.Rect":
        if page_no % 2 == 1:  # trang lẻ (phải): gáy bên trái
            return pymupdf.Rect(inside, top, W - outside, H - bottom)
        return pymupdf.Rect(outside, top, W - inside, H - bottom)

    writer = pymupdf.DocumentWriter(str(out_pdf))
    state = {"page": 0, "dev": None, "y": 0.0}

    def new_page():
        if state["dev"] is not None:
            writer.end_page()
        state["page"] += 1
        state["dev"] = writer.begin_page(pymupdf.Rect(0, 0, W, H))
        state["y"] = frame(state["page"]).y0

    def place_html(fragment: str):
        story = pymupdf.Story(html=f"<body>{fragment}</body>", user_css=css, archive=arch)
        more, guard = 1, 0
        while more:
            r = frame(state["page"])
            if state["y"] > r.y1 - 14:  # không còn chỗ cho một dòng
                new_page()
                r = frame(state["page"])
            rect = pymupdf.Rect(r.x0, state["y"], r.x1, r.y1)
            more, filled = story.place(rect)
            story.draw(state["dev"])
            state["y"] = filled[3]
            if more:
                guard += 1
                if guard > 400:
                    raise RuntimeError("Bản xem trước: có khối nội dung không đặt vừa trang.")
                new_page()

    chapter_pages: list[tuple[int, str]] = []
    gen = _Html(job["figures"])
    for ch in book.chapters:
        if state["dev"] is not None and job["template"].get("chapter_start") == "recto" and state["page"] % 2 == 1:
            new_page()  # trang trắng để chương mở ở trang lẻ
        new_page()
        chapter_pages.append((state["page"], ch.title))
        parts = (gen.blocks(ch.blocks) + gen.footnotes()).split(SEP)
        for k, part in enumerate(parts):
            if k % 2 == 0:
                if part:
                    place_html(part)
            else:
                # Ảnh không vừa phần còn lại của trang -> sang trang mới (Story của MuPDF
                # bị kẹt nếu để nó tự xử lý trường hợp này).
                if state["y"] + gen.figure_height(part) > frame(state["page"]).y1:
                    new_page()
                place_html(gen.figure_html(part))
    if state["dev"] is not None:
        writer.end_page()
    writer.close()

    # Số trang + tiêu đề chạy (trừ trang mở chương và trang trắng)
    doc = pymupdf.open(str(out_pdf))
    starts = {p for p, _ in chapter_pages}
    font = str(fdir / fonts[0])
    title = job.get("title") or ""
    for i, page in enumerate(doc, 1):
        if not page.get_text().strip():
            continue
        cur = [t for p, t in chapter_pages if p <= i][-1]
        page.insert_font(fontname="pf", fontfile=font)
        fy = H - bottom + 10 * MM
        if i % 2 == 1:
            page.insert_text((W - outside - 10, fy), str(i), fontname="pf", fontsize=8)
        else:
            page.insert_text((outside, fy), str(i), fontname="pf", fontsize=8)
        if i not in starts:
            head = title if i % 2 == 0 else cur
            if head:
                x = outside if i % 2 == 0 else inside
                page.insert_text((x, top - 8 * MM), head, fontname="pf", fontsize=8, color=(0.3, 0.3, 0.3))
    doc.set_metadata({"title": f"{title} — BẢN XEM TRƯỚC (không dùng để in)", "creator": "HTL preview"})
    tmp = out_pdf.with_suffix(".tmp.pdf")
    doc.save(str(tmp), garbage=3, deflate=True, deflate_images=True, deflate_fonts=True)
    doc.close()
    tmp.replace(out_pdf)
    return out_pdf


if __name__ == "__main__":  # pragma: no cover
    print(render_preview(sys.argv[1]))

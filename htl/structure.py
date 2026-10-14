"""Hậu xử lý cấu trúc sau khi đọc: nhận diện chú thích hình/bảng, đánh mã ảnh, chia chương.

Các bước ở đây chỉ GÁN VAI TRÒ, không bao giờ sửa chữ.
"""
from __future__ import annotations

import re

from .ir import Book, Chapter, Figure, Paragraph, Table, iter_blocks
from .report import Report
from .textnorm import clean


def detect_captions(blocks: list, patterns: dict) -> int:
    """Đoạn thường đứng sát ảnh/bảng và bắt đầu bằng 'Hình 3.1', 'Bảng 2'... -> chú thích."""
    fig_re = re.compile(patterns["figure"], re.IGNORECASE)
    tab_re = re.compile(patterns["table"], re.IGNORECASE)
    changed = 0
    for i, b in enumerate(blocks):
        if not isinstance(b, Paragraph) or b.role not in ("body", "caption"):
            continue
        prev = blocks[i - 1] if i > 0 else None
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        near_fig = isinstance(prev, Figure) or isinstance(nxt, Figure)
        near_tab = isinstance(prev, Table) or isinstance(nxt, Table)
        if near_tab and tab_re.match(b.text):
            if b.role != "table_caption":
                b.role = "table_caption"
                changed += 1
        elif b.role == "body" and near_fig and fig_re.match(b.text):
            b.role = "caption"
            changed += 1
    for b in blocks:
        if isinstance(b, Table):
            for row in b.rows:
                for cell in row:
                    changed += detect_captions(cell.blocks, patterns)
    return changed


def caption_of(blocks: list, idx: int) -> str:
    for j in (idx + 1, idx - 1):
        if 0 <= j < len(blocks) and isinstance(blocks[j], Paragraph) and blocks[j].role == "caption":
            return blocks[j].text
    return ""


def assign_figure_ids(book: Book) -> None:
    n = 0
    for ch in book.chapters:
        for b in iter_blocks(ch.blocks):
            if isinstance(b, Figure):
                n += 1
                b.id = f"fig{n:04d}"


def split_chapters(blocks: list, source: str, split_role: str) -> list[Chapter]:
    """Chia một file thành nhiều chương tại mỗi đoạn có vai trò `split_role`.

    Nếu ngay trước đoạn tiêu đề chương là đoạn 'chapter_number' thì đoạn đó
    thuộc về chương mới.
    """
    chapters: list[Chapter] = []
    cur: list = []
    for b in blocks:
        if isinstance(b, Paragraph) and b.role == split_role and any(
            not (isinstance(x, Paragraph) and x.role == "chapter_number") for x in cur
        ):
            carry = []
            while cur and isinstance(cur[-1], Paragraph) and cur[-1].role == "chapter_number":
                carry.insert(0, cur.pop())
            if cur:
                chapters.append(Chapter(blocks=cur, source=source))
            cur = carry
        cur.append(b)
    if cur:
        chapters.append(Chapter(blocks=cur, source=source))
    return chapters


def _normalize_text(blocks) -> int:
    changed = 0
    for b in iter_blocks(blocks):
        if isinstance(b, Paragraph):
            for p in [b] + [fp for fn in b.footnotes() for fp in fn]:
                c = clean(p.label)
                changed += c != p.label
                p.label = c
                for r in p.runs:
                    if r.footnote is None:
                        c = clean(r.text)
                        changed += c != r.text
                        r.text = c
    return changed


def finalize(book: Book, patterns: dict, report: Report) -> None:
    caps = 0
    nfc = sum(_normalize_text(ch.blocks) for ch in book.chapters)
    if nfc:
        report.info(f"Chuẩn hóa Unicode NFC thêm {nfc} đoạn chữ (đầu vào JSON).")
    for i, ch in enumerate(book.chapters):
        if not ch.id:
            ch.id = f"ch{i + 1:02d}"
        caps += detect_captions(ch.blocks, patterns)
        if not ch.blocks:
            report.warn(f"Chương {ch.id} ({ch.source}) không có nội dung.")
    assign_figure_ids(book)
    if caps:
        report.info(f"Nhận diện {caps} chú thích hình/bảng theo mẫu 'Hình …'/'Bảng …' đứng sát ảnh/bảng.")

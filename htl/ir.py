"""Mô hình dữ liệu trung gian (IR) của bản thảo.

Mọi đầu vào (Word, JSON từ hệ thống dịch, ...) đều được đưa về IR này.
Mọi đầu ra (ICML cho InDesign, văn bản đối chiếu, ...) đều sinh ra từ IR.
IR chỉ mô tả CẤU TRÚC và NỘI DUNG, không mô tả hình thức trình bày:
hình thức do mẫu layout (template) quyết định.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Union

# Các vai trò (role) đoạn văn mà hệ thống hiểu. Mẫu layout ánh xạ mỗi role
# sang một paragraph style trong InDesign.
ROLES = (
    "chapter_number",
    "chapter_title",
    "h1",
    "h2",
    "h3",
    "h4",
    "body",
    "body_first",
    "list_bullet",
    "list_number",
    "quote",
    "box_title",
    "box",
    "caption",
    "table_caption",
    "table_head",
    "table_body",
    "table_note",
    "reference",
    "footnote",
    "figure",
    "toc",
)

HEADING_ROLES = ("chapter_number", "chapter_title", "h1", "h2", "h3", "h4")


@dataclass
class Run:
    """Một đoạn chữ cùng định dạng ký tự.

    Nếu `footnote` khác None thì run này là điểm tham chiếu chú thích chân
    trang; `text` khi đó rỗng (số chú thích do InDesign tự đánh).
    """

    text: str = ""
    bold: bool = False
    italic: bool = False
    underline: bool = False
    sup: bool = False
    sub: bool = False
    smallcaps: bool = False
    caps: bool = False
    footnote: list["Paragraph"] | None = None

    def same_format(self, other: "Run") -> bool:
        return (
            self.footnote is None
            and other.footnote is None
            and (self.bold, self.italic, self.underline, self.sup, self.sub, self.smallcaps, self.caps)
            == (other.bold, other.italic, other.underline, other.sup, other.sub, other.smallcaps, other.caps)
        )


@dataclass
class Paragraph:
    role: str = "body"
    runs: list[Run] = field(default_factory=list)
    level: int = 1  # cấp danh sách (1..3)
    label: str = ""  # nhãn đánh số dạng chữ cố định, ví dụ "1.\t" hoặc "a)\t"
    source_style: str = ""  # tên style gốc trong Word, để báo cáo

    @property
    def text(self) -> str:
        return self.label + "".join(r.text for r in self.runs if r.footnote is None)

    def footnotes(self) -> list[list["Paragraph"]]:
        return [r.footnote for r in self.runs if r.footnote is not None]

    def is_empty(self) -> bool:
        return not self.text.strip() and not self.footnotes()


@dataclass
class Figure:
    id: str = ""
    image: str = ""  # đường dẫn tới file ảnh nguồn (đã trích ra từ Word hoặc ảnh gốc)
    alt: str = ""
    source_name: str = ""  # tên gốc của ảnh trong bản thảo (để đối chiếu ảnh gốc)
    role: str = "figure"


@dataclass
class Cell:
    blocks: list[Union[Paragraph, Figure]] = field(default_factory=list)
    colspan: int = 1
    rowspan: int = 1
    covered: bool = False  # ô bị gộp vào ô khác (không có nội dung riêng)


@dataclass
class Table:
    rows: list[list[Cell]] = field(default_factory=list)
    header_rows: int = 0
    col_widths: list[float] = field(default_factory=list)  # tỉ lệ tương đối
    source_style: str = ""
    role: str = "table"

    @property
    def ncols(self) -> int:
        return max((len(r) for r in self.rows), default=0)

    def merges(self) -> list[tuple[int, int, int, int]]:
        """Danh sách ô gộp (col, row, colspan, rowspan)."""
        out = []
        for r, row in enumerate(self.rows):
            for c, cell in enumerate(row):
                if not cell.covered and (cell.colspan > 1 or cell.rowspan > 1):
                    out.append((c, r, cell.colspan, cell.rowspan))
        return out


Block = Union[Paragraph, Table, Figure]


@dataclass
class Chapter:
    id: str = ""
    source: str = ""
    blocks: list[Block] = field(default_factory=list)

    @property
    def title(self) -> str:
        for b in self.blocks:
            if isinstance(b, Paragraph) and b.role in ("chapter_title", "h1"):
                return b.text.strip()
        return self.id


@dataclass
class Book:
    title: str = ""
    chapters: list[Chapter] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Duyệt IR theo đúng thứ tự đọc
# ---------------------------------------------------------------------------

def iter_blocks(blocks, *, into_tables: bool = True):
    """Duyệt mọi block theo thứ tự đọc (kể cả nội dung trong bảng)."""
    for b in blocks:
        yield b
        if into_tables and isinstance(b, Table):
            for row in b.rows:
                for cell in row:
                    if not cell.covered:
                        yield from iter_blocks(cell.blocks)


def iter_figures(book: Book):
    for ch in book.chapters:
        for b in iter_blocks(ch.blocks):
            if isinstance(b, Figure):
                yield ch, b


FN_MARK = "\ue000"  # vị trí số chú thích chân trang trong văn bản đối chiếu


def main_text(blocks, fn_marker: str = "") -> list[str]:
    """Văn bản dòng chính (không gồm nội dung chú thích chân trang), theo thứ tự đọc.

    Mỗi phần tử là văn bản của một đoạn. Đây là "chuẩn" để đối chiếu với PDF.
    `fn_marker` (nếu có) được chèn đúng chỗ số chú thích xuất hiện trong câu.
    """
    out: list[str] = []
    for b in iter_blocks(blocks):
        if isinstance(b, Paragraph):
            if fn_marker:
                out.append(b.label + "".join(fn_marker if r.footnote is not None else r.text for r in b.runs))
            else:
                out.append(b.text)
    return out


def footnote_texts(blocks) -> list[str]:
    out: list[str] = []
    for b in iter_blocks(blocks):
        if isinstance(b, Paragraph):
            for fn in b.footnotes():
                out.append("\n".join(p.text for p in fn))
    return out


# ---------------------------------------------------------------------------
# JSON (dùng làm định dạng đầu vào cho hệ thống dịch bằng Claude)
# ---------------------------------------------------------------------------

def to_dict(book: Book) -> dict:
    def block(b):
        d = asdict(b)
        d["type"] = type(b).__name__.lower()
        return d

    return {
        "title": book.title,
        "chapters": [
            {"id": ch.id, "source": ch.source, "blocks": [block(b) for b in ch.blocks]}
            for ch in book.chapters
        ],
    }


def _run_from(d: dict) -> Run:
    fn = d.get("footnote")
    return Run(
        text=d.get("text", ""),
        bold=d.get("bold", False),
        italic=d.get("italic", False),
        underline=d.get("underline", False),
        sup=d.get("sup", False),
        sub=d.get("sub", False),
        smallcaps=d.get("smallcaps", False),
        caps=d.get("caps", False),
        footnote=[_para_from(p) for p in fn] if fn is not None else None,
    )


def _para_from(d: dict) -> Paragraph:
    return Paragraph(
        role=d.get("role", "body"),
        runs=[_run_from(r) for r in d.get("runs", [])],
        level=d.get("level", 1),
        label=d.get("label", ""),
        source_style=d.get("source_style", ""),
    )


def block_from_dict(d: dict) -> Block:
    t = d.get("type", "paragraph")
    if t == "paragraph":
        return _para_from(d)
    if t == "figure":
        return Figure(
            id=d.get("id", ""),
            image=d.get("image", ""),
            alt=d.get("alt", ""),
            source_name=d.get("source_name", ""),
        )
    if t == "table":
        rows = [
            [
                Cell(
                    blocks=[block_from_dict(x) for x in c.get("blocks", [])],
                    colspan=c.get("colspan", 1),
                    rowspan=c.get("rowspan", 1),
                    covered=c.get("covered", False),
                )
                for c in row
            ]
            for row in d.get("rows", [])
        ]
        return Table(
            rows=rows,
            header_rows=d.get("header_rows", 0),
            col_widths=d.get("col_widths", []),
            source_style=d.get("source_style", ""),
        )
    raise ValueError(f"Loại block không hợp lệ: {t!r}")


def from_dict(d: dict) -> Book:
    return Book(
        title=d.get("title", ""),
        chapters=[
            Chapter(
                id=c.get("id", f"ch{i + 1:02d}"),
                source=c.get("source", ""),
                blocks=[block_from_dict(b) for b in c.get("blocks", [])],
            )
            for i, c in enumerate(d.get("chapters", []))
        ],
    )

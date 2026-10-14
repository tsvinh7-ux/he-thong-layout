"""Bộ đọc đầu vào: Word (.docx) và JSON (định dạng IR, dành cho hệ thống dịch)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import StyleMap
from ..ir import Book, Chapter, from_dict, iter_figures
from ..report import Report
from ..structure import split_chapters
from .docx_reader import DocxReader


def natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def expand_inputs(inputs: list[str]) -> list[Path]:
    out: list[Path] = []
    for i in inputs:
        p = Path(i)
        if p.is_dir():
            files = [f for f in p.iterdir() if f.suffix.lower() in (".docx", ".json") and not f.name.startswith("~$")]
            out += sorted(files, key=natural_key)
        else:
            out.append(p)
    return out


def read_book(
    inputs: list[str],
    style_map: StyleMap,
    report: Report,
    media_dir: Path,
    *,
    split_role: str | None = None,
    accept_tracked_changes: bool = False,
    title: str = "",
) -> Book:
    """Đọc danh sách file theo đúng thứ tự (thư mục: sắp theo tên tự nhiên ch1, ch2, ..., ch10)."""
    book = Book(title=title)
    files = expand_inputs(inputs)
    if not files:
        raise SystemExit("Không có file đầu vào (.docx/.json).")
    for idx, f in enumerate(files, 1):
        report.info(f"Đầu vào #{idx}: {f.name}")
        if f.suffix.lower() == ".json":
            sub = from_dict(json.loads(f.read_text(encoding="utf-8")))
            book.title = book.title or sub.title
            for _, fig in iter_figures(sub):
                if fig.image and not Path(fig.image).is_absolute():
                    fig.image = str((f.parent / fig.image).resolve())
            for ch in sub.chapters:
                ch.source = ch.source or f.name
                ch.id = ""
                book.chapters.append(ch)
            continue
        if f.suffix.lower() == ".doc":
            raise SystemExit(f"{f.name}: định dạng .doc cũ — hãy lưu lại thành .docx.")
        reader = DocxReader(
            f, style_map, report, media_dir,
            media_prefix=f"src{idx:02d}",
            accept_tracked_changes=accept_tracked_changes,
        )
        blocks = reader.read()
        if split_role:
            book.chapters += split_chapters(blocks, f.name, split_role)
        else:
            book.chapters.append(Chapter(source=f.name, blocks=blocks))
    return book

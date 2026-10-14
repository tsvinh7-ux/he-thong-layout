"""Điều phối một lần dựng sách: bản thảo -> gói dựng cho InDesign."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import load_style_map, load_template
from .icml import fig_marker, write_chapter_icml
from .images import match_hires, process_images
from .ir import Figure, Paragraph, Table, footnote_texts, iter_blocks, main_text, to_dict
from .readers import read_book
from .report import Report
from .structure import finalize

ROOT = Path(__file__).resolve().parent.parent
JSX_SRC = ROOT / "indesign" / "htl_build.jsx"


@dataclass
class BuildOptions:
    inputs: list[str]
    template: str
    out: str
    title: str = ""
    style_map: str | None = None
    hires_dir: str | None = None
    image_map: str | None = None
    split_role: str | None = None
    accept_tracked_changes: bool = False


def build(opts: BuildOptions) -> tuple[Report, Path]:
    report = Report()
    tpl = load_template(opts.template)
    tpl_map = tpl["style_map"]
    if tpl_map:
        tpl_map = tpl.path.parent / tpl_map
    style_map = load_style_map(opts.style_map, tpl_map)

    out = Path(opts.out)
    if out.exists():
        for sub in ("stories", "images", "_source_media"):
            shutil.rmtree(out / sub, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "stories").mkdir()
    (out / "output").mkdir(exist_ok=True)

    book = read_book(
        opts.inputs, style_map, report, out / "_source_media",
        split_role=opts.split_role,
        accept_tracked_changes=opts.accept_tracked_changes,
        title=opts.title,
    )
    finalize(book, tpl["caption_patterns"], report)
    match_hires(book, Path(opts.hires_dir) if opts.hires_dir else None,
                Path(opts.image_map) if opts.image_map else None, report)
    placed = process_images(book, tpl, out / "images", report)

    chapters_job = []
    content = {"title": book.title, "chapters": []}
    for ch in book.chapters:
        icml_name = f"stories/{ch.id}.icml"
        write_chapter_icml(ch, tpl, out / icml_name)
        tables = [b for b in iter_blocks(ch.blocks) if isinstance(b, Table)]
        figures = [b for b in iter_blocks(ch.blocks) if isinstance(b, Figure)]
        paras = [b for b in iter_blocks(ch.blocks) if isinstance(b, Paragraph)]
        fns = footnote_texts(ch.blocks)
        chapters_job.append({
            "id": ch.id,
            "title": ch.title,
            "source": ch.source,
            "icml": icml_name,
            "tables": [{"merges": [list(m) for m in t.merges()], "header_rows": t.header_rows,
                        "cols": t.ncols, "rows": len(t.rows)} for t in tables],
            "figures": [fig_marker(f.id) for f in figures],
            "footnotes": len(fns),
            "paragraphs": len(paras),
        })
        content["chapters"].append({
            "id": ch.id,
            "title": ch.title,
            "paragraphs": main_text(ch.blocks),
            "footnotes": fns,
            "figures": [f.id for f in figures],
            "headings": [p.text for p in paras if p.role in ("chapter_title", "chapter_number", "h1", "h2")],
        })

    job = {
        "version": 1,
        "title": book.title,
        "template": tpl.to_job(),
        "chapters": chapters_job,
        "figures": {fig_marker(k): v.to_job() for k, v in placed.items()},
        "build_errors": len(report.errors),
        "output": {"indd": "output/sach.indd", "pdf": "output/sach.pdf", "report": "output/indesign_report.json"},
    }
    (out / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "content.json").write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "book.json").write_text(json.dumps(to_dict(book), ensure_ascii=False, indent=1), encoding="utf-8")

    shutil.copy2(JSX_SRC, out / "htl_build.jsx")
    # ExtendScript (ES3) không có JSON.parse: nhúng cấu hình dưới dạng object literal.
    (out / "run_in_indesign.jsx").write_text(
        "// Chạy file này trong InDesign: File > Scripts > Browse... (hoặc kéo vào bảng Scripts)\n"
        "#target indesign\n"
        f"var HTL_JOB = {json.dumps(job, ensure_ascii=True)};\n"
        '#include "htl_build.jsx"\n',
        encoding="utf-8",
    )

    n_fig = sum(len(c["figures"]) for c in chapters_job)
    n_tab = sum(len(c["tables"]) for c in chapters_job)
    n_fn = sum(c["footnotes"] for c in chapters_job)
    n_par = sum(c["paragraphs"] for c in chapters_job)
    report.info(f"Tổng: {len(chapters_job)} chương, {n_par} đoạn, {n_tab} bảng, {n_fig} hình, {n_fn} chú thích chân trang.")
    (out / "report.md").write_text(report.to_markdown(f"Báo cáo dựng: {book.title or out.name}"), encoding="utf-8")
    return report, out

"""Giao diện dòng lệnh: htl build | verify | preflight | inspect."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path


def _utf8_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def cmd_build(a) -> int:
    from .build import BuildOptions, build

    report, out = build(BuildOptions(
        inputs=a.inputs, template=a.template, out=a.out, title=a.title or "",
        style_map=a.style_map, hires_dir=a.images, image_map=a.image_map,
        split_role=a.split, accept_tracked_changes=a.accept_changes,
    ))
    print(f"Gói dựng: {out}")
    print(f"  - Báo cáo:          {out / 'report.md'}")
    print(f"  - Script InDesign:  {out / 'run_in_indesign.jsx'}")
    print(f"Lỗi: {len(report.errors)}  Cảnh báo: {len(report.warnings)}")
    for e in report.errors[:20]:
        print(f"  [LỖI] {e}")
    return 0 if report.ok else 1


def cmd_verify(a) -> int:
    from .verify import verify

    res = verify(a.pdf, a.build, allowed_extra=a.allow_extra)
    md = res.to_markdown()
    out = Path(a.report or Path(a.build) / "output" / "verify_report.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md if len(md) < 6000 else md[:6000] + "\n…")
    print(f"\nBáo cáo: {out}")
    return 0 if res.ok else 1


def cmd_preflight(a) -> int:
    from .config import load_template
    from .preflight import preflight

    tpl = load_template(a.template) if a.template else None
    res = preflight(a.pdf, tpl)
    md = res.to_markdown()
    print(md)
    if a.report:
        Path(a.report).write_text(md, encoding="utf-8")
    return 0 if res.ok else 1


def cmd_inspect(a) -> int:
    """Liệt kê style Word đang dùng và vai trò hệ thống gán — để lập style_map cho NXB mới."""
    from .config import load_style_map
    from .readers import expand_inputs
    from .readers.docx_reader import DocxReader
    from .report import Report
    import tempfile

    sm = load_style_map(a.style_map)
    total: Counter = Counter()
    rep = Report()
    with tempfile.TemporaryDirectory() as tmp:
        for f in expand_inputs(a.inputs):
            if f.suffix.lower() != ".docx":
                continue
            DocxReader(f, sm, rep, tmp, accept_tracked_changes=True).read()
    total.update(rep.style_usage)
    print(f"{'Style Word':40} {'Vai trò':16} Số đoạn")
    for (s, r), n in sorted(total.items(), key=lambda x: -x[1]):
        flag = "  <- chưa ánh xạ" if s in rep.unmapped_styles else ""
        print(f"{(s or '(không style)')[:40]:40} {r:16} {n}{flag}")
    return 0


def main(argv=None) -> int:
    _utf8_stdout()
    ap = argparse.ArgumentParser(prog="htl", description="Hệ thống dàn trang sách tự động (bản thảo -> InDesign -> PDF in offset)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Dựng gói InDesign từ bản thảo")
    b.add_argument("inputs", nargs="+", help="File .docx/.json hoặc thư mục (đọc theo thứ tự tên)")
    b.add_argument("-t", "--template", required=True, help="Thư mục mẫu layout (chứa template.yaml)")
    b.add_argument("-o", "--out", required=True, help="Thư mục gói dựng")
    b.add_argument("--title", help="Tên sách")
    b.add_argument("--style-map", help="Bảng ánh xạ style riêng của dự án/NXB (YAML)")
    b.add_argument("--images", help="Thư mục ảnh gốc độ phân giải cao")
    b.add_argument("--image-map", help="CSV ánh xạ figure_id,file (ưu tiên hơn tự khớp)")
    b.add_argument("--split", metavar="ROLE", help="Tách chương trong 1 file tại vai trò này (vd. chapter_title)")
    b.add_argument("--accept-changes", action="store_true", help="Chấp nhận toàn bộ track changes còn sót")
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("verify", help="Đối chiếu nội dung PDF với bản thảo")
    v.add_argument("build", help="Thư mục gói dựng (chứa content.json)")
    v.add_argument("pdf", help="File PDF xuất từ InDesign")
    v.add_argument("--allow-extra", action="append", help="Regex token được phép thừa (vd. tên sách ở tiêu đề chạy)")
    v.add_argument("--report", help="Nơi ghi báo cáo .md")
    v.set_defaults(func=cmd_verify)

    p = sub.add_parser("preflight", help="Kiểm tra kỹ thuật PDF trước khi in")
    p.add_argument("pdf")
    p.add_argument("-t", "--template", help="Mẫu layout để lấy thông số (khổ, bleed, ppi, TAC)")
    p.add_argument("--report", help="Nơi ghi báo cáo .md")
    p.set_defaults(func=cmd_preflight)

    i = sub.add_parser("inspect", help="Xem style Word trong bản thảo và vai trò được gán")
    i.add_argument("inputs", nargs="+")
    i.add_argument("--style-map")
    i.set_defaults(func=cmd_inspect)

    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())

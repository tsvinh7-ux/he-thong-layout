"""Chạy demo trọn quy trình bằng một lệnh:

    python demo/chay_demo.py

1. Tạo ảnh gốc demo (nếu chưa có).
2. htl build    : bản thảo Word (2 chương) + ảnh gốc -> gói InDesign.
3. htl preview  : PDF xem trước (không cần InDesign).
4. htl verify   : đối chiếu PDF xem trước với bản thảo.
5. htl preflight: kiểm tra kỹ thuật (bản xem trước KHÔNG phải PDF/X nên sẽ báo lỗi — đúng như mong đợi).
6. Nén gói InDesign thành demo/ket-qua/goi-indesign.zip.

Kết quả nằm trong demo/ket-qua/. Bước tiếp theo trên máy có InDesign: giải nén zip, chạy run_in_indesign.jsx.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from htl.build import BuildOptions, build  # noqa: E402
from htl.config import load_template  # noqa: E402
from htl.preflight import preflight  # noqa: E402
from htl.preview import render_preview  # noqa: E402
from htl.verify import verify  # noqa: E402
from tao_du_lieu_demo import ANH_GOC, BAN_THAO, tao_anh  # noqa: E402

KQ = HERE / "ket-qua"
TPL = ROOT / "templates" / "y-khoa-19x27"


def main() -> int:
    tao_anh()
    KQ.mkdir(exist_ok=True)
    goi = KQ / "goi-indesign"

    print("== 1. Dựng gói InDesign")
    rep, out = build(BuildOptions(
        inputs=[str(BAN_THAO)], template=str(TPL), out=str(goi),
        title="Nội khoa tim mạch – chuyển hóa (DEMO)", hires_dir=str(ANH_GOC),
    ))
    print(f"   lỗi: {len(rep.errors)}, cảnh báo: {len(rep.warnings)}  -> {out / 'report.md'}")

    print("== 2. PDF xem trước")
    pdf = render_preview(goi, KQ / "xem-truoc.pdf")
    print(f"   {pdf}")

    print("== 3. Đối chiếu nội dung")
    v = verify(pdf, goi)
    (KQ / "doi-chieu.md").write_text(v.to_markdown(), encoding="utf-8")
    print(f"   {'ĐẠT' if v.ok else 'KHÔNG ĐẠT'}: khớp {v.matched}/{v.expected_tokens} từ")

    print("== 3b. Thử: giả lập designer lỡ xóa chữ '1,28 tỷ' trong PDF")
    import pymupdf

    sua = KQ / "xem-truoc-bi-sua.pdf"
    with pymupdf.open(str(pdf)) as d:
        for page in d:
            for r in page.search_for("1,28 tỷ"):
                page.add_redact_annot(r)
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
        d.save(str(sua), garbage=3, deflate=True)
    v2 = verify(sua, goi)
    (KQ / "doi-chieu-ban-bi-sua.md").write_text(v2.to_markdown(), encoding="utf-8")
    thieu = [i.text for i in v2.issues if i.kind == "missing"]
    print(f"   {'ĐẠT' if v2.ok else 'KHÔNG ĐẠT'} — phát hiện thiếu: {thieu}")

    print("== 4. Preflight (bản xem trước không phải PDF/X -> lỗi là đúng)")
    pf = preflight(pdf, load_template(TPL))
    (KQ / "preflight-xem-truoc.md").write_text(pf.to_markdown(), encoding="utf-8")
    print(f"   lỗi: {len(pf.errors)}, cảnh báo: {len(pf.warnings)}")

    shutil.copy2(goi / "report.md", KQ / "bao-cao-dung.md")
    zip_path = shutil.make_archive(str(KQ / "goi-indesign"), "zip", root_dir=goi)
    print(f"== 5. Gói InDesign: {zip_path}")
    return 0 if v.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

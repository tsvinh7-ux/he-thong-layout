"""Kiểm thử bước đối chiếu nội dung và preflight bằng PDF giả lập dàn trang."""
import json
from pathlib import Path

import pymupdf
import pytest

from htl.config import load_template
from htl.preflight import preflight
from htl.verify import verify

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "templates" / "y-khoa-19x27"
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
pytestmark = pytest.mark.skipif(not FONT.exists(), reason="cần font DejaVu để tạo PDF tiếng Việt")

PARAS = [
    "Chương 3",
    "Bệnh tim thiếu máu cục bộ",
    "Đại cương",
    "Bệnh tim thiếu máu cục bộ là nguyên nhân tử vong hàng đầu trên thế giới, "
    "chiếm khoảng 16% tổng số ca tử vong theo Tổ chức Y tế Thế giới.",
    "Các yếu tố nguy cơ chính gồm tăng huyết áp, đái tháo đường, rối loạn lipid máu, "
    "hút thuốc lá và tiền sử gia đình. Điều trị bằng thuốc chẹn beta-adrenergic giúp giảm nhu cầu oxy cơ tim; "
    "dược động học (pharmacokinetics) của từng thuốc cần được cân nhắc ở bệnh nhân suy thận mạn tính.",
    "Thuốc", "Liều", "Aspirin", "75–100 mg/ngày",
    "Hình 3.1. Hình ảnh điện tâm đồ.",
    "1.\tThay đổi lối sống.",
    "2.\tĐiều trị nội khoa tối ưu.",
] * 6
FOOTNOTES = ["Số liệu năm 2019.", "Xem thêm Chương 7."]


def make_content(build_dir: Path, paras=PARAS, footnotes=FOOTNOTES):
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "content.json").write_text(json.dumps({
        "title": "Tim mạch học",
        "chapters": [{"id": "ch01", "title": "Bệnh tim thiếu máu cục bộ", "paragraphs": paras,
                      "footnotes": footnotes, "figures": ["fig0001"],
                      "headings": ["Chương 3", "Bệnh tim thiếu máu cục bộ", "Đại cương"]}],
    }, ensure_ascii=False), encoding="utf-8")


def make_pdf(path: Path, paras, footnotes, *, hyphenate=True, bleed_mm=3, running_head=True, extra_box=None):
    """Mô phỏng PDF dàn trang: tiêu đề chạy, số trang, chú thích chân trang ở cuối trang,
    ngắt dòng có gạch nối, CMYK. Mỗi trang ~12 đoạn."""
    mm = 72 / 25.4
    W, H, bl = 190 * mm, 270 * mm, bleed_mm * mm
    b = 12 * mm  # vùng dấu cắt quanh trang (MediaBox lớn hơn TrimBox)
    doc = pymupdf.open()
    chunks = [paras[i:i + 12] for i in range(0, len(paras), 12)]
    fn_by_page = {0: footnotes[:1], 1: footnotes[1:]}
    for pno, chunk in enumerate(chunks):
        page = doc.new_page(width=W + 2 * b, height=H + 2 * b)
        page.set_trimbox(pymupdf.Rect(b, b, W + b, H + b))
        page.set_bleedbox(pymupdf.Rect(b - bl, b - bl, W + b + bl, H + b + bl))
        page.insert_font(fontname="dv", fontfile=str(FONT))
        y = b + 20 * mm
        if running_head:
            page.insert_text((b + 17 * mm, b + 12 * mm), "Tim mạch học" if pno % 2 else "Bệnh tim thiếu máu cục bộ",
                             fontname="dv", fontsize=8, color=(0, 0, 0, 1))
        for para in chunk:
            words = para.replace("\t", " ").split()
            line: list[str] = []
            lines = []
            for w in words:
                if len(" ".join(line + [w])) > 44:
                    if hyphenate and "-" in w:  # ngắt tại gạch nối có sẵn
                        cut = w.index("-") + 1
                        lines.append(" ".join(line + [w[:cut]]))
                        line = [w[cut:]]
                        continue
                    if hyphenate and len(w) >= 4:
                        cut = len(w) // 2
                        lines.append(" ".join(line + [w[:cut] + "-"]))
                        line = [w[cut:]]
                        continue
                    lines.append(" ".join(line))
                    line = [w]
                else:
                    line.append(w)
            lines.append(" ".join(line))
            for ln in lines:
                page.insert_text((b + 22 * mm, y), ln, fontname="dv", fontsize=9.5, color=(0, 0, 0, 1))
                y += 4.6 * mm
            y += 1.5 * mm
        fy = b + H - 34 * mm
        for k, fn in enumerate(fn_by_page.get(pno, [])):
            page.insert_text((b + 22 * mm, fy), f"{pno + k + 1} {fn}", fontname="dv", fontsize=7, color=(0, 0, 0, 1))
            fy += 3.5 * mm
        page.insert_text((b + 100 * mm, b + H - 10 * mm), str(pno + 1), fontname="dv", fontsize=8, color=(0, 0, 0, 1))
        if extra_box and pno == 0:
            page.draw_rect(pymupdf.Rect(b + 20 * mm, b + 200 * mm, b + 60 * mm, b + 220 * mm),
                           color=None, fill=extra_box)
    doc.save(str(path))


def test_verify_passes_on_faithful_layout(tmp_path):
    make_content(tmp_path)
    pdf = tmp_path / "ok.pdf"
    make_pdf(pdf, PARAS, FOOTNOTES)
    lines = [ln for pg in pymupdf.open(str(pdf)) for ln in pg.get_text().splitlines()]
    assert sum(ln.endswith("-") for ln in lines) >= 2  # có ngắt dòng bằng gạch nối
    res = verify(pdf, tmp_path)
    assert res.ok, res.to_markdown()
    assert res.matched == res.expected_tokens


def test_verify_detects_missing_word(tmp_path):
    make_content(tmp_path)
    changed = list(PARAS)
    changed[4] = changed[4].replace("đái tháo đường, ", "")
    pdf = tmp_path / "missing.pdf"
    make_pdf(pdf, changed, FOOTNOTES)
    res = verify(pdf, tmp_path)
    assert not res.ok
    missing = [i for i in res.issues if i.kind == "missing"]
    assert missing and "đái tháo đường," in missing[0].text


def test_verify_detects_added_text(tmp_path):
    make_content(tmp_path)
    changed = list(PARAS)
    changed[3] = changed[3] + " Đây là câu được thêm vào trái phép."
    pdf = tmp_path / "extra.pdf"
    make_pdf(pdf, changed, FOOTNOTES)
    res = verify(pdf, tmp_path)
    extra = [i for i in res.issues if i.kind == "extra"]
    assert extra and "trái phép" in extra[0].text


def test_verify_detects_reordered_paragraphs(tmp_path):
    make_content(tmp_path)
    changed = list(PARAS)
    changed[3], changed[4] = changed[4], changed[3]
    pdf = tmp_path / "order.pdf"
    make_pdf(pdf, changed, FOOTNOTES)
    assert not verify(pdf, tmp_path).ok


def test_verify_detects_missing_footnote_and_unplaced_image(tmp_path):
    make_content(tmp_path)
    changed = list(PARAS)
    changed[9] = "##HTLFIG0001##"
    pdf = tmp_path / "fn.pdf"
    make_pdf(pdf, changed, FOOTNOTES[:1])
    res = verify(pdf, tmp_path)
    kinds = {i.kind for i in res.issues}
    assert "footnote" in kinds and "marker" in kinds


def test_preflight_flags_non_pdfx_and_ink(tmp_path):
    pdf = tmp_path / "pf.pdf"
    make_pdf(pdf, PARAS[:12], [], extra_box=(1, 1, 1, 1), bleed_mm=1)  # 400% mực, bleed 1 mm
    res = preflight(pdf, load_template(TPL))
    text = "\n".join(res.errors)
    assert "Output Intent" in text
    assert "Bleed nhỏ hơn" in text
    assert "Tổng lượng mực" in text
    assert any("đã được nhúng" in i for i in res.infos)


def test_preflight_clean_geometry(tmp_path):
    pdf = tmp_path / "pf2.pdf"
    make_pdf(pdf, PARAS[:48], FOOTNOTES)
    res = preflight(pdf, load_template(TPL))
    text = "\n".join(res.errors)
    assert "Bleed" not in text and "TrimBox" not in text and "Khổ thành phẩm" not in text
    assert "Tổng lượng mực" not in text


def test_footnote_number_only_accepted_at_marked_position():
    from htl.verify import align

    exp = ["chẩn", "đoán", "đúng", "kỹ", "thuật\ue000.", "theo", "who"]
    ok = ["chẩn", "đoán", "đúng", "kỹ", "thuật1.", "theo", "who"]
    matched, missing, extra = align(exp, ok)
    assert matched == len(exp) and not missing and not extra
    # Số xuất hiện ở chỗ bản thảo không có chú thích -> phải bị bắt
    exp2 = ["bảng", "2.1.", "theo", "who", "năm", "nay"]
    bad = ["bảng", "2.11.", "theo", "who", "năm", "nay"]
    _, missing2, extra2 = align(exp2, bad)
    assert missing2 and extra2

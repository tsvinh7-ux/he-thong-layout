from pathlib import Path

import pytest

from htl.config import load_style_map, load_template
from htl.ir import Figure, Paragraph, Table, main_text
from htl.readers.docx_reader import DocxReader
from htl.report import Report
from htl.structure import detect_captions

from docx_factory import drawing, make_docx, p, png_bytes, r, t, tbl, tc, textbox_alt, tr

TPL = Path(__file__).resolve().parent.parent / "templates" / "y-khoa-19x27"


def read(tmp_path, body, **kw):
    accept = kw.pop("accept", False)
    path = tmp_path / "in.docx"
    make_docx(path, body, **kw)
    rep = Report()
    blocks = DocxReader(path, load_style_map(), rep, tmp_path / "media", accept_tracked_changes=accept).read()
    return blocks, rep


def paras(blocks):
    return [b for b in blocks if isinstance(b, Paragraph)]


def test_roles_and_inline_formatting(tmp_path):
    body = (
        p(r("Chương 1. Tim mạch"), style="Title")
        + p(r("Đại cương"), style="Heading1")
        + p(r("Nồng độ "), r("Na", "<w:b/>"), r("+", '<w:b/><w:vertAlign w:val="superscript"/>'),
            r(" và H"), r("2", '<w:vertAlign w:val="subscript"/>'), r("O "),
            r("in nghiêng", '<w:rStyle w:val="ItalicChar"/>'), r(" "), r("đậm", '<w:rStyle w:val="Strong"/>'))
    )
    blocks, rep = read(tmp_path, body)
    ps = paras(blocks)
    assert [x.role for x in ps] == ["chapter_title", "h1", "body"]
    # Tiêu đề đậm do paragraph style, không biến thành chữ đậm ký tự
    assert not any(run.bold for run in ps[1].runs)
    runs = ps[2].runs
    assert ps[2].text == "Nồng độ Na+ và H2O in nghiêng đậm"
    na = [x for x in runs if x.text == "Na"][0]
    plus = [x for x in runs if x.text == "+"][0]
    assert na.bold and not na.sup and plus.bold and plus.sup
    assert [x for x in runs if x.text == "2"][0].sub
    assert [x for x in runs if x.text == "in nghiêng"][0].italic
    assert [x for x in runs if x.text == "đậm"][0].bold
    assert rep.ok


def test_vietnamese_nfc_normalisation(tmp_path):
    nfd = "Việt Nam"  # dấu tổ hợp
    blocks, rep = read(tmp_path, p(r(nfd)))
    assert paras(blocks)[0].text == "Việt Nam"
    assert any("NFC" in m for m in rep.infos)


def test_numbering_is_materialised_in_order(tmp_path):
    body = (
        p(r("Một"), style="ListParagraph", num=(1, 0))
        + p(r("Hai"), style="ListParagraph", num=(1, 0))
        + p(r("Hai-a"), style="ListParagraph", num=(1, 1))
        + p(r("Hai-b"), style="ListParagraph", num=(1, 1))
        + p(r("Ba"), style="ListParagraph", num=(1, 0))
        + p(r("Danh sách mới"), style="ListParagraph", num=(3, 0))
        + p(r("Chấm"), num=(2, 0))
        + p(r("Mục La Mã"), num=(4, 0))
        + p(r("Mục La Mã 2"), num=(4, 0))
    )
    blocks, _ = read(tmp_path, body)
    ps = paras(blocks)
    assert [x.label for x in ps] == ["1.\t", "2.\t", "a)\t", "b)\t", "3.\t", "1.\t", "", "I. ", "II. "]
    assert [x.role for x in ps][:6] == ["list_number"] * 6
    assert ps[2].level == 2
    assert ps[6].role == "list_bullet"
    assert main_text(blocks)[0] == "1.\tMột"


def test_footnotes(tmp_path):
    fn = {1: p(r("", inner='<w:footnoteRef/>'), r(" Theo "), r("WHO", "<w:i/>"), r(" 2020."), style="FootnoteText")}
    body = p(r("Tăng huyết áp"), r("", inner='<w:footnoteReference w:id="1"/>'), r(" là bệnh phổ biến."))
    blocks, rep = read(tmp_path, body, footnotes=fn)
    para = paras(blocks)[0]
    assert para.text == "Tăng huyết áp là bệnh phổ biến."
    notes = para.footnotes()
    assert len(notes) == 1
    assert notes[0][0].role == "footnote"
    assert notes[0][0].text == "Theo WHO 2020."
    assert notes[0][0].runs[1].italic


def test_table_merges_header_and_widths(tmp_path):
    body = tbl(
        [2000, 1000, 1000],
        tr(tc(p(r("Thuốc"))), tc(p(r("Liều dùng")), span=2), header=True),
        tr(tc(p(r("Amoxicillin")), vmerge="restart"), tc(p(r("Người lớn"))), tc(p(r("500 mg")))),
        tr(tc(p(), vmerge="continue"), tc(p(r("Trẻ em"))), tc(p(r("25 mg/kg")))),
    )
    blocks, rep = read(tmp_path, body)
    table = blocks[0]
    assert isinstance(table, Table)
    assert table.header_rows == 1
    assert table.ncols == 3 and len(table.rows) == 3
    assert table.merges() == [(1, 0, 2, 1), (0, 1, 1, 2)]
    assert table.rows[0][2].covered and table.rows[2][0].covered
    assert [round(w, 2) for w in table.col_widths] == [0.5, 0.25, 0.25]
    assert table.rows[0][0].blocks[0].role == "table_head"
    assert table.rows[1][1].blocks[0].role == "table_body"
    assert main_text(blocks) == ["Thuốc", "Liều dùng", "Amoxicillin", "Người lớn", "500 mg", "Trẻ em", "25 mg/kg"]


def test_images_and_caption_detection(tmp_path):
    body = (
        p(r("Đoạn trước."))
        + p(r("", inner=drawing("rIdImg1", "x-quang.png")))
        + p(r("Hình 1.1. Phim X-quang ngực thẳng."))
        + p(r("Hình 1.1 cho thấy bóng tim to."))  # câu văn, không phải chú thích
    )
    blocks, rep = read(tmp_path, body, media={"rIdImg1": png_bytes(1200, 800)})
    detect_captions(blocks, load_template(TPL)["caption_patterns"])
    assert isinstance(blocks[1], Figure)
    assert Path(blocks[1].image).exists()
    assert blocks[1].source_name == "x-quang.png"
    assert blocks[2].role == "caption"
    assert blocks[3].role == "body"


def test_tracked_changes_are_an_error_unless_accepted(tmp_path):
    body = p(r("Liều "), '<w:del w:id="1" w:author="a"><w:r><w:delText>5 mg</w:delText></w:r></w:del>',
             '<w:ins w:id="2" w:author="a"><w:r><w:t>10 mg</w:t></w:r></w:ins>', r(" mỗi ngày."))
    _, rep = read(tmp_path, body)
    assert not rep.ok and "track changes" in rep.errors[0]
    blocks, rep2 = read(tmp_path, body, accept=True)
    assert rep2.ok
    assert paras(blocks)[0].text == "Liều 10 mg mỗi ngày."


def test_hidden_text_symbol_font_fields_and_toc(tmp_path):
    body = (
        p(r("Mục lục — Chương 1 ...... 5"), style="TOC1")
        + p(r("Thụ thể "), r("", inner='<w:sym w:font="Symbol" w:char="F061"/>'), r("-adrenergic và "),
            r("b", '<w:rFonts w:ascii="Symbol" w:hAnsi="Symbol"/>'), r("-blocker"),
            r("GHI CHÚ ẨN", "<w:vanish/>"))
        + p(r("Xem trang "), r("", inner='<w:fldChar w:fldCharType="begin"/>'),
            r("", inner='<w:instrText> PAGEREF _Ref1 \\h </w:instrText>'),
            r("", inner='<w:fldChar w:fldCharType="separate"/>'), r("12"),
            r("", inner='<w:fldChar w:fldCharType="end"/>'), r("."))
        + p()
    )
    blocks, rep = read(tmp_path, body)
    ps = paras(blocks)
    assert [x.text for x in ps] == ["Thụ thể α-adrenergic và β-blocker", "Xem trang 12."]
    assert any("ẩn" in w for w in rep.warnings)
    assert any("mục lục" in i for i in rep.infos)
    assert any("đoạn trống" in i for i in rep.infos)


def test_textbox_content_kept_once(tmp_path):
    body = p(r("Đoạn neo."), r("", inner=textbox_alt(p(r("Điểm chính: uống đủ nước.")))))
    blocks, rep = read(tmp_path, body)
    texts = [(b.role, b.text) for b in paras(blocks)]
    assert texts == [("body", "Đoạn neo."), ("box", "Điểm chính: uống đủ nước.")]


def test_unmapped_styles_are_reported(tmp_path):
    blocks, rep = read(tmp_path, p(r("Văn bản NXB"), style="PublisherBody"))
    assert paras(blocks)[0].role == "body"
    assert "PUB Body Indent" in rep.unmapped_styles


def test_project_style_map_takes_priority(tmp_path):
    custom = tmp_path / "map.yaml"
    custom.write_text("- {pattern: 'TX-.*', role: quote}\n", encoding="utf-8")
    path = tmp_path / "in.docx"
    make_docx(path, p(r("Trích dẫn"), style="PublisherBody"))
    rep = Report()
    blocks = DocxReader(path, load_style_map(custom), rep, tmp_path / "m").read()
    assert paras(blocks)[0].role == "quote"  # khớp qua style cha TX-Custom


def test_image_inside_textbox_not_duplicated(tmp_path):
    body = p(r("Neo."), r("", inner=textbox_alt(p(r("", inner=drawing("rIdImg1"))), p(r("Hình 2.1. Trong khung.")))))
    blocks, rep = read(tmp_path, body, media={"rIdImg1": png_bytes(600, 400)})
    figs = [b for b in blocks if isinstance(b, Figure)]
    assert len(figs) == 1
    assert [b.text for b in paras(blocks)] == ["Neo.", "Hình 2.1. Trong khung."]

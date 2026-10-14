import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from lxml import etree
from PIL import Image

from htl.build import BuildOptions, build

from docx_factory import drawing, make_docx, p, png_bytes, r, tbl, tc, tr

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "templates" / "y-khoa-19x27"
GS_CMYK = Path("/usr/share/color/icc/ghostscript/default_cmyk.icc")
ACORN = Path("/tmp/claude-0/-home-user-he-thong-layout/459633d0-efc4-54c0-9a1c-dccdb55338a7/scratchpad/node_modules/acorn")


def chapter_docx(path, n, img_px=(3000, 2000)):
    fn = {1: p(r("", inner="<w:footnoteRef/>"), r(" Chú thích của chương " + str(n) + "."))}
    body = (
        p(r(f"Chương {n}"), style="Title")
        + p(r("Đại cương"), style="Heading1")
        + p(r("Đoạn mở đầu"), r("", inner='<w:footnoteReference w:id="1"/>'), r(" có chú thích."))
        + p(r("Đoạn thứ hai với "), r("chữ nghiêng", "<w:i/>"), r(" & ký tự <đặc biệt>."))
        + p(r("", inner=drawing("rIdImg1")))
        + p(r(f"Hình {n}.1. Ảnh minh họa."))
        + p(r(f"Bảng {n}.1. Liều thuốc"))
        + tbl([3000, 3000],
              tr(tc(p(r("Thuốc"))), tc(p(r("Liều"))), header=True),
              tr(tc(p(r("A")), span=2)))
        + p(r("Mục"), num=(1, 0))
    )
    make_docx(path, body, footnotes=fn, media={"rIdImg1": png_bytes(*img_px)})


@pytest.fixture
def two_chapters(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    chapter_docx(src / "ch2.docx", 2)
    chapter_docx(src / "ch10.docx", 10, img_px=(400, 300))
    return src


def test_build_package(tmp_path, two_chapters):
    out = tmp_path / "build"
    report, out = build(BuildOptions(inputs=[str(two_chapters)], template=str(TPL), out=str(out), title="Sách thử"))
    # thứ tự tự nhiên: ch2 trước ch10
    job = json.loads((out / "job.json").read_text(encoding="utf-8"))
    assert [c["source"] for c in job["chapters"]] == ["ch2.docx", "ch10.docx"]
    assert [c["id"] for c in job["chapters"]] == ["ch01", "ch02"]
    assert job["chapters"][0]["tables"][0]["merges"] == [[0, 1, 2, 1]]
    assert job["chapters"][0]["figures"] == ["##HTLFIG0001##"]
    assert job["chapters"][0]["footnotes"] == 1

    # ICML hợp lệ, đủ style, đủ mốc
    icml = (out / "stories" / "ch01.icml").read_text(encoding="utf-8")
    root = etree.fromstring(icml.encode("utf-8"))
    names = {e.get("Name") for e in root.iter("ParagraphStyle")}
    assert {"Chapter Title", "H1", "Body First", "Body", "Figure", "Figure Caption",
            "Table Caption", "Table Head", "Table Body", "List Number", "Footnote"} <= names
    assert icml.count("##HTLFIG0001##") == 1
    assert "<?ACE 4?>" in icml
    assert "&amp; ký tự &lt;đặc biệt&gt;" in icml
    cells = root.findall(".//Cell")
    assert len(cells) == 4 and {c.get("Name") for c in cells} == {"0:0", "1:0", "0:1", "1:1"}
    story_text = "".join(e.text or "" for e in root.iter("Content"))
    assert "Đoạn mở đầu" in story_text and "1.\tMục" in story_text

    # ảnh nhỏ -> lỗi độ phân giải; ảnh lớn -> đặt rộng bằng cột
    figs = job["figures"]
    assert figs["##HTLFIG0001##"]["ppi"] >= 300
    assert figs["##HTLFIG0002##"]["ppi"] >= 299  # không bao giờ phóng to quá min_ppi
    assert any("FIG0002" in w.upper() and "ảnh nhỏ" in w for w in report.warnings)

    # Script InDesign: cấu hình nhúng được, mã hợp lệ ES3
    run = (out / "run_in_indesign.jsx").read_text(encoding="utf-8")
    assert run.startswith("//") and '#include "htl_build.jsx"' in run
    assert (out / "htl_build.jsx").exists()
    if ACORN.exists() and shutil.which("node"):
        js = "\n".join(l for l in run.splitlines() if not l.startswith("#"))
        js += "\n" + (out / "htl_build.jsx").read_text(encoding="utf-8")
        tmp_js = tmp_path / "all.js"
        tmp_js.write_text(js, encoding="utf-8")
        res = subprocess.run(
            ["node", "-e", f'require("{ACORN}").parse(require("fs").readFileSync("{tmp_js}","utf8"),{{ecmaVersion:3,allowReserved:true}})'],
            capture_output=True, text=True)
        assert res.returncode == 0, res.stderr

    content = json.loads((out / "content.json").read_text(encoding="utf-8"))
    assert content["chapters"][0]["footnotes"] == ["Chú thích của chương 2."]
    assert (out / "report.md").read_text(encoding="utf-8").startswith("# Báo cáo dựng")


@pytest.mark.skipif(not GS_CMYK.exists(), reason="không có ICC CMYK để thử")
def test_images_converted_to_cmyk(tmp_path, two_chapters):
    tpl_dir = tmp_path / "tpl"
    shutil.copytree(TPL, tpl_dir)
    data = yaml.safe_load((tpl_dir / "template.yaml").read_text(encoding="utf-8"))
    data["color"]["icc_file"] = str(GS_CMYK)
    (tpl_dir / "template.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    _, out = build(BuildOptions(inputs=[str(two_chapters)], template=str(tpl_dir), out=str(tmp_path / "b")))
    with Image.open(out / "images" / "fig0001.tif") as im:
        assert im.mode == "CMYK"
        assert im.info.get("icc_profile")
        assert round(im.info["dpi"][0]) >= 300


def test_hires_matching_by_caption_number(tmp_path, two_chapters):
    hires = tmp_path / "hires"
    hires.mkdir()
    Image.new("RGB", (4000, 3000), (10, 120, 200)).save(hires / "Fig10_1_hires.tif")
    report, out = build(BuildOptions(inputs=[str(two_chapters)], template=str(TPL),
                                     out=str(tmp_path / "b"), hires_dir=str(hires)))
    job = json.loads((out / "job.json").read_text(encoding="utf-8"))
    assert job["figures"]["##HTLFIG0002##"]["px_w"] == 4000
    assert any("Fig10_1_hires.tif" in i for i in report.infos)


def test_json_input_from_translation_system(tmp_path):
    book = {
        "title": "Sách dịch",
        "chapters": [{"blocks": [
            {"type": "paragraph", "role": "chapter_title", "runs": [{"text": "Chương 1"}]},
            {"type": "paragraph", "role": "body", "runs": [
                {"text": "Insulin "}, {"text": "glargine", "italic": True},
                {"footnote": [{"type": "paragraph", "role": "footnote", "runs": [{"text": "Tên biệt dược."}]}]}]},
        ]}],
    }
    src = tmp_path / "book.json"
    src.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    report, out = build(BuildOptions(inputs=[str(src)], template=str(TPL), out=str(tmp_path / "b")))
    assert report.ok
    content = json.loads((out / "content.json").read_text(encoding="utf-8"))
    assert content["chapters"][0]["paragraphs"] == ["Chương 1", "Insulin glargine\ue000"]
    assert content["chapters"][0]["footnotes"] == ["Tên biệt dược."]


def test_preview_then_verify_end_to_end(tmp_path, two_chapters):
    from htl.preview import render_preview
    from htl.verify import verify

    _, out = build(BuildOptions(inputs=[str(two_chapters)], template=str(TPL), out=str(tmp_path / "b"), title="Sách thử"))
    pdf = render_preview(out)
    res = verify(pdf, out)
    assert res.ok, res.to_markdown()

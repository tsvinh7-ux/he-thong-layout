"""Tạo file .docx tối thiểu (viết tay XML) để kiểm thử các tình huống khó của bản thảo."""
from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

from PIL import Image

W_NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'xmlns:v="urn:schemas-microsoft-com:vml" '
    'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'
)


def t(text: str) -> str:
    return f'<w:t xml:space="preserve">{escape(text)}</w:t>'


def r(text: str = "", rpr: str = "", inner: str = "") -> str:
    body = inner or t(text)
    return f"<w:r>{f'<w:rPr>{rpr}</w:rPr>' if rpr else ''}{body}</w:r>"


def p(*runs: str, style: str | None = None, num: tuple[int, int] | None = None) -> str:
    ppr = ""
    if style or num:
        ppr = "<w:pPr>"
        if style:
            ppr += f'<w:pStyle w:val="{style}"/>'
        if num:
            ppr += f'<w:numPr><w:ilvl w:val="{num[1]}"/><w:numId w:val="{num[0]}"/></w:numPr>'
        ppr += "</w:pPr>"
    return f"<w:p>{ppr}{''.join(runs)}</w:p>"


def drawing(rid: str, name: str = "Picture 1") -> str:
    return (
        '<w:drawing><wp:inline><wp:extent cx="100" cy="100"/>'
        f'<wp:docPr id="1" name="{name}"/>'
        '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:pic><pic:blipFill><a:blip r:embed="{rid}"/></pic:blipFill></pic:pic>'
        "</a:graphicData></a:graphic></wp:inline></w:drawing>"
    )


def textbox_alt(*paras: str) -> str:
    """Text box dạng mc:AlternateContent: Choice (wps) + Fallback (VML) trùng nội dung."""
    inner = "".join(paras)
    return (
        "<mc:AlternateContent><mc:Choice Requires=\"wps\"><w:drawing><wp:anchor>"
        '<wp:docPr id="9" name="Text Box 9"/><a:graphic><a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
        f"<wps:wsp><wps:txbx><w:txbxContent>{inner}</w:txbxContent></wps:txbx></wps:wsp>"
        "</a:graphicData></a:graphic></wp:anchor></w:drawing></mc:Choice>"
        f"<mc:Fallback><w:pict><v:shape><v:textbox><w:txbxContent>{inner}</w:txbxContent></v:textbox></v:shape></w:pict></mc:Fallback>"
        "</mc:AlternateContent>"
    )


def tc(content: str, span: int = 1, vmerge: str | None = None) -> str:
    pr = ""
    if span > 1 or vmerge is not None:
        pr = "<w:tcPr>"
        if span > 1:
            pr += f'<w:gridSpan w:val="{span}"/>'
        if vmerge is not None:
            pr += '<w:vMerge w:val="restart"/>' if vmerge == "restart" else "<w:vMerge/>"
        pr += "</w:tcPr>"
    return f"<w:tc>{pr}{content}</w:tc>"


def tr(*cells: str, header: bool = False) -> str:
    pr = "<w:trPr><w:tblHeader/></w:trPr>" if header else ""
    return f"<w:tr>{pr}{''.join(cells)}</w:tr>"


def tbl(grid: list[int], *rows: str) -> str:
    g = "".join(f'<w:gridCol w:w="{x}"/>' for x in grid)
    return f"<w:tbl><w:tblPr/><w:tblGrid>{g}</w:tblGrid>{''.join(rows)}</w:tbl>"


STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {ns}>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:rPr><w:b/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/><w:basedOn w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/><w:basedOn w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="FootnoteText"><w:name w:val="footnote text"/><w:basedOn w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="PublisherTX"><w:name w:val="TX-Custom"/><w:basedOn w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="PublisherBody"><w:name w:val="PUB Body Indent"/><w:basedOn w:val="PublisherTX"/></w:style>
<w:style w:type="character" w:styleId="Strong"><w:name w:val="Strong"/></w:style>
<w:style w:type="character" w:styleId="ItalicChar"><w:name w:val="My Italic"/><w:rPr><w:i/></w:rPr></w:style>
</w:styles>""".format(ns=W_NS)

NUMBERING = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering {ns}>
<w:abstractNum w:abstractNumId="0">
 <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl>
 <w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%2)"/></w:lvl>
</w:abstractNum>
<w:abstractNum w:abstractNumId="1">
 <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/></w:lvl>
</w:abstractNum>
<w:abstractNum w:abstractNumId="2">
 <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="upperRoman"/><w:lvlText w:val="%1."/><w:suff w:val="space"/></w:lvl>
</w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
<w:num w:numId="3"><w:abstractNumId w:val="0"/><w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>
<w:num w:numId="4"><w:abstractNumId w:val="2"/></w:num>
</w:numbering>""".format(ns=W_NS)


def footnotes_xml(notes: dict[int, str]) -> str:
    body = (
        '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
        '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
    )
    for i, paras in notes.items():
        body += f'<w:footnote w:id="{i}">{paras}</w:footnote>'
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:footnotes {W_NS}>{body}</w:footnotes>'


def png_bytes(w: int, h: int, color=(200, 30, 30), mode="RGB") -> bytes:
    im = Image.new(mode, (w, h), color)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def make_docx(path, body: str, *, footnotes: dict[int, str] | None = None,
              media: dict[str, bytes] | None = None) -> None:
    media = media or {}
    rels = ['<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
            '<Relationship Id="rIdNum" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>']
    if footnotes:
        rels.append('<Relationship Id="rIdFn" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>')
    for rid, name in ((k, k) for k in media):
        rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}.png"/>')
    doc = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W_NS}><w:body>{body}<w:sectPr/></w:body></w:document>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/></Types>')
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/numbering.xml", NUMBERING)
        if footnotes:
            z.writestr("word/footnotes.xml", footnotes_xml(footnotes))
        z.writestr("word/_rels/document.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(rels) + "</Relationships>")
        for rid, data in media.items():
            z.writestr(f"word/media/{rid}.png", data)

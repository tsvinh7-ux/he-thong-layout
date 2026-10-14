"""Sinh file ICML (InCopy story) — định dạng InDesign đọc trực tiếp.

Mỗi chương là một story. Định dạng hiển thị KHÔNG nằm ở đây: ICML chỉ gán
tên paragraph/character style; khi đặt vào tài liệu InDesign, style của mẫu
(.indt) sẽ quyết định font, cỡ chữ, khoảng cách...

Ảnh được đặt bằng mốc (marker) ##HTLFIG0001## để script InDesign thay bằng
khung ảnh thật. Nếu script chưa chạy, mốc vẫn hiện trên trang và bước kiểm
tra nội dung sẽ báo lỗi — không có ảnh nào "lặng lẽ biến mất".
"""
from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from .config import Template
from .ir import Chapter, Figure, HEADING_ROLES, Paragraph, Run, Table

FIG_MARKER = "##HTL{id}##"  # id dạng FIG0001

NONE_CHAR = "$ID/[No character style]"
NONE_PARA = "$ID/[No paragraph style]"


def fig_marker(fig_id: str) -> str:
    return FIG_MARKER.format(id=fig_id.upper())


def _attr(v) -> str:
    return quoteattr(str(v))


def _style_ref(kind: str, name: str) -> str:
    if name.startswith("$ID/"):
        return f"{kind}/{name}"
    return f"{kind}/" + name.replace(":", "%3a")


class IcmlWriter:
    def __init__(self, tpl: Template):
        self.tpl = tpl
        self.para_styles: set[str] = set()
        self.char_styles: set[str] = set()
        self.table_styles: set[str] = set()
        self._uid = 0
        cs = tpl["character_styles"]
        self.cs_bold, self.cs_italic, self.cs_bi = cs["bold"], cs["italic"], cs["bold_italic"]

    def uid(self) -> str:
        self._uid += 1
        return f"u{self._uid:x}"

    # --- đoạn văn ------------------------------------------------------------
    def _pstyle(self, role: str, level: int = 1) -> str:
        name = self.tpl.style_for(f"{role}_{level}" if role.startswith("list_") and level > 1 else role)
        if role.startswith("list_") and level > 1 and name == f"{role}_{level}":
            name = self.tpl.style_for(role)
        self.para_styles.add(name)
        return name

    def _cstyle(self, r: Run) -> str:
        if r.bold and r.italic:
            name = self.cs_bi
        elif r.bold:
            name = self.cs_bold
        elif r.italic:
            name = self.cs_italic
        else:
            return NONE_CHAR
        self.char_styles.add(name)
        return name

    def _run_xml(self, r: Run) -> str:
        if r.footnote is not None:
            return self._footnote_xml(r.footnote)
        attrs = [f'AppliedCharacterStyle={_attr(_style_ref("CharacterStyle", self._cstyle(r)))}']
        if r.sup:
            attrs.append('Position="Superscript"')
        elif r.sub:
            attrs.append('Position="Subscript"')
        if r.underline:
            attrs.append('Underline="true"')
        if r.smallcaps:
            attrs.append('Capitalization="SmallCaps"')
        elif r.caps:
            attrs.append('Capitalization="AllCaps"')
        return f"<CharacterStyleRange {' '.join(attrs)}>{self._content(r.text)}</CharacterStyleRange>"

    @staticmethod
    def _content(text: str) -> str:
        # Xuống dòng mềm (Shift+Enter) trong InDesign là U+2028 bên trong <Content>.
        return f"<Content>{escape(text)}</Content>"

    def _footnote_xml(self, paras: list[Paragraph]) -> str:
        inner = []
        for i, p in enumerate(paras):
            runs = "".join(self._run_xml(r) for r in p.runs if r.footnote is None)
            if i == 0:
                runs = (f'<CharacterStyleRange AppliedCharacterStyle={_attr(_style_ref("CharacterStyle", NONE_CHAR))}>'
                        f"<Content><?ACE 4?></Content></CharacterStyleRange>") + runs
            inner.append(
                f'<ParagraphStyleRange AppliedParagraphStyle={_attr(_style_ref("ParagraphStyle", self._pstyle("footnote")))}>'
                f"{runs}</ParagraphStyleRange>"
            )
        return (f'<CharacterStyleRange AppliedCharacterStyle={_attr(_style_ref("CharacterStyle", NONE_CHAR))}>'
                f"<Footnote>{'<Br/>'.join(inner)}</Footnote></CharacterStyleRange>")

    def _para_xml(self, p: Paragraph, role: str | None = None) -> str:
        style = self._pstyle(role or p.role, p.level)
        body = ""
        if p.label:
            body += self._run_xml(Run(text=p.label))
        body += "".join(self._run_xml(r) for r in p.runs)
        return f'<ParagraphStyleRange AppliedParagraphStyle={_attr(_style_ref("ParagraphStyle", style))}>{body}</ParagraphStyleRange>'

    def _figure_xml(self, f: Figure) -> str:
        style = self._pstyle("figure")
        return (f'<ParagraphStyleRange AppliedParagraphStyle={_attr(_style_ref("ParagraphStyle", style))}>'
                f'<CharacterStyleRange AppliedCharacterStyle={_attr(_style_ref("CharacterStyle", NONE_CHAR))}>'
                f"{self._content(fig_marker(f.id))}</CharacterStyleRange></ParagraphStyleRange>")

    # --- bảng ---------------------------------------------------------------
    def _table_xml(self, t: Table) -> str:
        ncols = t.ncols
        nrows = len(t.rows)
        tstyle = self.tpl["table_style"]
        self.table_styles.add(tstyle)
        width = self.tpl.column_w
        widths = t.col_widths if len(t.col_widths) == ncols else [1 / ncols] * ncols
        parts = [
            f'<Table Self="{self.uid()}" HeaderRowCount="{t.header_rows}" FooterRowCount="0" '
            f'BodyRowCount="{nrows - t.header_rows}" ColumnCount="{ncols}" '
            f'AppliedTableStyle={_attr(_style_ref("TableStyle", tstyle))} TableDirection="LeftToRightDirection">'
        ]
        for c in range(ncols):
            parts.append(f'<Column Self="{self.uid()}" Name="{c}" SingleColumnWidth="{widths[c] * width:.3f}"/>')
        for r, row in enumerate(t.rows):
            for c, cell in enumerate(row):
                # Ô bị gộp vẫn được ghi ra (rỗng); script InDesign sẽ gộp theo manifest.
                default_role = "table_head" if r < t.header_rows else "table_body"
                parts.append(f'<Cell Self="{self.uid()}" Name="{c}:{r}" RowSpan="1" ColumnSpan="1">')
                blocks = [] if cell.covered else cell.blocks
                if not blocks:
                    blocks = [Paragraph(role=default_role)]
                parts.append(self._blocks_xml(blocks, in_table=True))
                parts.append("</Cell>")
        parts.append("</Table>")
        anchor = self._pstyle("table")
        return (f'<ParagraphStyleRange AppliedParagraphStyle={_attr(_style_ref("ParagraphStyle", anchor))}>'
                f'<CharacterStyleRange AppliedCharacterStyle={_attr(_style_ref("CharacterStyle", NONE_CHAR))}>'
                f"{''.join(parts)}</CharacterStyleRange></ParagraphStyleRange>")

    # --- chuỗi block ---------------------------------------------------------
    def _blocks_xml(self, blocks: list, in_table: bool = False) -> str:
        out = []
        prev = None
        has_first = "body_first" in self.tpl["roles"]
        for b in blocks:
            if isinstance(b, Paragraph):
                role = b.role
                if role == "body" and has_first and not in_table and (
                    prev is None or not (isinstance(prev, Paragraph) and prev.role in ("body", "body_first"))
                ) and not (isinstance(prev, Paragraph) and prev.role in ("list_bullet", "list_number", "quote")):
                    role = "body_first"
                out.append(self._para_xml(b, role))
            elif isinstance(b, Figure):
                out.append(self._figure_xml(b))
            elif isinstance(b, Table):
                out.append(self._table_xml(b))
            prev = b
        # Giữa các đoạn là <Br/> (ký tự xuống đoạn), giống cấu trúc ICML của InDesign/Pandoc.
        return "\n<Br/>\n".join(out)

    # --- tài liệu ICML ------------------------------------------------------
    def story(self, ch: Chapter) -> str:
        body = self._blocks_xml(ch.blocks)
        self.para_styles.add(NONE_PARA)
        self.char_styles.add(NONE_CHAR)
        pstyles = "".join(
            f'<ParagraphStyle Self={_attr(_style_ref("ParagraphStyle", n))} Name={_attr(n)}/>'
            for n in sorted(self.para_styles)
        )
        cstyles = "".join(
            f'<CharacterStyle Self={_attr(_style_ref("CharacterStyle", n))} Name={_attr(n)}/>'
            for n in sorted(self.char_styles)
        )
        tstyles = "".join(
            f'<TableStyle Self={_attr(_style_ref("TableStyle", n))} Name={_attr(n)}/>'
            for n in sorted(self.table_styles | {"$ID/[Basic Table]"})
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<?aid style="50" type="snippet" readerVersion="6.0" featureSet="513" product="8.0(370)" ?>\n'
            '<?aid SnippetType="InCopyInterchange"?>\n'
            '<Document DOMVersion="8.0" Self="htl_doc">\n'
            f'<RootCharacterStyleGroup Self="htl_cs">{cstyles}</RootCharacterStyleGroup>\n'
            f'<RootParagraphStyleGroup Self="htl_ps">{pstyles}</RootParagraphStyleGroup>\n'
            f'<RootTableStyleGroup Self="htl_ts">{tstyles}</RootTableStyleGroup>\n'
            f'<Story Self="htl_story_{escape(ch.id)}" AppliedTOCStyle="n" TrackChanges="false" '
            f'StoryTitle={_attr(ch.id)} AppliedNamedGrid="n">\n'
            '<StoryPreference OpticalMarginAlignment="true" OpticalMarginSize="12" '
            'FrameType="TextFrameType" StoryOrientation="Horizontal" StoryDirection="LeftToRightDirection"/>\n'
            '<InCopyExportOption IncludeGraphicProxies="true" IncludeAllResources="false"/>\n'
            f"{body}\n"
            "</Story>\n</Document>\n"
        )


def write_chapter_icml(ch: Chapter, tpl: Template, path) -> dict:
    w = IcmlWriter(tpl)
    xml = w.story(ch)
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)
    return {"paragraph_styles": sorted(w.para_styles), "character_styles": sorted(w.char_styles)}


__all__ = ["IcmlWriter", "write_chapter_icml", "fig_marker", "HEADING_ROLES"]

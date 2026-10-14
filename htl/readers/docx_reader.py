"""Đọc bản thảo Word (.docx), kể cả file dịch xuất từ SDL Trados.

Nguyên tắc: KHÔNG thêm, bớt hay đảo thứ tự nội dung. Mọi trường hợp không
chắc chắn (track changes, chữ ẩn, biểu đồ nhúng, ký tự không đổi được...)
đều được ghi vào báo cáo; trường hợp có thể làm sai nội dung là LỖI.
"""
from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from ..config import StyleMap
from ..ir import Cell, Figure, Paragraph, Run, Table
from ..report import Report
from ..textnorm import SYMBOL_FONTS, clean, map_symbol_text, symbol_char

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "v": "urn:schemas-microsoft-com:vml",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def q(tag: str) -> str:
    p, local = tag.split(":")
    return f"{{{NS[p]}}}{local}"


W_VAL = q("w:val")
R_ID = q("r:id")
R_EMBED = q("r:embed")
R_LINK = q("r:link")

_TRUE = {None, "1", "true", "on"}


def _toggle(el) -> bool | None:
    if el is None:
        return None
    return el.get(W_VAL) in _TRUE


def _int(el, default=0) -> int:
    if el is None:
        return default
    try:
        return int(el.get(W_VAL))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Đánh số danh sách (Word tự sinh số, không lưu trong văn bản)
# ---------------------------------------------------------------------------

def _roman(n: int) -> str:
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
            (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


def _letters(n: int) -> str:
    # Kiểu Word: a..z, aa..zz, aaa..
    if n <= 0:
        return str(n)
    k = (n - 1) // 26 + 1
    return chr(ord("a") + (n - 1) % 26) * k


def format_number(n: int, fmt: str) -> str | None:
    if fmt in ("decimal", "decimalZero"):
        return f"{n:02d}" if fmt == "decimalZero" and n < 10 else str(n)
    if fmt == "lowerLetter":
        return _letters(n)
    if fmt == "upperLetter":
        return _letters(n).upper()
    if fmt == "lowerRoman":
        return _roman(n).lower()
    if fmt == "upperRoman":
        return _roman(n)
    if fmt == "none":
        return ""
    return None


@dataclass
class Level:
    start: int = 1
    fmt: str = "decimal"
    text: str = "%1."
    suffix: str = "tab"


class Numbering:
    def __init__(self, root, report: Report):
        self.report = report
        self.abstract: dict[str, dict[int, Level]] = {}
        self.nums: dict[str, tuple[str, dict[int, int]]] = {}
        self.counters: dict[str, list[int | None]] = {}
        self.seen_nums: set[str] = set()
        if root is None:
            return
        for an in root.findall(q("w:abstractNum")):
            levels = {}
            for lvl in an.findall(q("w:lvl")):
                il = int(lvl.get(q("w:ilvl"), "0"))
                fmt = lvl.find(q("w:numFmt"))
                txt = lvl.find(q("w:lvlText"))
                suff = lvl.find(q("w:suff"))
                levels[il] = Level(
                    start=_int(lvl.find(q("w:start")), 1),
                    fmt=fmt.get(W_VAL) if fmt is not None else "decimal",
                    text=txt.get(W_VAL, "") if txt is not None else "",
                    suffix=suff.get(W_VAL) if suff is not None else "tab",
                )
            self.abstract[an.get(q("w:abstractNumId"))] = levels
        for num in root.findall(q("w:num")):
            aid = num.find(q("w:abstractNumId"))
            overrides = {}
            for ov in num.findall(q("w:lvlOverride")):
                so = ov.find(q("w:startOverride"))
                if so is not None:
                    overrides[int(ov.get(q("w:ilvl"), "0"))] = _int(so, 1)
            if aid is not None:
                self.nums[num.get(q("w:numId"))] = (aid.get(W_VAL), overrides)

    def next_label(self, num_id: str, ilvl: int) -> tuple[str, str] | None:
        """Trả về (kiểu, nhãn) cho một đoạn có đánh số. kiểu: 'bullet' | 'number'."""
        if num_id not in self.nums:
            return None
        aid, overrides = self.nums[num_id]
        levels = self.abstract.get(aid, {})
        lvl = levels.get(ilvl)
        if lvl is None:
            return None
        cnt = self.counters.setdefault(aid, [None] * 10)
        if num_id not in self.seen_nums:
            self.seen_nums.add(num_id)
            for il, start in overrides.items():
                if 0 <= il < 10:
                    cnt[il] = start - 1
                    for d in range(il + 1, 10):
                        cnt[d] = None
        cnt[ilvl] = (cnt[ilvl] if cnt[ilvl] is not None else lvl.start - 1) + 1
        for d in range(ilvl + 1, 10):
            cnt[d] = None
        if lvl.fmt == "bullet":
            return ("bullet", "")

        def repl(m):
            k = int(m.group(1)) - 1
            lv = levels.get(k, Level())
            n = cnt[k] if cnt[k] is not None else lv.start
            s = format_number(n, lv.fmt)
            if s is None:
                self.report.warn(f"Kiểu đánh số Word '{lv.fmt}' chưa hỗ trợ, dùng số thường.")
                s = str(n)
            return s

        label = re.sub(r"%(\d)", repl, lvl.text)
        if not label:
            return ("number", "")
        suffix = {"tab": "\t", "space": " "}.get(lvl.suffix, "")
        return ("number", label + suffix)


# ---------------------------------------------------------------------------
# Trình đọc
# ---------------------------------------------------------------------------

LIST_ROLES = {"body", "list_bullet", "list_number"}


class DocxReader:
    def __init__(
        self,
        path: str | Path,
        style_map: StyleMap,
        report: Report,
        media_dir: str | Path,
        media_prefix: str = "img",
        accept_tracked_changes: bool = False,
    ):
        self.path = Path(path)
        self.style_map = style_map
        self.report = report
        self.media_dir = Path(media_dir)
        self.media_prefix = media_prefix
        self.accept_tracked = accept_tracked_changes
        self.zf = zipfile.ZipFile(self.path)
        self.names = set(self.zf.namelist())
        self.doc = self._xml("word/document.xml")
        self.rels = self._rels("word/_rels/document.xml.rels")
        self._load_styles()
        self.numbering = Numbering(self._xml("word/numbering.xml"), report)
        self.notes = {}
        for part, tag in (("word/footnotes.xml", "w:footnote"), ("word/endnotes.xml", "w:endnote")):
            root = self._xml(part)
            if root is None:
                continue
            rels = self._rels(part.replace("word/", "word/_rels/") + ".rels")
            for fn in root.findall(q(tag)):
                if fn.get(q("w:type")) in ("separator", "continuationSeparator", "continuationNotice"):
                    continue
                self.notes[(tag, fn.get(q("w:id")))] = (fn, rels)
        self.field_stack: list[str] = []
        self.img_count = 0
        self.stats = {"ins": 0, "del": 0, "hidden": 0, "page_breaks": 0, "nfc": 0, "empty": 0,
                      "toc": 0, "equations": 0, "endnotes": 0}
        self._cur_rels = self.rels

    # --- tiện ích đọc gói --------------------------------------------------
    def _xml(self, name):
        if name not in self.names:
            return None
        parser = etree.XMLParser(resolve_entities=False, huge_tree=True, remove_blank_text=False)
        return etree.fromstring(self.zf.read(name), parser)

    def _rels(self, name) -> dict:
        root = self._xml(name)
        out = {}
        if root is None:
            return out
        base = posixpath.dirname(name.replace("_rels/", "").rsplit(".rels", 1)[0])
        for r in root.findall(q("rel:Relationship")):
            target = r.get("Target")
            external = r.get("TargetMode") == "External"
            if not external:
                target = posixpath.normpath(posixpath.join(base, target)).lstrip("/")
            out[r.get("Id")] = (target, external)
        return out

    def _load_styles(self):
        self.styles: dict[str, dict] = {}
        self.default_pstyle = None
        root = self._xml("word/styles.xml")
        if root is None:
            return
        for s in root.findall(q("w:style")):
            sid = s.get(q("w:styleId"))
            name_el = s.find(q("w:name"))
            based = s.find(q("w:basedOn"))
            ppr = s.find(q("w:pPr"))
            num = None
            if ppr is not None and ppr.find(q("w:numPr")) is not None:
                npr = ppr.find(q("w:numPr"))
                nid = npr.find(q("w:numId"))
                num = (nid.get(W_VAL) if nid is not None else None, _int(npr.find(q("w:ilvl")), 0))
            self.styles[sid] = {
                "name": name_el.get(W_VAL) if name_el is not None else sid,
                "type": s.get(q("w:type")),
                "based": based.get(W_VAL) if based is not None else None,
                "rpr": s.find(q("w:rPr")),
                "num": num,
            }
            if s.get(q("w:type")) == "paragraph" and s.get(q("w:default")) in _TRUE - {None}:
                self.default_pstyle = sid

    def _chain(self, sid):
        seen = set()
        while sid and sid in self.styles and sid not in seen:
            seen.add(sid)
            yield sid, self.styles[sid]
            sid = self.styles[sid]["based"]

    # --- API ---------------------------------------------------------------
    def read(self) -> list:
        body = self.doc.find(q("w:body"))
        blocks = self._blocks(body, ctx={})
        self._summarize()
        return blocks

    def _summarize(self):
        s, rep, src = self.stats, self.report, self.path.name
        if s["ins"] or s["del"]:
            msg = (f"{src}: còn track changes ({s['ins']} chỗ chèn, {s['del']} chỗ xóa).")
            if self.accept_tracked:
                rep.warn(msg + " Đã CHẤP NHẬN toàn bộ thay đổi theo tùy chọn --accept-changes.")
            else:
                rep.error(msg + " Hãy Accept/Reject trong Word hoặc chạy lại với --accept-changes.")
        if s["hidden"]:
            rep.warn(f"{src}: {s['hidden']} đoạn chữ bị ẩn (hidden text) trong Word — KHÔNG đưa vào sách. Kiểm tra lại nếu cần.")
        if s["nfc"]:
            rep.info(f"{src}: chuẩn hóa Unicode NFC cho {s['nfc']} đoạn chữ (dấu tiếng Việt tổ hợp -> dựng sẵn; hiển thị không đổi).")
        if s["empty"]:
            rep.info(f"{src}: bỏ {s['empty']} đoạn trống (dùng để tạo khoảng cách trong Word).")
        if s["toc"]:
            rep.info(f"{src}: bỏ {s['toc']} đoạn mục lục tự động của Word (InDesign sẽ tạo mục lục mới).")
        if s["page_breaks"]:
            rep.info(f"{src}: bỏ qua {s['page_breaks']} ngắt trang/ngắt cột thủ công (dàn trang do mẫu quyết định).")
        if s["equations"]:
            rep.warn(f"{src}: {s['equations']} công thức toán (Equation) đã chuyển thành chữ thường — designer cần kiểm tra/dựng lại.")
        if s["endnotes"]:
            rep.warn(f"{src}: {s['endnotes']} endnote được xử lý như chú thích chân trang (footnote).")

    # --- block-level -------------------------------------------------------
    def _blocks(self, parent, ctx) -> list:
        out = []
        for el in parent:
            tag = el.tag
            if tag == q("w:p"):
                out += self._paragraph(el, ctx)
            elif tag == q("w:tbl"):
                out.append(self._table(el, ctx))
            elif tag in (q("w:sdt"),):
                content = el.find(q("w:sdtContent"))
                if content is not None:
                    out += self._blocks(content, ctx)
            elif tag in (q("w:customXml"), q("w:ins"), q("w:moveTo")):
                out += self._blocks(el, ctx)
            elif tag in (q("w:del"), q("w:moveFrom")):
                self.stats["del"] += 1
                if not self.accept_tracked:
                    out += self._blocks(el, ctx)
            elif tag == q("mc:AlternateContent"):
                choice = el.find(q("mc:Choice"))
                if choice is not None:
                    out += self._blocks(choice, ctx)
        return out

    def _role_for_style(self, sid) -> tuple[str, str]:
        sid = sid or self.default_pstyle
        name = self.styles.get(sid, {}).get("name", sid or "")
        for cid, st in self._chain(sid):
            role = self.style_map.role(st["name"])
            if role:
                if cid != sid and cid == self.default_pstyle:
                    # Chỉ khớp nhờ kế thừa từ "Normal": vẫn báo để người dùng xem lại
                    # (style riêng của NXB như "CT", "FGC"... thường kế thừa Normal).
                    self.report.unmapped_styles[name] += 1
                return name, role
        if name:
            self.report.unmapped_styles[name] += 1
        return name, "body"

    def _paragraph(self, p, ctx) -> list:
        ppr = p.find(q("w:pPr"))
        sid = None
        num = None
        if ppr is not None:
            ps = ppr.find(q("w:pStyle"))
            sid = ps.get(W_VAL) if ps is not None else None
            npr = ppr.find(q("w:numPr"))
            if npr is not None:
                nid = npr.find(q("w:numId"))
                num = (nid.get(W_VAL) if nid is not None else None, _int(npr.find(q("w:ilvl")), 0))
        style_name, role = self._role_for_style(sid)
        if num is None or num[0] is None:
            for _, st in self._chain(sid or self.default_pstyle):
                if st["num"]:
                    sn = st["num"]
                    num = (sn[0], num[1] if num else sn[1])
                    break

        force = ctx.get("force_role")
        if force == "footnote" and role in LIST_ROLES:
            role = "footnote"
        elif force == "box" and role == "body":
            role = "box"
        if ctx.get("in_table") and role == "body":
            role = "table_head" if ctx.get("header") else "table_body"

        items: list = []  # Run | Figure | ("blocks", [...])
        self._inline(p, items, ctx, rpr_base={})

        # Đánh số
        label, level = "", 1
        if role == "toc":
            pass
        elif num and num[0] not in (None, "0"):
            res = self.numbering.next_label(num[0], num[1])
            if res:
                kind, lab = res
                level = min(num[1] + 1, 3)
                if role in LIST_ROLES:
                    role = "list_bullet" if kind == "bullet" else "list_number"
                    label = lab if kind == "number" else ""
                elif kind == "number":
                    label = lab
                # bullet trên tiêu đề/chú thích: bỏ qua ký hiệu bullet

        # Tách đoạn tại vị trí ảnh; khối text box đặt sau đoạn
        out: list = []
        after: list = []
        cur = Paragraph(role=role, level=level, label=clean(label), source_style=style_name)

        def flush():
            nonlocal cur
            self._finish_para(cur)
            if role == "toc":
                if not cur.is_empty():
                    self.stats["toc"] += 1
            elif not cur.is_empty():
                self.report.style_usage[(style_name, cur.role)] += 1
                out.append(cur)
            cur = Paragraph(role=role, level=level, source_style=style_name)

        for it in items:
            if isinstance(it, Run):
                cur.runs.append(it)
            elif isinstance(it, Figure):
                flush()
                out.append(it)
            elif isinstance(it, tuple) and it[0] == "blocks":
                after += it[1]
        flush()
        if not out and not after and role != "toc":
            self.stats["empty"] += 1
        return out + after

    def _finish_para(self, para: Paragraph):
        merged: list[Run] = []
        for r in para.runs:
            if r.footnote is None:
                t = clean(r.text)
                if t != r.text:
                    self.stats["nfc"] += 1
                r.text = t
                if not r.text:
                    continue
            if merged and merged[-1].same_format(r):
                merged[-1].text += r.text
            else:
                merged.append(r)
        para.runs = merged

    # --- inline ------------------------------------------------------------
    def _run_props(self, rpr) -> dict:
        props: dict = {}
        if rpr is None:
            return props
        rs = rpr.find(q("w:rStyle"))
        if rs is not None:
            chain = list(self._chain(rs.get(W_VAL)))
            for _, st in reversed(chain):
                props.update(self._direct_props(st["rpr"]))
                name = st["name"].lower()
                if name in ("strong",):
                    props["bold"] = True
                if name in ("emphasis",):
                    props["italic"] = True
        props.update(self._direct_props(rpr))
        return props

    def _direct_props(self, rpr) -> dict:
        d: dict = {}
        if rpr is None:
            return d
        for key, tag in (("bold", "w:b"), ("italic", "w:i"), ("smallcaps", "w:smallCaps"),
                         ("caps", "w:caps"), ("hidden", "w:vanish")):
            v = _toggle(rpr.find(q(tag)))
            if v is not None:
                d[key] = v
        u = rpr.find(q("w:u"))
        if u is not None:
            d["underline"] = u.get(W_VAL) != "none"
        va = rpr.find(q("w:vertAlign"))
        if va is not None:
            d["sup"] = va.get(W_VAL) == "superscript"
            d["sub"] = va.get(W_VAL) == "subscript"
        fonts = rpr.find(q("w:rFonts"))
        if fonts is not None:
            f = fonts.get(q("w:ascii")) or fonts.get(q("w:hAnsi"))
            if f:
                d["font"] = f
        return d

    def _make_run(self, text, props) -> Run:
        return Run(
            text=text,
            bold=props.get("bold", False),
            italic=props.get("italic", False),
            underline=props.get("underline", False),
            sup=props.get("sup", False),
            sub=props.get("sub", False),
            smallcaps=props.get("smallcaps", False),
            caps=props.get("caps", False),
        )

    def _emit_text(self) -> bool:
        return all(s == "result" for s in self.field_stack)

    def _inline(self, parent, items, ctx, rpr_base):
        for el in parent:
            tag = el.tag
            if tag == q("w:r"):
                self._run(el, items, ctx)
            elif tag in (q("w:hyperlink"), q("w:smartTag"), q("w:customXml"), q("w:fldSimple"),
                         q("w:dir"), q("w:bdo")):
                self._inline(el, items, ctx, rpr_base)
            elif tag == q("w:sdt"):
                c = el.find(q("w:sdtContent"))
                if c is not None:
                    self._inline(c, items, ctx, rpr_base)
            elif tag in (q("w:ins"), q("w:moveTo")):
                self.stats["ins"] += 1
                self._inline(el, items, ctx, rpr_base)
            elif tag in (q("w:del"), q("w:moveFrom")):
                self.stats["del"] += 1
                if not self.accept_tracked:
                    # Chưa chấp nhận: giữ nguyên như bản gốc trước khi sửa
                    self._inline_deleted(el, items, ctx)
            elif tag in (q("m:oMath"), q("m:oMathPara")):
                txt = "".join(t.text or "" for t in el.iter(q("m:t")))
                if txt:
                    self.stats["equations"] += 1
                    items.append(Run(text=txt, italic=False))
            elif tag == q("mc:AlternateContent"):
                self._alternate(el, items, ctx, inline=True)

    def _inline_deleted(self, el, items, ctx):
        # w:del chứa w:r với w:delText; trước khi chấp nhận thì đó là nội dung gốc.
        for r in el.iter(q("w:r")):
            props = self._run_props(r.find(q("w:rPr")))
            txt = "".join(t.text or "" for t in r.iter(q("w:delText")))
            if txt:
                items.append(self._make_run(txt, props))

    def _alternate(self, el, items, ctx, inline):
        choice = el.find(q("mc:Choice"))
        fallback = el.find(q("mc:Fallback"))
        tmp: list = []
        if choice is not None:
            self._mixed(choice, tmp, ctx)
        unsupported = any(isinstance(x, Figure) and not x.image for x in tmp)
        if (choice is None or unsupported) and fallback is not None:
            tmp2: list = []
            self._mixed(fallback, tmp2, ctx)
            if any(isinstance(x, Figure) and x.image for x in tmp2):
                tmp = tmp2
        items += tmp

    def _mixed(self, container, items, ctx):
        """Nội dung mc:Choice/mc:Fallback có thể là w:r (cấp đoạn) hoặc w:drawing (cấp run)."""
        for el in container:
            if el.tag == q("w:r"):
                self._run(el, items, ctx)
            elif el.tag in (q("w:hyperlink"), q("w:smartTag"), q("w:ins"), q("w:sdt")):
                self._inline([el], items, ctx, {})
            else:
                self._run_children([el], items, ctx, {})

    def _run(self, r, items, ctx):
        props = self._run_props(r.find(q("w:rPr")))
        self._run_children(r, items, ctx, props)

    def _run_children(self, r, items, ctx, props):
        font = (props.get("font") or "").lower()
        is_symbol = font in SYMBOL_FONTS
        for el in r:
            tag = el.tag
            if tag == q("w:fldChar"):
                t = el.get(q("w:fldCharType"))
                if t == "begin":
                    self.field_stack.append("instr")
                elif t == "separate" and self.field_stack:
                    self.field_stack[-1] = "result"
                elif t == "end" and self.field_stack:
                    self.field_stack.pop()
                continue
            if not self._emit_text():
                continue
            if tag == q("w:t"):
                txt = el.text or ""
                if props.get("hidden"):
                    if txt.strip():
                        self.stats["hidden"] += 1
                    continue
                if is_symbol:
                    txt, bad = map_symbol_text(txt)
                    if bad:
                        self.report.error(f"{self.path.name}: ký tự font Symbol không đổi được sang Unicode: {bad!r}")
                items.append(self._make_run(txt, props))
            elif tag in (q("w:tab"), q("w:ptab")):
                items.append(self._make_run("\t", props))
            elif tag == q("w:br"):
                if el.get(q("w:type")) in ("page", "column"):
                    self.stats["page_breaks"] += 1
                else:
                    items.append(self._make_run(" ", props))
            elif tag == q("w:cr"):
                items.append(self._make_run(" ", props))
            elif tag == q("w:noBreakHyphen"):
                items.append(self._make_run("‑", props))
            elif tag == q("w:softHyphen"):
                items.append(self._make_run("­", props))
            elif tag == q("w:sym"):
                code = int(el.get(q("w:char"), "0"), 16)
                f = (el.get(q("w:font")) or "").lower()
                ch = symbol_char(code) if f in SYMBOL_FONTS else None
                if ch is None:
                    ch = "�"
                    self.report.error(
                        f"{self.path.name}: ký tự đặc biệt font '{el.get(q('w:font'))}' mã {code:04X} "
                        "không đổi được sang Unicode — đã đánh dấu bằng ký tự �, cần sửa bản thảo.")
                items.append(self._make_run(ch, props))
            elif tag in (q("w:footnoteReference"), q("w:endnoteReference")):
                kind = "w:footnote" if tag == q("w:footnoteReference") else "w:endnote"
                if kind == "w:endnote":
                    self.stats["endnotes"] += 1
                note = self.notes.get((kind, el.get(q("w:id"))))
                if note is None:
                    self.report.error(f"{self.path.name}: không tìm thấy nội dung chú thích id={el.get(q('w:id'))}.")
                    continue
                items.append(Run(footnote=self._footnote(*note)))
            elif tag == q("w:drawing"):
                self._drawing(el, items, ctx)
            elif tag == q("w:pict") or tag == q("w:object"):
                self._vml(el, items, ctx, is_object=(tag == q("w:object")))
            elif tag == q("mc:AlternateContent"):
                self._alternate(el, items, ctx, inline=True)
            elif tag in (q("w:delText"),):
                pass

    def _footnote(self, fn, rels) -> list[Paragraph]:
        saved_stack, self.field_stack = self.field_stack, []
        saved_rels, self._cur_rels = self._cur_rels, rels
        try:
            blocks = self._blocks(fn, ctx={"force_role": "footnote"})
        finally:
            self.field_stack = saved_stack
            self._cur_rels = saved_rels
        paras = []
        for b in blocks:
            if isinstance(b, Paragraph):
                b.role = "footnote"
                paras.append(b)
            else:
                self.report.error(f"{self.path.name}: chú thích chân trang chứa bảng/ảnh — chưa hỗ trợ, cần xử lý tay.")
        if paras and paras[0].runs and paras[0].runs[0].footnote is None:
            paras[0].runs[0].text = paras[0].runs[0].text.lstrip()
            if not paras[0].runs[0].text:
                paras[0].runs.pop(0)
        return paras

    # --- ảnh, text box -----------------------------------------------------
    def _textbox_blocks(self, container, items, ctx):
        for tx in container.iter(q("w:txbxContent")):
            sub = self._blocks(tx, ctx={**ctx, "force_role": "box"})
            if sub:
                self.report.warn(
                    f"{self.path.name}: nội dung trong text box (khung chữ nổi) đã được đưa vào dòng chính, "
                    "ngay sau đoạn chứa khung, với vai trò 'box'.")
                items.append(("blocks", sub))

    def _drawing(self, el, items, ctx):
        doc_pr = el.find(".//" + q("wp:docPr"))
        name = ""
        if doc_pr is not None:
            name = doc_pr.get("descr") or doc_pr.get("name") or ""
        # Ảnh nằm trong text box sẽ được đọc khi đọc nội dung text box — bỏ ở đây để không nhân đôi.
        blips = [b for b in el.iter(q("a:blip")) if not _in_textbox(b, el)]
        found = False
        for blip in blips:
            rid = blip.get(R_EMBED) or blip.get(R_LINK)
            fig = self._figure_from_rel(rid, name, external=blip.get(R_LINK) is not None)
            if fig:
                items.append(fig)
                found = True
        gdata = el.find(".//" + q("a:graphicData"))
        uri = gdata.get("uri", "") if gdata is not None else ""
        if not found and ("chart" in uri or "diagram" in uri):
            kind = "Biểu đồ (chart)" if "chart" in uri else "SmartArt"
            self.report.error(
                f"{self.path.name}: {kind} nhúng trong Word không phải ảnh — cần xuất thành ảnh độ phân giải cao "
                "và cung cấp qua thư mục ảnh gốc.")
            items.append(Figure(image="", source_name=name or kind))
        self._textbox_blocks(el, items, ctx)

    def _vml(self, el, items, ctx, is_object):
        for img in el.iter(q("v:imagedata")):
            if _in_textbox(img, el):
                continue
            rid = img.get(R_ID)
            fig = self._figure_from_rel(rid, "", external=False)
            if fig:
                if is_object:
                    self.report.warn(
                        f"{self.path.name}: đối tượng OLE (công thức/Visio/...) chỉ lấy được ảnh xem trước "
                        f"({Path(fig.image).name}) — chất lượng có thể thấp, nên thay bằng ảnh gốc.")
                items.append(fig)
        self._textbox_blocks(el, items, ctx)

    def _figure_from_rel(self, rid, name, external) -> Figure | None:
        if not rid or rid not in self._cur_rels:
            return None
        target, is_ext = self._cur_rels[rid]
        self.img_count += 1
        if is_ext or external:
            p = Path(target.replace("file:///", "").replace("file://", ""))
            if not p.is_absolute():
                p = self.path.parent / p
            if not p.exists():
                self.report.error(f"{self.path.name}: ảnh liên kết ngoài không tìm thấy: {target}")
                return Figure(image="", source_name=name or target)
            return Figure(image=str(p), source_name=name or p.name)
        if target not in self.names:
            self.report.error(f"{self.path.name}: thiếu ảnh {target} trong file Word.")
            return Figure(image="", source_name=name)
        ext = posixpath.splitext(target)[1].lower() or ".bin"
        self.media_dir.mkdir(parents=True, exist_ok=True)
        out = self.media_dir / f"{self.media_prefix}_{self.img_count:03d}{ext}"
        out.write_bytes(self.zf.read(target))
        return Figure(image=str(out), source_name=name or posixpath.basename(target))

    # --- bảng --------------------------------------------------------------
    def _table(self, tbl, ctx) -> Table:
        grid = [_int_attr(g, q("w:w")) for g in tbl.findall(q("w:tblGrid") + "/" + q("w:gridCol"))]
        rows_el = []
        for el in tbl:
            if el.tag == q("w:tr"):
                rows_el.append(el)
            elif el.tag in (q("w:sdt"), q("w:customXml")):
                rows_el += list(el.iter(q("w:tr")))
        table = Table()
        anchors: dict[tuple[int, int], tuple[int, int]] = {}
        header_done = False
        for r, tr in enumerate(rows_el):
            trpr = tr.find(q("w:trPr"))
            is_header = False
            if trpr is not None and _toggle(trpr.find(q("w:tblHeader"))):
                is_header = not header_done
            if is_header:
                table.header_rows += 1
            else:
                header_done = True
            row: list[Cell] = []
            if trpr is not None:
                for _ in range(_int(trpr.find(q("w:gridBefore")), 0)):
                    row.append(Cell())
            tcs = []
            for el in tr:
                if el.tag == q("w:tc"):
                    tcs.append(el)
                elif el.tag in (q("w:sdt"), q("w:customXml")):
                    tcs += list(el.iter(q("w:tc")))
            for tc in tcs:
                tcpr = tc.find(q("w:tcPr"))
                span = _int(tcpr.find(q("w:gridSpan")), 1) if tcpr is not None else 1
                vm = tcpr.find(q("w:vMerge")) if tcpr is not None else None
                c = len(row)
                cell_ctx = {**ctx, "in_table": True, "header": is_header}
                blocks = self._cell_blocks(tc, cell_ctx)
                if vm is not None and vm.get(W_VAL) != "restart" and r > 0 and (r - 1, c) in anchors:
                    ar, ac = anchors[(r - 1, c)]
                    anchor = table.rows[ar][ac]
                    anchor.rowspan = r - ar + 1
                    if blocks:
                        self.report.warn(f"{self.path.name}: ô gộp dọc trong bảng có nội dung ở ô phụ — đã nối vào ô chính.")
                        anchor.blocks += blocks
                    for k in range(span):
                        row.append(Cell(covered=True))
                        anchors[(r, c + k)] = (ar, ac)
                else:
                    row.append(Cell(blocks=blocks, colspan=span))
                    anchors[(r, c)] = (r, c)
                    for k in range(1, span):
                        row.append(Cell(covered=True))
                        anchors[(r, c + k)] = (r, c)
            table.rows.append(row)
        ncols = max([len(grid)] + [len(rw) for rw in table.rows]) if table.rows else len(grid)
        for row in table.rows:
            while len(row) < ncols:
                row.append(Cell())
        if len(grid) == ncols and all(g > 0 for g in grid):
            total = sum(grid)
            table.col_widths = [g / total for g in grid]
        else:
            table.col_widths = [1 / ncols] * ncols if ncols else []
        return table

    def _cell_blocks(self, tc, ctx) -> list:
        out = []
        for el in tc:
            if el.tag == q("w:p"):
                out += self._paragraph(el, ctx)
            elif el.tag == q("w:tbl"):
                self.report.warn(f"{self.path.name}: bảng lồng trong bảng — đã trải phẳng nội dung bảng con theo thứ tự đọc.")
                inner = self._table(el, ctx)
                for row in inner.rows:
                    for cell in row:
                        if not cell.covered:
                            out += cell.blocks
            elif el.tag in (q("w:sdt"),):
                c = el.find(q("w:sdtContent"))
                if c is not None:
                    out += self._cell_blocks(c, ctx)
        return out


def _int_attr(el, attr) -> int:
    try:
        return int(el.get(attr))
    except (TypeError, ValueError):
        return 0


def _in_textbox(node, stop) -> bool:
    for anc in node.iterancestors():
        if anc is stop:
            return False
        if anc.tag == q("w:txbxContent"):
            return True
    return False

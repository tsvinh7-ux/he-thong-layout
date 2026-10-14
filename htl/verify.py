"""Đối chiếu nội dung PDF với bản thảo: KHÔNG THIẾU, KHÔNG THỪA, ĐÚNG THỨ TỰ.

Cách làm:
1. Lấy chuỗi từ (token) chuẩn từ bản thảo (content.json do bước build tạo).
2. Trích chữ từ PDF theo thứ tự trong file, nối lại các từ bị ngắt dòng có gạch nối.
3. Dóng hàng tuần tự hai chuỗi. Mọi từ của bản thảo phải xuất hiện đúng thứ tự.
   Phần "thừa" trong PDF chỉ được phép là: số trang, tiêu đề chạy (running head),
   ký hiệu bullet, số chú thích, và nội dung chú thích chân trang (được kiểm riêng).

So sánh không phân biệt hoa/thường và kiểu dấu nháy (“ ” vs "), vì đó là
hình thức trình bày (All Caps, typographer's quotes), không phải nội dung.
"""
from __future__ import annotations

import bisect
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .ir import FN_MARK
from .textnorm import norm_for_compare, tokens

K = 4  # độ dài k-gram dùng để đồng bộ lại sau chỗ lệch
LOOKAHEAD_PDF = 4000
LOOKAHEAD_EXP = 400

DEFAULT_ALLOWED_EXTRA = r"^([0-9]+|[ivxlcdm]+|[•◦▪■□○●–—\-*·►▸✓])$"


@dataclass
class Issue:
    kind: str  # missing | extra | marker | footnote | figure
    where: str
    text: str


@dataclass
class VerifyResult:
    expected_tokens: int = 0
    pdf_tokens: int = 0
    matched: int = 0
    issues: list[Issue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_markdown(self) -> str:
        lines = ["# Báo cáo đối chiếu nội dung", ""]
        lines.append(f"**Kết quả:** {'ĐẠT — nội dung khớp 100% bản thảo' if self.ok else 'KHÔNG ĐẠT'}")
        lines.append("")
        lines.append(f"- Số từ bản thảo: {self.expected_tokens}")
        lines.append(f"- Số từ trong PDF: {self.pdf_tokens}")
        lines.append(f"- Số từ khớp đúng thứ tự: {self.matched}")
        lines.append("")
        labels = {
            "missing": "THIẾU/SAI so với bản thảo",
            "extra": "THỪA so với bản thảo",
            "marker": "Ảnh chưa được đặt",
            "footnote": "Chú thích chân trang",
            "figure": "Hình",
        }
        for kind, label in labels.items():
            items = [i for i in self.issues if i.kind == kind]
            if items:
                lines.append(f"## {label} ({len(items)})")
                for i in items[:500]:
                    lines.append(f"- [{i.where}] `{i.text}`")
                if len(items) > 500:
                    lines.append(f"- … và {len(items) - 500} mục khác")
                lines.append("")
        if self.notes:
            lines.append("## Ghi chú")
            lines += [f"- {n}" for n in self.notes]
        return "\n".join(lines)


# ---------------------------------------------------------------------------

def pdf_tokens(pdf_path: str | Path, vocab: set[str]) -> tuple[list[str], list[int]]:
    """Trích token từ PDF theo thứ tự nội dung; trả về (tokens, số trang của từng token)."""
    import pymupdf

    toks: list[str] = []
    pages: list[int] = []
    with pymupdf.open(str(pdf_path)) as doc:
        for pno, page in enumerate(doc, 1):
            words = page.get_text("words", sort=False)
            i = 0
            while i < len(words):
                w = words[i]
                text = w[4]
                nxt = words[i + 1] if i + 1 < len(words) else None
                line_end = nxt is None or (nxt[5], nxt[6]) != (w[5], w[6])
                if nxt is not None and line_end and text.endswith(("-", "­", "‐")):
                    stem = text[:-1]
                    a = norm_for_compare(stem + nxt[4])
                    b = norm_for_compare(text + nxt[4])
                    if a in vocab or b in vocab:
                        merged = a if a in vocab else b
                        toks.append(merged)
                        pages.append(pno)
                        i += 2
                        continue
                for t in tokens(text):
                    toks.append(t)
                    pages.append(pno)
                i += 1
    return toks, pages


def _kgram_index(seq: list[str]) -> dict[tuple, list[int]]:
    idx: dict[tuple, list[int]] = {}
    for i in range(len(seq) - K + 1):
        idx.setdefault(tuple(seq[i:i + K]), []).append(i)
    return idx


def _find(idx, key, lo, hi) -> int | None:
    pos = idx.get(key)
    if not pos:
        return None
    k = bisect.bisect_left(pos, lo)
    if k < len(pos) and pos[k] <= hi:
        return pos[k]
    return None


_PAT_CACHE: dict[str, re.Pattern] = {}


def _eq(e: str, p: str) -> bool:
    """So token bản thảo với token PDF. Mốc chú thích trong bản thảo khớp với
    số chú thích (1–3 chữ số) mà InDesign tự đánh ở đúng vị trí đó."""
    if e == p:
        return True
    if FN_MARK not in e:
        return False
    pat = _PAT_CACHE.get(e)
    if pat is None:
        pat = re.compile(r"\d{0,3}".join(re.escape(x) for x in e.split(FN_MARK)))
        _PAT_CACHE[e] = pat
    return pat.fullmatch(p) is not None


def align(exp: list[str], pdf: list[str]):
    """Dóng hàng tuần tự. Trả về (matched_count, missing_ranges, extra_ranges)."""
    pidx = _kgram_index(pdf)
    eidx = _kgram_index(exp)
    i = j = matched = 0
    missing: list[tuple[int, int]] = []
    extra: list[tuple[int, int]] = []
    n, m = len(exp), len(pdf)
    while i < n and j < m:
        if _eq(exp[i], pdf[j]):
            i += 1
            j += 1
            matched += 1
            continue
        # Khác nhau do cách tách từ (ví dụ chỉ số trên dính liền / tách rời)
        hit = _concat_match(exp, pdf, i, j)
        if hit:
            i, j = i + hit[0], j + hit[1]
            matched += hit[0]
            continue
        # PDF có phần thừa (tiêu đề chạy, số trang, chú thích chân trang...)?
        jj = _find(pidx, tuple(exp[i:i + K]), j + 1, j + LOOKAHEAD_PDF) if i + K <= n else None
        # Bản thảo có phần bị thiếu trong PDF?
        ii = _find(eidx, tuple(pdf[j:j + K]), i + 1, i + LOOKAHEAD_EXP) if j + K <= m else None
        if jj is not None and (ii is None or (jj - j) <= (ii - i) * 8):
            extra.append((j, jj))
            j = jj
        elif ii is not None:
            missing.append((i, ii))
            i = ii
        else:
            missing.append((i, i + 1))
            extra.append((j, j + 1))
            i += 1
            j += 1
    if i < n:
        missing.append((i, n))
    if j < m:
        extra.append((j, m))
    return matched, _merge_ranges(missing), _merge_ranges(extra)


def _concat_match(exp, pdf, i, j):
    for a in range(1, 4):
        for b in range(1, 4):
            if a == b == 1:
                continue
            if _eq("".join(exp[i:i + a]), "".join(pdf[j:j + b])):
                return a, b
    return None


def _merge_ranges(rs):
    out = []
    for a, b in sorted(rs):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


# ---------------------------------------------------------------------------

def verify(pdf_path: str | Path, build_dir: str | Path, allowed_extra: list[str] | None = None) -> VerifyResult:
    build_dir = Path(build_dir)
    content = json.loads((build_dir / "content.json").read_text(encoding="utf-8"))
    res = VerifyResult()

    exp: list[str] = []
    where: list[str] = []
    headings: list[list[str]] = []
    for ch in content["chapters"]:
        for pi, ptext in enumerate(ch["paragraphs"]):
            # Mốc chú thích đứng riêng (sau dấu cách) -> bỏ; số chú thích là phần "thừa" hợp lệ.
            t = [x for x in tokens(ptext) if x != FN_MARK]
            exp += t
            where += [f"{ch['id']} ¶{pi + 1}"] * len(t)
        headings += [tokens(h) for h in ch.get("headings", []) if h.strip()]
    if content.get("title"):
        headings.append(tokens(content["title"]))
    fn_list = [(ch["id"], fi + 1, tokens(f)) for ch in content["chapters"] for fi, f in enumerate(ch["footnotes"])]

    vocab = {t.replace(FN_MARK, "") for t in exp} | {t for _, _, ft in fn_list for t in ft}
    pdf, pages = pdf_tokens(pdf_path, vocab)
    res.expected_tokens, res.pdf_tokens = len(exp), len(pdf)

    # Ảnh chưa đặt (mốc ##HTLFIGxxxx## còn trong PDF)
    for t, p in zip(pdf, pages):
        if "##htlfig" in t:
            res.issues.append(Issue("marker", f"trang {p}", t))

    matched, missing, extra = align(exp, pdf)
    res.matched = matched
    for a, b in missing:
        res.issues.append(Issue("missing", where[a], " ".join(exp[a:b])[:300]))

    # Phần thừa: trừ chú thích chân trang, tiêu đề chạy, số trang, bullet
    allowed = [re.compile(DEFAULT_ALLOWED_EXTRA)] + [re.compile(x, re.IGNORECASE) for x in (allowed_extra or [])]
    extra_tokens: list[tuple[int, str]] = [(k, pdf[k]) for a, b in extra for k in range(a, b)]
    consumed: set[int] = set()

    # Chú thích chân trang: phải xuất hiện đủ và đúng thứ tự trong phần thừa
    pos = 0
    seq = [t for _, t in extra_tokens]
    for ch_id, fi, ft in fn_list:
        if not ft:
            continue
        hits = _find_gapped(seq, ft, pos)
        if hits is None:
            res.issues.append(Issue("footnote", f"{ch_id} chú thích {fi}", " ".join(ft)[:300]))
            continue
        for k in hits:
            consumed.add(extra_tokens[k][0])
        pos = hits[-1] + 1

    # Tiêu đề chạy: chuỗi trùng với tiêu đề chương/mục hoặc tên sách
    for h in headings:
        start = 0
        while True:
            found = _find_subseq(seq, h, start)
            if found is None:
                break
            for k in range(found, found + len(h)):
                consumed.add(extra_tokens[k][0])
            start = found + len(h)

    leftovers: list[list[int]] = []
    for k, t in extra_tokens:
        if k in consumed or any(r.match(t) for r in allowed):
            continue
        if leftovers and leftovers[-1][-1] == k - 1:
            leftovers[-1].append(k)
        else:
            leftovers.append([k])
    for grp in leftovers:
        res.issues.append(Issue("extra", f"trang {pages[grp[0]]}", " ".join(pdf[k] for k in grp)[:300]))

    if res.ok:
        res.notes.append("Toàn bộ chữ của bản thảo có mặt trong PDF theo đúng thứ tự; không có nội dung lạ.")
    return res


def _find_subseq(seq: list[str], sub: list[str], start: int) -> int | None:
    n = len(sub)
    if n == 0:
        return None
    first = sub[0]
    for i in range(start, len(seq) - n + 1):
        if seq[i] == first and seq[i:i + n] == sub:
            return i
    return None


def _find_gapped(seq: list[str], sub: list[str], start: int, max_gap: int = 60) -> list[int] | None:
    """Tìm `sub` theo thứ tự trong `seq`, cho phép xen kẽ (chú thích chân trang bị
    tách sang trang sau thì giữa hai phần có số trang, tiêu đề chạy...)."""
    first = None
    for i in range(start, len(seq)):
        if seq[i] == sub[0] and seq[i:i + min(len(sub), K)] == sub[:K]:
            first = i
            break
    if first is None:
        return None
    hits = [first]
    k = first + 1
    for t in sub[1:]:
        limit = k + max_gap
        while k < len(seq) and k < limit and seq[k] != t:
            k += 1
        if k >= len(seq) or k >= limit:
            return None
        hits.append(k)
        k += 1
    return hits

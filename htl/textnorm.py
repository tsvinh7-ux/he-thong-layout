"""Chuẩn hóa văn bản: Unicode tiếng Việt, ký tự font Symbol, tách từ để đối chiếu."""
from __future__ import annotations

import re
import unicodedata

# Ký tự font "Symbol" (bản thảo cũ hay dùng cho chữ Hy Lạp: α, β, μ, ...)
# Mã Symbol -> Unicode. Word lưu w:sym với mã F0xx hoặc lưu chữ Latin thường
# kèm font Symbol.
_SYMBOL_BASE = {
    0x41: "Α", 0x42: "Β", 0x43: "Χ", 0x44: "Δ", 0x45: "Ε", 0x46: "Φ", 0x47: "Γ",
    0x48: "Η", 0x49: "Ι", 0x4A: "ϑ", 0x4B: "Κ", 0x4C: "Λ", 0x4D: "Μ", 0x4E: "Ν",
    0x4F: "Ο", 0x50: "Π", 0x51: "Θ", 0x52: "Ρ", 0x53: "Σ", 0x54: "Τ", 0x55: "Υ",
    0x56: "ς", 0x57: "Ω", 0x58: "Ξ", 0x59: "Ψ", 0x5A: "Ζ",
    0x61: "α", 0x62: "β", 0x63: "χ", 0x64: "δ", 0x65: "ε", 0x66: "φ", 0x67: "γ",
    0x68: "η", 0x69: "ι", 0x6A: "ϕ", 0x6B: "κ", 0x6C: "λ", 0x6D: "μ", 0x6E: "ν",
    0x6F: "ο", 0x70: "π", 0x71: "θ", 0x72: "ρ", 0x73: "σ", 0x74: "τ", 0x75: "υ",
    0x76: "ϖ", 0x77: "ω", 0x78: "ξ", 0x79: "ψ", 0x7A: "ζ",
    0x20: " ", 0x21: "!", 0x22: "∀", 0x23: "#", 0x24: "∃", 0x25: "%", 0x26: "&",
    0x27: "∋", 0x28: "(", 0x29: ")", 0x2A: "∗", 0x2B: "+", 0x2C: ",", 0x2D: "−",
    0x2E: ".", 0x2F: "/", 0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4",
    0x35: "5", 0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9", 0x3A: ":", 0x3B: ";",
    0x3C: "<", 0x3D: "=", 0x3E: ">", 0x3F: "?", 0x40: "≅", 0x5B: "[", 0x5C: "∴",
    0x5D: "]", 0x5E: "⊥", 0x5F: "_", 0x7B: "{", 0x7C: "|", 0x7D: "}", 0x7E: "∼",
    0xA1: "ϒ", 0xA2: "′", 0xA3: "≤", 0xA4: "⁄", 0xA5: "∞", 0xA6: "ƒ", 0xA7: "♣",
    0xA8: "♦", 0xA9: "♥", 0xAA: "♠", 0xAB: "↔", 0xAC: "←", 0xAD: "↑", 0xAE: "→",
    0xAF: "↓", 0xB0: "°", 0xB1: "±", 0xB2: "″", 0xB3: "≥", 0xB4: "×", 0xB5: "∝",
    0xB6: "∂", 0xB7: "•", 0xB8: "÷", 0xB9: "≠", 0xBA: "≡", 0xBB: "≈", 0xBC: "…",
    0xBF: "↵", 0xC0: "ℵ", 0xC4: "⊗", 0xC5: "⊕", 0xC6: "∅", 0xC7: "∩", 0xC8: "∪",
    0xC9: "⊃", 0xCA: "⊇", 0xCB: "⊄", 0xCC: "⊂", 0xCD: "⊆", 0xCE: "∈", 0xCF: "∉",
    0xD0: "∠", 0xD1: "∇", 0xD2: "®", 0xD3: "©", 0xD4: "™", 0xD5: "∏", 0xD6: "√",
    0xD7: "⋅", 0xD8: "¬", 0xD9: "∧", 0xDA: "∨", 0xDB: "⇔", 0xDC: "⇐", 0xDD: "⇑",
    0xDE: "⇒", 0xDF: "⇓", 0xE0: "◊", 0xE1: "〈", 0xE5: "∑", 0xF1: "〉", 0xF2: "∫",
}

SYMBOL_FONTS = {"symbol"}


def symbol_char(code: int) -> str | None:
    """Đổi mã ký tự font Symbol (có thể ở vùng F0xx) sang Unicode."""
    if 0xF000 <= code <= 0xF0FF:
        code -= 0xF000
    return _SYMBOL_BASE.get(code)


def map_symbol_text(text: str) -> tuple[str, list[str]]:
    """Đổi chuỗi gõ bằng font Symbol sang Unicode. Trả về (chuỗi, ký tự không đổi được)."""
    out, bad = [], []
    for ch in text:
        m = symbol_char(ord(ch))
        if m is None:
            bad.append(ch)
            out.append(ch)
        else:
            out.append(m)
    return "".join(out), bad


# Ký tự điều khiển không hợp lệ trong XML 1.0 (trừ tab).
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def clean(text: str) -> str:
    """Chuẩn hóa NFC (bắt buộc với tiếng Việt) và bỏ ký tự điều khiển lỗi."""
    return _CTRL.sub("", unicodedata.normalize("NFC", text))


# ---------------------------------------------------------------------------
# Chuẩn hóa để ĐỐI CHIẾU (không dùng để xuất bản)
# ---------------------------------------------------------------------------

_QUOTES = str.maketrans({
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "‘": "'", "’": "'", "‚": "'", "′": "'",
    "‑": "-",  # gạch nối không ngắt
    " ": " ", " ": " ",
})
_DROP = dict.fromkeys(map(ord, "­​‌‍﻿⁠"), None)


def norm_for_compare(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_QUOTES).translate(_DROP)
    return unicodedata.normalize("NFC", text.casefold())


_WS = re.compile(r"\s+")


def tokens(text: str) -> list[str]:
    return [t for t in _WS.split(norm_for_compare(text)) if t]

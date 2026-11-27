"""Chuẩn hoá id: ascii snake_case, bỏ dấu tiếng Việt."""
from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def strip_diacritics(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def slugify(text: str, fallback: str = "x") -> str:
    """'Chú Tư' -> 'chu_tu'; 'Chợ đêm (Q.5)' -> 'cho_dem_q_5'."""
    s = _NON_ALNUM.sub("_", strip_diacritics(text).lower()).strip("_")
    if not s:
        return fallback
    if s[0].isdigit():
        s = f"{fallback}_{s}"
    return s


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)

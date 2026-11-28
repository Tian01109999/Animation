"""Đối chiếu câu thoại/lời kể trong storyboard với đoạn văn của script.txt.

Storyboard không lưu đoạn văn gốc, nên dò lần lượt từng câu (theo thứ tự) trong kịch bản đã
chuẩn hoá thành danh sách từ. Mỗi dòng không trống của kịch bản là một đoạn văn.
Câu được AI viết lại khác chữ vẫn khớp nếu đủ nửa số từ trùng; không khớp → None.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_WORD = re.compile(r"\w+", re.UNICODE)
MIN_WINDOW = 400          # số từ tối thiểu dò phía trước vị trí hiện tại
MIN_SHARE = 0.5           # tỷ lệ từ trùng tối thiểu để coi là khớp


def _words(text: str) -> list[str]:
    return _WORD.findall(unicodedata.normalize("NFC", text or "").lower())


def script_words(script_text: str) -> tuple[list[str], list[int]]:
    """(các từ của kịch bản, số thứ tự đoạn văn của từng từ)."""
    words: list[str] = []
    para: list[int] = []
    for idx, block in enumerate(ln for ln in (script_text or "").splitlines() if ln.strip()):
        w = _words(block)
        words += w
        para += [idx] * len(w)
    return words, para


def line_paragraphs(script_text: str, texts: list[str]) -> list[tuple[int, int] | None]:
    """Với từng câu (theo thứ tự phim): (đoạn văn chứa đầu câu, đoạn văn chứa cuối câu) hoặc None."""
    words, para = script_words(script_text)
    out: list[tuple[int, int] | None] = []
    cursor = 0
    for text in texts:
        toks = _words(text)
        if not toks or not words:
            out.append(None)
            continue
        hit = _find(words, toks, cursor)
        if hit is None and cursor:
            hit = _find(words, toks, max(0, cursor - 3 * len(toks)))   # câu lặp lại/đảo nhẹ thứ tự
        if hit is None:
            out.append(None)
            continue
        a, b = hit
        out.append((para[a], para[b]))
        cursor = b + 1
    return out


def _find(words: list[str], toks: list[str], cursor: int) -> tuple[int, int] | None:
    m = min(3, len(toks))
    window = max(MIN_WINDOW, 4 * len(toks))
    stop = min(len(words), cursor + window)
    # nhanh: khớp nguyên văn vài từ đầu
    for j in range(cursor, max(cursor, stop - m + 1)):
        if words[j:j + m] == toks[:m]:
            end = min(len(words) - 1, j + len(toks) - 1)
            if len(toks) <= m or words[end - m + 1:end + 1] == toks[-m:]:
                return j, end
            break
    # chậm: câu bị viết lại → so khớp mờ trong cửa sổ
    seg = words[cursor:stop]
    if not seg:
        return None
    blocks = [b for b in SequenceMatcher(None, seg, toks, autojunk=False).get_matching_blocks() if b.size]
    if sum(b.size for b in blocks) < MIN_SHARE * len(toks):
        return None
    big = [b for b in blocks if b.size >= 2] or blocks
    return cursor + big[0].a, cursor + big[-1].a + big[-1].size - 1

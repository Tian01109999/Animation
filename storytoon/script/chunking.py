"""Chia kịch bản dài thành các đoạn ~3-4k ký tự theo ranh giới chương / đoạn văn."""
from __future__ import annotations

import re

from .ids import nfc

TARGET_CHARS = 3500
MAX_CHARS = 4200
# đoạn tối thiểu trước khi cho phép cắt tại tiêu đề chương
MIN_CHARS_BEFORE_CHAPTER_BREAK = 800

_CHAPTER_RE = re.compile(
    r"^\s*(#{1,6}\s+\S|(chương|chuong|chapter|phần|phan|hồi|hoi|tập|tap)\s+[\w\dIVXLC]+\b)",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def is_chapter_heading(paragraph: str) -> bool:
    first = paragraph.strip().splitlines()[0] if paragraph.strip() else ""
    return bool(_CHAPTER_RE.match(first)) and len(first) <= 120


def split_paragraphs(text: str) -> list[str]:
    text = nfc(text).replace("\r\n", "\n").replace("\r", "\n")
    if re.search(r"\n\s*\n", text):
        parts = re.split(r"\n\s*\n", text)
    else:
        parts = text.split("\n")
    return [p.strip() for p in parts if p.strip()]


def _split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    out: list[str] = []
    cur = ""
    for sent in _SENTENCE_SPLIT_RE.split(paragraph):
        if cur and len(cur) + 1 + len(sent) > max_chars:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    # câu đơn quá dài (hiếm): cắt cứng
    final: list[str] = []
    for piece in out:
        while len(piece) > max_chars:
            final.append(piece[:max_chars])
            piece = piece[max_chars:]
        if piece:
            final.append(piece)
    return final


def split_script(
    text: str,
    *,
    target_chars: int = TARGET_CHARS,
    max_chars: int = MAX_CHARS,
) -> list[str]:
    """Trả về danh sách đoạn (mỗi đoạn là các paragraph nối bằng dòng trống).

    - Ưu tiên cắt ngay trước tiêu đề chương (nếu đoạn hiện tại đã đủ dài).
    - Không vượt quá max_chars (trừ khi 1 câu đơn dài hơn).
    - Kịch bản ngắn hơn target -> 1 đoạn.
    """
    paragraphs: list[str] = []
    for p in split_paragraphs(text):
        paragraphs.extend(_split_long_paragraph(p, max_chars) if len(p) > max_chars else [p])

    chunks: list[list[str]] = []
    cur: list[str] = []
    cur_len = 0
    for p in paragraphs:
        heading = is_chapter_heading(p)
        # không tách tiêu đề chương khỏi nội dung ngay sau nó
        after_heading = bool(cur) and is_chapter_heading(cur[-1])
        should_break = bool(cur) and (
            (heading and cur_len >= MIN_CHARS_BEFORE_CHAPTER_BREAK)
            or cur_len + len(p) + 2 > max_chars
            or (cur_len >= target_chars and not after_heading)
        )
        if should_break:
            chunks.append(cur)
            cur, cur_len = [], 0
        cur.append(p)
        cur_len += len(p) + 2
    if cur:
        chunks.append(cur)
    return ["\n\n".join(c) for c in chunks]

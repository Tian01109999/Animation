"""Gộp các Storyboard từng đoạn + hậu xử lý để renderer luôn nhận dữ liệu hợp lệ.

merge_part(acc, part)  : chuẩn hoá id của `part` theo những gì `acc` đã biết rồi nối vào `acc`.
finalize(sb, ...)      : đánh số lại shot, điền giọng, tạo stub cho id thiếu, kẹp slot/action/...,
                         đảm bảo nametag lần đầu xuất hiện, NFC toàn bộ chữ.
"""
from __future__ import annotations

import logging
from typing import Any

from ..schema import CharacterDef, CharacterInShot, LocationDef, Overlay, Shot, Storyboard
from . import vocab
from .ids import nfc, slugify

log = logging.getLogger(__name__)
_NARRATOR_ALIASES = {"", "narrator", "nguoi_ke", "nguoi_ke_chuyen", "dan_truyen", "voice_over", "vo"}
_MOOD_ALIASES = {
    "suspense": "tense", "tension": "tense", "danger": "tense",
    "creepy": "horror", "scary": "horror", "fear": "horror", "dark": "horror", "ghost": "horror",
    "peaceful": "calm", "neutral": "calm", "daily": "calm",
    "happy": "warm", "tender": "warm", "nostalgic": "warm", "family": "warm",
    "sorrow": "sad", "melancholy": "sad", "grief": "sad",
    "mysterious": "mystery", "eerie": "mystery",
    "police": "investigation", "detective": "investigation", "interrogation": "investigation",
    "chase": "action", "fight": "action", "escape": "action",
    "reveal": "shock", "twist": "shock",
    "hope": "hopeful", "ending": "hopeful", "relief": "hopeful",
    "hacker": "tech", "technology": "tech", "cyber": "tech",
}


# ---------------------------------------------------------------- tiện ích

def _nfc_deep(obj: Any) -> Any:
    if isinstance(obj, str):
        return nfc(obj).strip()
    if isinstance(obj, list):
        return [_nfc_deep(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_nfc_deep(v) for v in obj)
    if isinstance(obj, dict):
        return {k: _nfc_deep(v) for k, v in obj.items()}
    return obj


def normalize_text(sb: Storyboard) -> Storyboard:
    """NFC + strip mọi chuỗi."""
    return Storyboard.model_validate(_nfc_deep(sb.model_dump()))


class _IdResolver:
    """Ánh xạ id thô (LLM) -> id chuẩn, dựa vào id + tên của những gì đã biết."""

    def __init__(self, known: dict[str, str]) -> None:
        # known: canonical id -> display name
        self.by_name = {slugify(name): cid for cid, name in known.items() if name}
        self.known = set(known)
        self.map: dict[str, str] = {}

    def define(self, raw_id: str, name: str) -> str:
        cid = slugify(raw_id or name)
        if cid not in self.known:
            cid = self.by_name.get(slugify(name), cid) if name else cid
        self.map[raw_id] = cid
        self.known.add(cid)
        if name:
            self.by_name.setdefault(slugify(name), cid)
        return cid

    def resolve(self, raw_id: str) -> str:
        if raw_id in self.map:
            return self.map[raw_id]
        cid = slugify(raw_id)
        if cid in self.known:
            return cid
        return self.by_name.get(cid, cid)


def _fill_blank_fields(dst: Any, src: Any, fields: tuple[str, ...]) -> None:
    for f in fields:
        if not getattr(dst, f) and getattr(src, f):
            setattr(dst, f, getattr(src, f))


# ---------------------------------------------------------------- gộp

def merge_part(acc: Storyboard, part: Storyboard) -> Storyboard:
    """Nối `part` vào `acc` (sửa tại chỗ và trả về acc). Shot id sẽ được đánh số lại ở finalize()."""
    part = normalize_text(part)
    if not acc.title and part.title:
        acc.title = part.title

    chars = _IdResolver({c.id: c.name for c in acc.characters})
    for cdef in part.characters:
        cid = chars.define(cdef.id, cdef.name)
        existing = acc.character(cid)
        if existing is None:
            acc.characters.append(cdef.model_copy(update={"id": cid}))
        else:
            _fill_blank_fields(existing, cdef, ("role", "description", "voice", "asset_id", "archetype"))
            for tag in cdef.tags:
                if tag not in existing.tags:
                    existing.tags.append(tag)

    locs = _IdResolver({l.id: l.name for l in acc.locations})
    for ldef in part.locations:
        lid = locs.define(ldef.id, ldef.name)
        existing_loc = acc.location(lid)
        if existing_loc is None:
            acc.locations.append(ldef.model_copy(update={"id": lid}))
        else:
            _fill_blank_fields(existing_loc, ldef, ("description", "asset_id"))
            for s in ldef.signs:
                if s not in existing_loc.signs:
                    existing_loc.signs.append(s)

    def res_char(raw: str | None) -> str | None:
        return chars.resolve(raw) if raw else raw

    def res_speaker(raw: str) -> str:
        return vocab.NARRATOR if slugify(raw, "") in _NARRATOR_ALIASES else chars.resolve(raw)

    def res_loc(raw: str) -> str:
        if raw.startswith("insert:"):
            return "insert:" + slugify(raw.split(":", 1)[1], "insert")
        return locs.resolve(raw)

    for shot in part.shots:
        shot.location = res_loc(shot.location)
        shot.focus = res_char(shot.focus)
        for ch in shot.characters:
            ch.id = chars.resolve(ch.id)
        for line in shot.lines:
            line.speaker = res_speaker(line.speaker)
        for ov in shot.overlays:
            ov.character_id = res_char(ov.character_id)
        acc.shots.append(shot)
    return acc


# ---------------------------------------------------------------- hậu xử lý

def _stub_character(cid: str) -> CharacterDef:
    name = "Tôi" if cid == "toi" else cid.replace("_", " ").title()
    return CharacterDef(id=cid, name=name, role="", description="")


def _stub_location(lid: str) -> LocationDef:
    return LocationDef(id=lid, name=lid.replace("_", " ").title(), description="")


def _default_voice(c: CharacterDef, voices: dict[str, str]) -> str:
    return voices["female"] if c.gender == "female" else voices["male"]


def _clamp_slots(chars: list[CharacterInShot]) -> None:
    used: set[str] = set()
    for ch in chars:
        slot = slugify(ch.slot or "", "")
        if slot not in vocab.SLOTS or slot in used:
            slot = next((s for s in vocab.SLOT_FILL_ORDER if s not in used), vocab.DEFAULT_SLOT)
        ch.slot = slot
        used.add(slot)


def _clean_sfx(names: list[str]) -> list[str]:
    """Đổi về tên chuẩn của thư viện âm thanh, bỏ tên không có, bỏ trùng (tối đa 3 âm / shot)."""
    from ..audio import library

    has_catalog = bool(library.sfx_guide())
    out: list[str] = []
    for raw in names:
        if not raw or not raw.strip():
            continue
        name = slugify(raw, "sfx")
        if has_catalog:
            canon = library.known_sfx(name)
            if canon is None:
                log.info("Bỏ hiệu ứng không có trong thư viện: %s", raw)
                continue
            name = canon
        if name not in out:
            out.append(name)
    return out[:3]


def _clamp_mood(mood: str | None) -> str | None:
    if not mood:
        return None
    m = slugify(mood, "")
    m = _MOOD_ALIASES.get(m, m)
    return m if m in vocab.MUSIC_MOODS else None


def finalize(
    sb: Storyboard,
    *,
    voices: dict[str, str] | None = None,
    auto_nametags: bool = True,
) -> Storyboard:
    """Hậu xử lý toàn bộ storyboard (sửa tại chỗ và trả về)."""
    voices = voices or {"male": vocab.VOICE_MALE, "female": vocab.VOICE_FEMALE}
    sb.title = sb.title or "Không tên"

    # bỏ định nghĩa trùng id
    seen: set[str] = set()
    sb.characters = [c for c in sb.characters if not (c.id in seen or seen.add(c.id))]
    seen = set()
    sb.locations = [l for l in sb.locations if not (l.id in seen or seen.add(l.id))]

    def ensure_char(cid: str) -> None:
        if cid and cid != vocab.NARRATOR and sb.character(cid) is None:
            sb.characters.append(_stub_character(cid))

    introduced: set[str] = set()
    # Nametag: vị trí "chuẩn" = lần xuất hiện đầu tiên không phải wide (nếu không có thì lần đầu).
    # Nametag do LLM/người đặt được giữ nếu nằm ở hoặc trước vị trí chuẩn; nếu muộn hơn -> tự thêm ở
    # vị trí chuẩn (nametag muộn sẽ bị bỏ vì nhân vật đã được giới thiệu).
    planned_first: dict[str, int] = {}
    for idx, s in enumerate(sb.shots):
        for o in s.overlays:
            if o.kind == "nametag":
                cid = o.character_id or sb_char_by_name(sb, o.title)
                if cid:
                    planned_first.setdefault(cid, idx)
    first_any: dict[str, int] = {}
    first_framed: dict[str, int] = {}
    for idx, s in enumerate(sb.shots):
        for ch in s.characters:
            first_any.setdefault(ch.id, idx)
            if s.framing != "wide":
                first_framed.setdefault(ch.id, idx)
    auto_tag_at: dict[int, list[str]] = {}
    if auto_nametags:
        for cid, idx in first_any.items():
            at = first_framed.get(cid, idx)
            if cid != vocab.NARRATOR and planned_first.get(cid, at + 1) > at:
                auto_tag_at.setdefault(at, []).append(cid)

    kept: list[Shot] = []
    for idx, shot in enumerate(sb.shots):
        shot.lines = [ln for ln in shot.lines if ln.text.strip()]
        if not shot.lines and not shot.characters and not shot.overlays and not shot.location:
            continue  # shot rỗng hoàn toàn

        # địa điểm
        if not shot.location:
            shot.location = kept[-1].location if kept else (sb.locations[0].id if sb.locations else "unknown")
        if not shot.location.startswith("insert:") and sb.location(shot.location) is None:
            sb.locations.append(_stub_location(shot.location))

        # nhân vật trong khung
        uniq: dict[str, CharacterInShot] = {}
        for ch in shot.characters:
            if ch.id and ch.id != vocab.NARRATOR and ch.id not in uniq:
                uniq[ch.id] = ch
        shot.characters = list(uniq.values())
        for ch in shot.characters:
            ensure_char(ch.id)
            if ch.action not in vocab.ACTIONS:
                ch.action = vocab.DEFAULT_ACTION
            if ch.prop:
                ch.prop = slugify(ch.prop, "prop")
        _clamp_slots(shot.characters)

        # người nói
        for ln in shot.lines:
            ensure_char(ln.speaker)

        # focus
        ids_in_shot = [c.id for c in shot.characters]
        if shot.focus not in ids_in_shot:
            shot.focus = None
        if shot.focus is None and shot.framing in ("close", "extreme_close") and ids_in_shot:
            speakers = [ln.speaker for ln in shot.lines if ln.speaker in ids_in_shot]
            shot.focus = speakers[0] if speakers else ids_in_shot[0]

        # phụ đề
        if not shot.subtitle and shot.lines:
            shot.subtitle = " ".join(ln.text for ln in shot.lines)

        # overlays + nametag lần đầu
        overlays: list[Overlay] = []
        for ov in shot.overlays:
            if ov.kind == "nametag":
                cid = ov.character_id or sb_char_by_name(sb, ov.title)
                if not cid or cid in introduced:
                    continue
                ensure_char(cid)
                ov.character_id = cid
                introduced.add(cid)
            overlays.append(ov)
        if auto_nametags:
            for cid in ids_in_shot:
                if cid not in introduced and cid in auto_tag_at.get(idx, ()):
                    cdef = sb.character(cid)
                    assert cdef is not None
                    overlays.append(Overlay(kind="nametag", title=cdef.name,
                                            subtitle=cdef.role or None, character_id=cid))
                    introduced.add(cid)
        shot.overlays = overlays

        # hiệu ứng: bỏ tên lạ / trùng; overlay cctv luôn kèm hiệu ứng cctv (khử màu + scanline)
        effects = [slugify(e, "") for e in shot.effects]
        if any(o.kind == "cctv" for o in shot.overlays):
            effects.append("cctv")
        shot.effects = list(dict.fromkeys(e for e in effects if e in vocab.EFFECTS))

        shot.sfx = _clean_sfx(shot.sfx)
        shot.music_mood = _clamp_mood(shot.music_mood)
        lo, hi = vocab.MIN_DURATION_RANGE
        shot.min_duration = min(max(shot.min_duration, lo), hi)
        kept.append(shot)

    for i, shot in enumerate(kept, start=1):
        shot.id = f"s{i:03d}"
    sb.shots = kept

    for c in sb.characters:
        if c.voice not in vocab.KNOWN_VOICES and not (c.voice or "").startswith("vi-VN-"):
            c.voice = _default_voice(c, voices)
    return sb


def sb_char_by_name(sb: Storyboard, name: str) -> str | None:
    key = slugify(name, "")
    for c in sb.characters:
        if slugify(c.name, "") == key or c.id == key:
            return c.id
    return None

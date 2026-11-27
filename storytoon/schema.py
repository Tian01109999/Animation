"""Pydantic models — nguồn sự thật duy nhất cho dữ liệu storyboard. Xem docs/SPEC.md."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Framing = Literal["wide", "medium", "close", "extreme_close"]
CameraMove = Literal["static", "zoom_in", "zoom_out", "pan_left", "pan_right", "push_in_slow", "shake"]
OverlayKind = Literal[
    "nametag", "location_card", "chapter_card", "rule_card", "time_card",
    # thêm (xem docs/STYLE_GUIDE.md §Overlay, assets/catalog/overlays.json):
    "cctv", "phone_chat", "phone_bank", "missing_poster", "map_card", "timeline",
    "info_card", "job_ad", "rule_list", "badge",
]
Expression = Literal[
    "neutral", "happy", "sad", "angry", "scared", "evil", "surprised",
    # thêm (công thức vẽ: docs/STYLE_GUIDE.md §Biểu cảm):
    "nervous", "shocked", "crying", "tired", "smirk",
]
# Hiệu ứng theo shot (tham số: assets/catalog/effects.json). Để str tự do cho tương thích tiến;
# renderer bỏ qua tên không biết.
SHOT_EFFECTS: tuple[str, ...] = ("rain", "fog", "cctv", "flash", "fade_white", "fade_black", "blur_in", "glow",
                                 "shake_light")
Transition = Literal["cut", "fade", "blur", "white"]
View = Literal["front", "back", "side"]


class Overlay(BaseModel):
    kind: OverlayKind
    title: str
    subtitle: str | None = None
    character_id: str | None = None
    # Tham số có cấu trúc theo kind (tin nhắn chat, nhãn CAM/timestamp/số người/lưới CCTV, nhãn bản đồ...).
    # Hình dạng từng kind: assets/catalog/overlays.json > <kind>.data.
    data: dict[str, Any] = Field(default_factory=dict)


class CharacterInShot(BaseModel):
    id: str
    slot: str = "center"
    action: str = "idle"
    expression: Expression = "neutral"
    facing: Literal["left", "right"] = "right"
    prop: str | None = None
    pose: str | None = None           # tư thế tĩnh tuỳ chọn (vd "hands_on_glass", "peek_over_counter")
    view: View = "front"              # back = sau gáy / qua vai (over-shoulder), side = nghiêng


class Line(BaseModel):
    speaker: str = "narrator"
    text: str
    audio: str | None = None
    start: float | None = None
    duration: float | None = None
    visemes: list[tuple[float, str]] | None = None


class Shot(BaseModel):
    id: str
    location: str
    framing: Framing = "medium"
    camera: CameraMove = "static"
    focus: str | None = None
    characters: list[CharacterInShot] = Field(default_factory=list)
    lines: list[Line] = Field(default_factory=list)
    subtitle: str | None = None
    overlays: list[Overlay] = Field(default_factory=list)
    sfx: list[str] = Field(default_factory=list)
    music_mood: str | None = None
    min_duration: float = 2.5
    duration: float | None = None
    effects: list[str] = Field(default_factory=list)   # tên trong SHOT_EFFECTS
    transition: Transition = "cut"                     # chuyển cảnh VÀO shot này


class CharacterDef(BaseModel):
    id: str
    name: str
    role: str = ""
    description: str = ""
    gender: Literal["male", "female"] = "male"
    age: Literal["child", "young", "adult", "old"] = "adult"
    voice: str | None = None
    asset_id: str | None = None
    tags: list[str] = Field(default_factory=list)      # đặc điểm: glasses, cap, uniform, ghost, pale, long_hair...
    archetype: str | None = None                       # id trong assets/catalog/archetypes.json


class LocationDef(BaseModel):
    id: str
    name: str
    description: str = ""
    time_of_day: Literal["day", "night", "dusk", "indoor"] = "day"
    signs: list[str] = Field(default_factory=list)
    asset_id: str | None = None


class Storyboard(BaseModel):
    title: str
    style: str = "realLens"
    characters: list[CharacterDef] = Field(default_factory=list)
    locations: list[LocationDef] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)

    def character(self, cid: str) -> CharacterDef | None:
        return next((c for c in self.characters if c.id == cid), None)

    def location(self, lid: str) -> LocationDef | None:
        return next((l for l in self.locations if l.id == lid), None)

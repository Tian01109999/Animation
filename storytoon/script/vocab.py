"""Từ vựng cố định cho storyboard do ChatGPT sinh ra.

Renderer / asset library dựa vào các tên này, nên LLM chỉ được dùng đúng các giá trị dưới đây.
Mọi giá trị lạ sẽ bị post-process "kẹp" (clamp) về mặc định.
"""
from __future__ import annotations

from typing import Final

# Slot đứng/ngồi trong Location (assets/locations/<id>/location.json > slots).
#   far_left / left / center / right / far_right : 5 vị trí trên đường sàn, từ trái sang phải
#   counter : sau quầy / xe hàng / bàn (người bán hàng, lễ tân...), thường hơi lùi vào trong
SLOTS: Final[tuple[str, ...]] = ("left", "center", "right", "far_left", "far_right", "counter")
DEFAULT_SLOT: Final = "center"
# thứ tự ưu tiên khi cần tự xếp chỗ cho nhân vật
SLOT_FILL_ORDER: Final[tuple[str, ...]] = ("left", "right", "center", "far_left", "far_right")

# Động tác (assets/actions/<name>.json)
ACTIONS: Final[tuple[str, ...]] = ("idle", "talk", "walk", "sit", "point", "nod", "shake_head", "scared")
DEFAULT_ACTION: Final = "idle"

EXPRESSIONS: Final[tuple[str, ...]] = (
    "neutral", "happy", "sad", "angry", "scared", "evil", "surprised",
    "nervous", "shocked", "crying", "tired", "smirk",
)

# Hiệu ứng theo shot / chuyển cảnh / góc nhìn (khớp schema.SHOT_EFFECTS, Transition, View)
EFFECTS: Final[tuple[str, ...]] = ("rain", "fog", "cctv", "flash", "fade_white", "fade_black", "blur_in", "glow",
                                   "shake_light")
TRANSITIONS: Final[tuple[str, ...]] = ("cut", "fade", "blur", "white")
VIEWS: Final[tuple[str, ...]] = ("front", "back", "side")
OVERLAY_KINDS: Final[tuple[str, ...]] = (
    "nametag", "location_card", "chapter_card", "rule_card", "time_card", "cctv", "phone_chat", "phone_bank",
    "missing_poster", "map_card", "timeline", "info_card", "job_ad", "rule_list", "badge",
)

# Tâm trạng nhạc nền; None = giữ nhạc của shot trước
MUSIC_OFF: Final = "none"   # music_mood = "none" → tắt nhạc từ shot đó
MUSIC_MOODS: Final[tuple[str, ...]] = (
    "calm", "warm", "sad", "mystery", "tense", "horror", "investigation", "action", "shock", "hopeful", "tech",
)

FRAMINGS: Final[tuple[str, ...]] = ("wide", "medium", "close", "extreme_close")
CAMERA_MOVES: Final[tuple[str, ...]] = (
    "static", "zoom_in", "zoom_out", "pan_left", "pan_right", "push_in_slow", "shake",
)

NARRATOR: Final = "narrator"

# Giọng edge-tts
VOICE_NARRATOR: Final = "vi-VN-NamMinhNeural"
VOICE_MALE: Final = "vi-VN-NamMinhNeural"
VOICE_FEMALE: Final = "vi-VN-HoaiMyNeural"
KNOWN_VOICES: Final[tuple[str, ...]] = (VOICE_MALE, VOICE_FEMALE)

# Tốc độ đọc ước lượng (tiếng Việt, edge-tts tốc độ mặc định)
WORDS_PER_SECOND: Final = 3.2
# khoảng đệm cuối shot (khớp bước audio: duration = max(min_duration, audio + 0.4))
SHOT_PADDING_S: Final = 0.4

MIN_DURATION_RANGE: Final = (1.5, 8.0)

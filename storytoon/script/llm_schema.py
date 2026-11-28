"""JSON Schema gửi cho ChatGPT (response_json_schema), suy ra từ pydantic Storyboard.

- Bỏ các trường do bước audio điền (Line.audio/start/duration/visemes, Shot.duration).
- Inline mọi $ref, bỏ metadata "title"/"default", giữ trường dữ liệu cùng tên trong properties.
- Siết slot / action / music_mood / voice thành enum theo vocab.py.
- Thêm "required" cho các trường quan trọng để model không bỏ sót.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from typing import Any

from ..schema import Storyboard
from . import vocab

_LLM_EXCLUDED: dict[str, tuple[str, ...]] = {
    "Line": ("audio", "start", "duration", "visemes"),
    "Shot": ("duration",),
}
# Overlay.data là dict tự do — không hợp structured output chặt (additionalProperties=false). Gửi cho LLM dưới
# dạng danh sách cặp {key, value} (value = JSON literal hoặc chữ thường); breakdown.parse_storyboard đổi lại dict
# qua overlay_data_from_pairs().
OVERLAY_DATA_SCHEMA: dict[str, Any] = {
    "type": "array",
    "description": ("Tham số theo kind dạng cặp key/value; value là JSON literal (số, true/false, list, object) "
                    "hoặc chữ thường. Vd cctv: [{key:'cam',value:'3'},{key:'label',value:'AISLE 3'},"
                    "{key:'timestamp',value:'12-03-2024 03:14:07'},{key:'people',value:'2'}]. [] nếu không cần."),
    "items": {
        "type": "object",
        "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
        "required": ["key", "value"],
        "additionalProperties": False,
    },
}
_REQUIRED: dict[str, tuple[str, ...]] = {
    "Storyboard": ("title", "characters", "locations", "shots"),
    "Shot": ("id", "location", "framing", "camera", "characters", "lines", "subtitle", "overlays", "effects",
             "transition"),
    "CharacterInShot": ("id", "slot", "action", "expression", "facing", "view"),
    "Line": ("speaker", "text"),
    "Overlay": ("kind", "title", "data"),
    "CharacterDef": ("id", "name", "role", "description", "gender", "age", "asset_id"),
    "LocationDef": ("id", "name", "description", "time_of_day", "signs", "asset_id"),
}
_DESCRIPTIONS: dict[tuple[str, str], str] = {
    ("CharacterInShot", "slot"): "Vị trí đứng: " + ", ".join(vocab.SLOTS),
    ("CharacterInShot", "action"): "Động tác: " + ", ".join(vocab.ACTIONS),
    ("Shot", "id"): "s001, s002, ... theo thứ tự",
    ("Shot", "location"): "LocationDef.id (ascii snake_case)",
    ("Shot", "focus"): "id nhân vật camera hướng vào (bắt buộc với close/extreme_close nếu có nhân vật)",
    ("Shot", "subtitle"): "Phụ đề ngắn <= 12 từ",
    ("Line", "speaker"): "'narrator' hoặc CharacterDef.id",
    ("Shot", "music_mood"): " | ".join(vocab.MUSIC_MOODS) + " | none (tắt nhạc) | null (không đổi)",
    ("Shot", "sfx"): "tên trong thư viện hiệu ứng (xem mục Âm thanh), vd door_knock, rain, police_siren, impact",
    ("Shot", "transition"): "chuyển cảnh VÀO shot: cut (mặc định) | fade | blur | white",
    ("CharacterInShot", "view"): "front | back (quay lưng / qua vai, tiền cảnh) | side",
    ("CharacterInShot", "pose"): "tư thế tĩnh tuỳ chọn hoặc null",
    ("CharacterDef", "tags"): "trait tiếng Anh khớp kho: glasses, cap, curly, bald, uniform, ghost, long_hair...",
    ("CharacterDef", "asset_id"): "id nhân vật trong kho assets hoặc null",
    ("LocationDef", "asset_id"): "id bối cảnh trong kho assets hoặc null",
}


def _literal(value: str) -> Any:
    text = (value or "").strip()
    if text and (text[0] in "[{\"-0123456789" or text in ("true", "false", "null")):
        try:
            return json.loads(text)
        except ValueError:
            pass
    return value


def overlay_data_from_pairs(pairs: Any) -> dict[str, Any]:
    """[{key,value}, ...] (LLM form) → dict. A dict passes through unchanged."""
    if isinstance(pairs, dict):
        return pairs
    out: dict[str, Any] = {}
    for item in pairs or []:
        if isinstance(item, dict) and str(item.get("key", "")).strip():
            out[str(item["key"]).strip()] = _literal(item.get("value", "")) if isinstance(item.get("value"), str) \
                else item.get("value")
    return out


def normalize_llm_storyboard(data: Any) -> Any:
    """Convert LLM-only representations (Overlay.data pairs) back to the Storyboard model shape (in place)."""
    if isinstance(data, dict):
        for shot in data.get("shots") or []:
            if isinstance(shot, dict):
                for ov in shot.get("overlays") or []:
                    if isinstance(ov, dict) and "data" in ov:
                        ov["data"] = overlay_data_from_pairs(ov.get("data"))
    return data


def _enum_override(model: str, field: str) -> dict[str, Any] | None:
    if model == "CharacterInShot" and field == "slot":
        return {"type": "string", "enum": list(vocab.SLOTS)}
    if model == "CharacterInShot" and field == "action":
        return {"type": "string", "enum": list(vocab.ACTIONS)}
    if model == "Shot" and field == "music_mood":
        return {"anyOf": [{"type": "string", "enum": [*vocab.MUSIC_MOODS, vocab.MUSIC_OFF]}, {"type": "null"}]}
    if model == "Shot" and field == "sfx":
        from ..audio import library
        names = sorted(library.sfx_guide())
        if names:
            return {"type": "array", "items": {"type": "string", "enum": names},
                    "description": "hiệu ứng âm thanh trong thư viện (tối đa 3, [] nếu không)"}
    if model == "Shot" and field == "effects":
        return {"type": "array", "items": {"type": "string", "enum": list(vocab.EFFECTS)},
                "description": "hiệu ứng shot: " + ", ".join(vocab.EFFECTS) + " ([] nếu không)"}
    if model == "Overlay" and field == "data":
        return copy.deepcopy(OVERLAY_DATA_SCHEMA)
    if model == "CharacterDef" and field == "voice":
        return {"anyOf": [{"type": "string", "enum": list(vocab.KNOWN_VOICES)}, {"type": "null"}]}
    return None


def _strip(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            return _strip(defs[name], defs)
        return {
            k: ({field: _strip(schema, defs) for field, schema in v.items()}
                if k == "properties" else _strip(v, defs))
            for k, v in node.items() if k not in ("title", "default")
        }
    if isinstance(node, list):
        return [_strip(v, defs) for v in node]
    return node


@lru_cache(maxsize=1)
def _cached() -> dict[str, Any]:
    raw = Storyboard.model_json_schema()
    defs: dict[str, Any] = raw.pop("$defs", {})
    defs["Storyboard"] = raw
    for name, sch in defs.items():
        props: dict[str, Any] = sch.get("properties", {})
        for field in _LLM_EXCLUDED.get(name, ()):
            props.pop(field, None)
        for field in list(props):
            override = _enum_override(name, field)
            if override is not None:
                props[field] = override
            desc = _DESCRIPTIONS.get((name, field))
            if desc:
                props[field] = {**props[field], "description": desc}
        if name in _REQUIRED:
            sch["required"] = [f for f in _REQUIRED[name] if f in props]
    return _strip(defs["Storyboard"], defs)


def storyboard_response_schema() -> dict[str, Any]:
    """Bản sao JSON Schema (dict) dùng cho GenerateContentConfig.response_json_schema."""
    return copy.deepcopy(_cached())

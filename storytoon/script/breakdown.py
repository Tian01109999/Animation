"""Parse and validate ChatGPT storyboard output."""
from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from pydantic import ValidationError

from .. import config
from ..schema import Storyboard
from . import vocab
from .chunking import split_script
from .llm_schema import normalize_llm_storyboard, storyboard_response_schema
from .postprocess import finalize, merge_part
from .prompts import SYSTEM_PROMPT, build_chunk_prompt, build_fix_prompt

log = logging.getLogger(__name__)

DEFAULT_MODEL = ""
MAX_FIX_RETRIES = 2          # số lần gửi lại kèm lỗi validate

ProgressFn = Callable[[int, int, str], None]


class BreakdownError(RuntimeError):
    """Lỗi tách kịch bản (thông điệp tiếng Việt cho người dùng)."""


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def parse_storyboard(text: str) -> Storyboard:
    """Parse + validate JSON trả về. Raise ValueError/ValidationError nếu không hợp lệ."""
    if not text or not text.strip():
        raise ValueError("Phản hồi rỗng")
    cleaned = _FENCE_RE.sub("", text.strip())
    data = json.loads(cleaned)
    if isinstance(data, dict) and "storyboard" in data and "shots" not in data:
        data = data["storyboard"]
    sb = Storyboard.model_validate(normalize_llm_storyboard(data))
    if not sb.shots:
        raise ValueError("Storyboard không có shot nào (shots rỗng)")
    for i, shot in enumerate(sb.shots):
        if not shot.location:
            raise ValueError(f"shots[{i}].location bị trống")
    return sb


def _response_text(resp: Any) -> str:
    text = getattr(resp, "text", None)
    if text is None and isinstance(resp, str):
        text = resp
    return text or ""


# ---------------------------------------------------------------- gọi 1 đoạn

def breakdown_chunk(
    client: Any,
    prompt: str,
    *,
    model: str,
    temperature: float = 0.6,
    sleep: Callable[[float], None] = time.sleep,
    generate_text: Callable[[Any], str] | None = None,
    provider_name: str = "ChatGPT",
) -> Storyboard:
    """Gọi ChatGPT cho 1 đoạn; nếu JSON không hợp lệ thì gửi lại kèm lỗi (tối đa MAX_FIX_RETRIES)."""
    if generate_text is None:
        from ..chatgpt import generate
        generate_text = generate
    contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": prompt}]}]
    last_err = ""
    for attempt in range(MAX_FIX_RETRIES + 1):
        text = generate_text(contents)
        try:
            return parse_storyboard(text)
        except (ValueError, ValidationError) as e:  # json.JSONDecodeError là ValueError
            last_err = str(e)
            log.warning("Storyboard không hợp lệ (lần %d): %s", attempt + 1, last_err[:500])
            contents = [
                {"role": "user", "parts": [{"text": prompt}]},
                {"role": "model", "parts": [{"text": text[:30000]}]},
                {"role": "user", "parts": [{"text": build_fix_prompt(last_err)}]},
            ]
    raise BreakdownError(
        f"{provider_name} trả về storyboard không hợp lệ sau {MAX_FIX_RETRIES + 1} lần thử. Lỗi cuối: {last_err[:800]}"
    )


# ---------------------------------------------------------------- API chính

def _voices() -> dict[str, str]:
    return {
        "male": config.get("tts.default_male", vocab.VOICE_MALE) or vocab.VOICE_MALE,
        "female": config.get("tts.default_female", vocab.VOICE_FEMALE) or vocab.VOICE_FEMALE,
    }


def breakdown(
    script_text: str,
    *,
    existing_characters: Sequence[str] = (),
    existing_locations: Sequence[str] = (),
    model: str | None = None,
    client: Any = None,
    on_progress: ProgressFn | None = None,
    sleep: Callable[[float], None] = time.sleep,
    chunk_chars: int | None = None,
    generate_text: Callable[[Any], str] | None = None,
    provider_name: str = "ChatGPT",
) -> Storyboard:
    """Convert a script through ChatGPT, with an injectable text generator for tests."""
    if not script_text or not script_text.strip():
        raise BreakdownError("Kịch bản trống.")
    model = model or ""
    kw = {"target_chars": chunk_chars, "max_chars": int(chunk_chars * 1.2)} if chunk_chars else {}
    chunks = split_script(script_text, **kw)
    n = len(chunks)
    acc = Storyboard(title="")
    voices = _voices()

    for i, chunk in enumerate(chunks):
        if on_progress:
            on_progress(i + 1, n, f"Đang tách đoạn {i + 1}/{n} bằng {provider_name} ({len(chunk)} ký tự)…")
        # finalize tạm để biết nametag/chương/luật đã có (không ảnh hưởng acc)
        snapshot = finalize(acc.model_copy(deep=True), voices=voices) if acc.shots else acc
        introduced = [o.character_id for s in snapshot.shots for o in s.overlays
                      if o.kind == "nametag" and o.character_id]
        chapters = sum(1 for s in snapshot.shots for o in s.overlays if o.kind == "chapter_card")
        rules = sum(1 for s in snapshot.shots for o in s.overlays if o.kind == "rule_card")
        prompt = build_chunk_prompt(
            chunk,
            chunk_index=i,
            chunk_count=n,
            known_characters=snapshot.characters,
            known_locations=snapshot.locations,
            introduced_characters=introduced,
            asset_characters=existing_characters,
            asset_locations=existing_locations,
            last_location=snapshot.shots[-1].location if snapshot.shots else None,
            chapters_so_far=chapters,
            rules_so_far=rules,
            title=acc.title or None,
        )
        part = breakdown_chunk(client, prompt, model=model, sleep=sleep, generate_text=generate_text,
                               provider_name=provider_name)
        merge_part(acc, part)

    if on_progress:
        on_progress(n, n, "Đang hậu xử lý storyboard…")
    sb = finalize(acc, voices=voices)
    # kiểm tra lần cuối theo schema
    return Storyboard.model_validate(sb.model_dump())

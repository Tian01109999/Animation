"""Động tác: nội suy keyframe (ease-in-out), cộng thở + chớp mắt (seed theo shot id), khẩu hình, biểu cảm."""
from __future__ import annotations

import json
import logging
import math
import random
import zlib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..paths import ACTIONS
from ..schema import CharacterInShot
from .rig import BonePose, Pose, Rig
from .timing import TimedLine

log = logging.getLogger("storytoon.render")

CHANNELS = ("r", "x", "y", "sx", "sy")
TALK_SHAPES = ["B", "C", "D", "C", "E", "B", "F", "C", "A", "D", "G", "C", "H", "B"]
# Khẩu hình lúc im lặng theo biểu cảm (khi character.json không khai báo "mouth" trong expressions).
# X = cười mỉm nhẹ -> sai với sợ/buồn/giận/ngạc nhiên.
REST_MOUTH = {"scared": "G", "surprised": "F", "angry": "A", "sad": "A"}


@dataclass
class Action:
    name: str
    loop: bool = True
    duration: float = 2.0
    tracks: dict[tuple[str, str], list[tuple[float, float]]] = field(default_factory=dict)
    slots: dict[str, str] = field(default_factory=dict)
    move_x_per_s: float = 0.0
    sit: bool = False
    default_expression: str | None = None


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def eval_keys(keys: list[tuple[float, float]], t: float) -> float:
    if not keys:
        return 0.0
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * ease((t - t0) / (t1 - t0 if t1 > t0 else 1.0))
    return keys[-1][1]


def _parse(name: str, data: dict) -> Action:
    tracks: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for key, keys in (data.get("tracks") or {}).items():
        bone, _, ch = key.partition(".")
        ch = ch or "r"
        if ch not in CHANNELS:
            continue
        tracks[(bone, ch)] = sorted((float(a), float(b)) for a, b in keys)
    return Action(name=data.get("name", name), loop=bool(data.get("loop", True)),
                  duration=float(data.get("duration", 2.0)) or 2.0, tracks=tracks, slots=data.get("slots") or {},
                  move_x_per_s=float((data.get("move") or {}).get("x_per_s", 0.0)), sit=bool(data.get("sit", False)),
                  default_expression=data.get("default_expression"))


@lru_cache(maxsize=64)
def load_action(name: str, root: str = str(ACTIONS)) -> Action:
    f = Path(root) / f"{name}.json"
    if not f.exists():
        if name != "idle":
            log.warning("Không có động tác '%s' — dùng 'idle'", name)
            return load_action("idle", root)
        return Action("idle")
    try:
        return _parse(name, json.loads(f.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as e:
        log.warning("Động tác '%s' lỗi: %s — dùng mặc định", name, e)
        return Action(name)


def sample_action(a: Action, t: float) -> dict[str, dict[str, float]]:
    tt = (t % a.duration) if a.loop else min(t, a.duration)
    out: dict[str, dict[str, float]] = {}
    for (bone, ch), keys in a.tracks.items():
        out.setdefault(bone, {})[ch] = eval_keys(keys, tt)
    return out


def blend(a: dict[str, dict[str, float]], b: dict[str, dict[str, float]], w: float) -> dict[str, dict[str, float]]:
    if w <= 0:
        return a
    if w >= 1:
        return b
    out: dict[str, dict[str, float]] = {}
    for bone in set(a) | set(b):
        da, db = a.get(bone, {}), b.get(bone, {})
        out[bone] = {}
        for ch in set(da) | set(db):
            dflt = 1.0 if ch in ("sx", "sy") else 0.0
            out[bone][ch] = da.get(ch, dflt) * (1 - w) + db.get(ch, dflt) * w
    return out


def seed_of(*parts: str) -> int:
    return zlib.crc32("|".join(parts).encode("utf-8"))


def blink_times(seed: int, duration: float) -> list[float]:
    rng = random.Random(seed)
    t = rng.uniform(0.4, 2.0)
    out = []
    while t < duration + 1:
        out.append(t)
        t += rng.uniform(2.2, 5.0) if rng.random() > 0.15 else 0.35  # thỉnh thoảng chớp đúp
    return out


@dataclass
class FrameState:
    pose: Pose
    slots: dict[str, str]
    dx: float = 0.0  # dịch root theo x (đơn vị canvas nhân vật, trước khi lật hướng)


class Animator:
    """Trạng thái động của 1 nhân vật trong 1 shot."""

    def __init__(self, rig: Rig, cis: CharacterInShot, shot_id: str, lines: list[TimedLine], duration: float) -> None:
        self.rig = rig
        self.cis = cis
        self.action = load_action(cis.action or "idle")
        self.talk = load_action("talk")
        self.lines = [tl for tl in lines if tl.line.speaker == cis.id]
        self.seed = seed_of(shot_id, cis.id)
        self.blinks = blink_times(self.seed, duration)
        self.phase = (self.seed % 1000) / 1000 * math.tau
        expr = cis.expression
        if expr == "neutral" and self.action.default_expression:
            expr = self.action.default_expression
        self.expression = expr
        ex = rig.expressions.get(expr) or rig.expressions.get("neutral") or {}
        self.base_eyes = ex.get("eyes", "open")
        self.base_brows = ex.get("brows", "neutral")
        rest = ex.get("mouth") or REST_MOUTH.get(expr, "X")
        self.rest_mouth = rest if rest in rig.slot_states.get("mouth", []) else "X"
        # FX trên mặt (mồ hôi, nước mắt, gân...) bật theo biểu cảm; slot không có -> bỏ qua
        self.fx_slots = {f"fx_{f}": "on" for f in (ex.get("fx") or []) if f"fx_{f}" in rig.slot_states}
        self.view = getattr(cis, "view", "front") or "front"
        self.sit_drop = 0.0
        if self.action.sit:
            # hông hạ xuống để bàn chân vẫn chạm sàn: đùi xoay góc a (và/hoặc co sy) -> đầu gối nâng lên
            sy = self.action.tracks.get(("leg_l_up", "sy"), [(0, 1.0)])[0][1]
            ang = self.action.tracks.get(("leg_l_up", "r"), [(0, 0.0)])[0][1]
            hb, kb = rig.bones.get("leg_l_up"), rig.bones.get("leg_l_low")
            if hb and kb:
                thigh = kb.pivot[1] - hb.pivot[1]
                self.sit_drop = thigh - thigh * sy * math.cos(math.radians(ang))
        # chỉ tự chuyển sang 'talk' khi động tác gốc là idle
        self.auto_talk = self.action.name == "idle" and bool(self.lines)

    # ------------------------------------------------------------ helpers
    def speaking_weight(self, t: float) -> float:
        w = 0.0
        for tl in self.lines:
            if tl.start - 0.25 <= t <= tl.end + 0.25:
                a = (t - (tl.start - 0.25)) / 0.25
                b = ((tl.end + 0.25) - t) / 0.25
                w = max(w, min(1.0, a, b))
        return ease(w)

    def mouth(self, t: float) -> str:
        for tl in self.lines:
            if tl.start <= t < tl.end:
                lt = t - tl.start
                vis = tl.line.visemes
                if vis:
                    shape = "X"
                    for vt, vs in vis:
                        if vt <= lt:
                            shape = vs
                        else:
                            break
                    return shape if shape in "ABCDEFGHX" else "X"
                # không có viseme: khẩu hình giả theo nhịp ~ 9 lần/giây
                if tl.end - t < 0.08:
                    return "X"
                k = int(lt * 9.0 + (self.seed % 7))
                rng = random.Random(self.seed + k)
                return TALK_SHAPES[rng.randrange(len(TALK_SHAPES))]
        return self.rest_mouth

    def eyes(self, t: float) -> str:
        if self.base_eyes == "closed":
            return "closed"
        for bt in self.blinks:
            d = t - bt
            if 0 <= d < 0.05 or 0.12 <= d < 0.17:
                return "half"
            if 0.05 <= d < 0.12:
                return "closed"
        return self.base_eyes

    # ------------------------------------------------------------ main
    def frame(self, t: float) -> FrameState:
        ch = sample_action(self.action, t)
        if self.auto_talk:
            w = self.speaking_weight(t)
            if w > 0:
                ch = blend(ch, sample_action(self.talk, t), w)
        pose: Pose = {}
        for bone, d in ch.items():
            pose[bone] = BonePose(d.get("r", 0.0), d.get("x", 0.0), d.get("y", 0.0), d.get("sx", 1.0), d.get("sy", 1.0))
        # thở: ngực phồng nhẹ (scale quanh eo), vai nâng theo
        br = math.sin(t * math.tau / 3.6 + self.phase)
        tp = pose.setdefault("torso", BonePose())
        tp.sy *= 1.0 + 0.010 * br
        tp.sx *= 1.0 + 0.004 * br
        hp = pose.setdefault("head", BonePose())
        hp.r += 0.6 * math.sin(t * math.tau / 5.3 + self.phase * 1.7)
        if self.sit_drop:
            pose.setdefault("hip", BonePose()).y += self.sit_drop
        slots = {"eyes": self.eyes(t), "brows": self.base_brows, "mouth": self.mouth(t), "view": self.view}
        slots.update(self.fx_slots)
        slots.update(self.action.slots)
        dx = self.action.move_x_per_s * t
        return FrameState(pose, slots, dx)

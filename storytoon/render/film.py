"""render_film: render từng shot -> projects/<p>/shots/<id>.mp4 (bỏ qua nếu không đổi), ghép, mux âm thanh."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from ..config import get
from ..paths import ACTIONS, CHARACTERS, LOCATIONS
from ..schema import Shot, Storyboard
from .encode import concat_videos, pick_encoder
from .timing import shot_duration

log = logging.getLogger("storytoon.render")

RENDER_VERSION = "4-overlays-effects"


def frame_counts(sb: Storyboard, fps: int) -> list[int]:
    """Số frame mỗi shot theo mốc tích luỹ -> tổng thời lượng video khớp tổng thời lượng âm thanh (không trôi)."""
    out, acc = [], 0.0
    for sh in sb.shots:
        a = round(acc * fps)
        acc += shot_duration(sh)
        out.append(max(1, round(acc * fps) - a))
    return out


_BAD_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def check_shot_ids(sb: Storyboard) -> None:
    """Shot id dùng làm tên file (shots/<id>.mp4, audio/<id>_..wav) -> phải duy nhất và hợp lệ trên Windows.
    Trùng id thì 2 shot ghi đè cùng 1 file và phim ghép sai mà không báo lỗi."""
    seen: set[str] = set()
    dup: list[str] = []
    bad: list[str] = []
    for sh in sb.shots:
        key = sh.id.casefold()   # Windows không phân biệt hoa/thường
        if key in seen:
            dup.append(sh.id)
        seen.add(key)
        if (not sh.id.strip() or _BAD_NAME.search(sh.id) or sh.id != sh.id.strip() or sh.id.endswith(".")
                or sh.id.split(".")[0].lower() in _RESERVED):
            bad.append(sh.id)
    msgs = []
    if dup:
        msgs.append("trùng id shot: " + ", ".join(sorted(set(dup))))
    if bad:
        msgs.append("id shot không dùng làm tên file được: " + ", ".join(repr(b) for b in bad))
    if msgs:
        raise ValueError("Storyboard lỗi — " + "; ".join(msgs) + ". Sửa 'id' trong storyboard.json (mỗi shot một id riêng, "
                         "chỉ chữ/số/_/-).")


def _mtime(p: Path) -> float:
    try:
        return round(p.stat().st_mtime, 3)
    except OSError:
        return 0.0


def _tree_mtime(d: Path) -> float:
    """mtime lớn nhất của mọi file trong thư mục (đệ quy); 0 nếu không có."""
    best = 0.0
    try:
        for root, _dirs, files in os.walk(d):
            for f in files:
                best = max(best, _mtime(Path(root) / f))
    except OSError:
        pass
    return best


def shot_hash(shot: Shot, sb: Storyboard, project_dir: Path, width: int, height: int, fps: int, n: int,
              encoder: str) -> str:
    """Hash mọi thứ ảnh hưởng tới hình của shot (dữ liệu shot, nhân vật/địa điểm liên quan, tài sản, tham số)."""
    cids = {c.id for c in shot.characters} | {o.character_id for o in shot.overlays if o.character_id}
    loc = shot.location
    # cả thư mục (ảnh bộ phận, nền, biển hiệu…): thay 1 file PNG mà không sửa .json cũng phải render lại
    assets = {cid: _tree_mtime(CHARACTERS / ((sb.character(cid).asset_id or cid) if sb.character(cid) else cid)) for cid in sorted(cids)}
    if loc.startswith("insert:"):
        assets[loc] = max([_mtime(p) for p in (project_dir / "inserts").glob(loc[7:] + ".*")] +
                          [_mtime(p) for p in (LOCATIONS.parent / "inserts").glob(loc[7:] + ".*")] + [0.0])
    else:
        definition = sb.location(loc)
        asset_id = (definition.asset_id or loc) if definition else loc
        assets[loc] = _tree_mtime(LOCATIONS / asset_id)
    # file động tác (assets/actions/*.json) cũng ảnh hưởng hình -> sửa động tác thì render lại shot dùng nó
    for act in sorted({c.action or "idle" for c in shot.characters} | ({"idle", "talk"} if shot.characters else set())):
        assets[f"action:{act}"] = _mtime(ACTIONS / f"{act}.json")
    # chuyển cảnh của shot kế tiếp được vẽ ở đuôi shot này (effects.py) -> đổi nó thì phải render lại shot này
    idx = next((i for i, s in enumerate(sb.shots) if s.id == shot.id), None)
    next_tr = sb.shots[idx + 1].transition if idx is not None and idx + 1 < len(sb.shots) else "cut"
    # overlay CCTV lưới 4 ô dùng nền của location khác (cells[].location)
    for ov in shot.overlays:
        for cell in (ov.data or {}).get("cells") or []:
            lid = cell.get("location") if isinstance(cell, dict) else None
            if lid:
                d = sb.location(lid)
                assets[f"cell:{lid}"] = _tree_mtime(LOCATIONS / ((d.asset_id or lid) if d else lid))
    payload = {
        "v": RENDER_VERSION, "shot": shot.model_dump(mode="json"), "title": sb.title, "next_transition": next_tr,
        "chars": [c.model_dump(mode="json") for c in sb.characters if c.id in cids],
        "loc": (sb.location(loc).model_dump(mode="json") if sb.location(loc) else None),
        "assets": assets, "size": [width, height, fps, n], "enc": encoder,
        "wm": get("render.watermark", "StoryToon"),
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _render_one(sb_json: str, idx: int, project_dir: str, out: str, width: int, height: int, fps: int, n: int) -> str:
    # chạy trong tiến trình con (Windows spawn) -> import lại ở đây
    from ..schema import Storyboard as SB
    from .compositor import render_shot
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sb = SB.model_validate_json(sb_json)
    render_shot(sb.shots[idx], sb, Path(project_dir), Path(out), width=width, height=height, fps=fps, n_frames=n)
    return out


def render_film(sb: Storyboard, project_dir: Path, out_mp4: Path, *, soundtrack: Path | None = None,
                width: int | None = None, height: int | None = None, fps: int | None = None,
                workers: int | None = None, force: bool = False,
                progress: Callable[[int, int, str], None] | None = None) -> Path:
    """Render cả phim. `soundtrack` = wav đã trộn sẵn (bước audio) hoặc None = phim câm.
    `progress(done, total, shot_id)` được gọi sau mỗi shot."""
    from ..asset_library import validate
    validate(sb)
    project_dir = Path(project_dir)
    check_shot_ids(sb)
    if not sb.shots:
        raise ValueError("Storyboard không có shot nào để dựng.")
    width = int(width or get("render.width", 1920))
    height = int(height or get("render.height", 1080))
    fps = int(fps or get("render.fps", 30))
    # mỗi tiến trình đã ~50 fps (GPU + NVENC); 2 tiến trình đủ che thời gian chuẩn bị shot
    workers = int(workers or get("render.workers", 0) or min(2, max(1, (os.cpu_count() or 2) // 4)))
    shots_dir = project_dir / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    encoder = pick_encoder()
    counts = frame_counts(sb, fps)
    sb_json = sb.model_dump_json()
    todo: list[tuple[int, Path, str]] = []
    outs: list[Path] = []
    for i, (sh, n) in enumerate(zip(sb.shots, counts)):
        out = shots_dir / f"{sh.id}.mp4"
        hf = shots_dir / f"{sh.id}.hash"
        h = shot_hash(sh, sb, project_dir, width, height, fps, n, encoder)
        outs.append(out)
        if not force and out.exists() and hf.exists() and hf.read_text(encoding="utf-8").strip() == h:
            continue
        todo.append((i, out, h))
    total = len(sb.shots)
    done = total - len(todo)
    log.info("Render phim: %d shot, cần render %d (bỏ qua %d không đổi), %d tiến trình", total, len(todo), done, workers)
    if progress:
        progress(done, total, "")

    def finish(i: int, out: Path, h: str) -> None:
        nonlocal done
        (shots_dir / f"{sb.shots[i].id}.hash").write_text(h, encoding="utf-8")
        done += 1
        if progress:
            progress(done, total, sb.shots[i].id)

    failed: list[tuple[str, BaseException]] = []
    if workers <= 1 or len(todo) <= 1:
        from .compositor import render_shot
        for i, out, h in todo:
            try:
                render_shot(sb.shots[i], sb, project_dir, out, width=width, height=height, fps=fps, n_frames=counts[i])
            except Exception as e:  # noqa: BLE001 — làm tiếp các shot khác, báo lỗi ở cuối
                log.error("Shot %s lỗi: %s", sb.shots[i].id, e)
                failed.append((sb.shots[i].id, e))
                continue
            finish(i, out, h)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_render_one, sb_json, i, str(project_dir), str(out), width, height, fps, counts[i]):
                    (i, out, h) for i, out, h in todo}
            for fu in as_completed(futs):
                i, out, h = futs[fu]
                try:
                    fu.result()
                except Exception as e:  # noqa: BLE001 — ghi .hash cho shot đã xong để lần sau không render lại
                    log.error("Shot %s lỗi: %s", sb.shots[i].id, e)
                    failed.append((sb.shots[i].id, e))
                    continue
                finish(i, out, h)
    if failed:
        ids = ", ".join(sid for sid, _ in failed[:10]) + (" …" if len(failed) > 10 else "")
        raise RuntimeError(f"{len(failed)} shot dựng lỗi ({ids}); các shot khác đã lưu, chạy lại sẽ chỉ dựng shot lỗi. "
                           f"Lỗi đầu tiên: {failed[0][1]}") from failed[0][1]
    return concat_videos(outs, Path(out_mp4), soundtrack)

"""Pipeline StoryToon: breakdown -> assets -> audio -> render, chạy tiếp được (projects/<p>/state.json).

Tệp trong projects/<p>/:
  script.txt              kịch bản gốc (người dùng viết)
  storyboard.json         storyboard (GPT tự động tạo) — KHÔNG chứa dữ liệu âm thanh
  storyboard.timed.json   bản đã điền thời gian/âm thanh/viseme (bước audio sinh ra, renderer dùng)
  soundtrack.wav          giọng + nhạc + sfx đã trộn
  shots/  audio/  lipsync/  subtitles.srt  final.mp4  log.txt  state.json

Dùng:
  from storytoon.pipeline import run
  run("demo", steps=["audio", "render"], provider="mock", progress=lambda step, frac, msg: ...)
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from . import config, paths
from .schema import CharacterDef, LocationDef, Storyboard

log = logging.getLogger("storytoon.pipeline")

STEPS: tuple[str, ...] = ("breakdown", "assets", "audio", "render")
STEP_LABELS = {"breakdown": "Tách kịch bản", "assets": "Tài sản", "audio": "Âm thanh", "render": "Dựng phim"}

ProgressCB = Callable[[str, float, str], None]   # (bước, 0..1, thông điệp tiếng Việt)


class PipelineError(RuntimeError):
    """Lỗi pipeline với thông điệp tiếng Việt cho người dùng."""


# ======================================================================= project
@dataclass(frozen=True)
class Project:
    dir: Path

    @property
    def name(self) -> str:
        return self.dir.name

    script = property(lambda s: s.dir / "script.txt")
    storyboard = property(lambda s: s.dir / "storyboard.json")
    timed = property(lambda s: s.dir / "storyboard.timed.json")
    soundtrack = property(lambda s: s.dir / "soundtrack.wav")
    final = property(lambda s: s.dir / "final.mp4")
    state_file = property(lambda s: s.dir / "state.json")
    log_file = property(lambda s: s.dir / "log.txt")
    shots_dir = property(lambda s: s.dir / "shots")


def project(p: str | Path) -> Project:
    """Tên project (thư mục trong projects/) hoặc đường dẫn thư mục."""
    pp = Path(p)
    if not pp.is_absolute() and not pp.exists():
        pp = paths.PROJECTS / str(p)
    return Project(pp.resolve())


def list_projects() -> list[str]:
    if not paths.PROJECTS.exists():
        return []
    return sorted(d.name for d in paths.PROJECTS.iterdir() if d.is_dir() and not d.name.startswith("."))


def delete_project(name: str) -> None:
    """Delete only one real project directory directly inside the app's project root."""
    from . import activity
    if not name or name in ('.','..') or '/' in name or '\\' in name or Path(name).is_absolute():
        raise PipelineError('Tên project không hợp lệ.')
    with activity.idle_operation():
        root = paths.PROJECTS.resolve()
        directory = root / name
        if directory.is_symlink() or directory.is_junction():
            raise PipelineError('Không xóa project là liên kết tới thư mục khác.')
        if not directory.is_dir():
            raise PipelineError('Project không còn tồn tại.')
        resolved = directory.resolve(strict=True)
        if resolved.parent != root or resolved.name != name:
            raise PipelineError('Chỉ được xóa project trong thư mục dự án của app.')
        shutil.rmtree(resolved)


def new_project(name: str, script_text: str = "") -> Project:
    """Tạo projects/<slug>/script.txt. Trùng tên -> thêm hậu tố _2, _3..."""
    from .script.ids import slugify

    base = slugify(name, fallback="phim")
    slug, i = base, 2
    while (paths.PROJECTS / slug).exists():
        slug, i = f"{base}_{i}", i + 1
    pr = Project(paths.PROJECTS / slug)
    pr.dir.mkdir(parents=True)
    pr.script.write_text(script_text or f"# {name}\n\n(Viết kịch bản tiếng Việt ở đây)\n", encoding="utf-8")
    return pr


def load_storyboard(pr: Project) -> Storyboard:
    if not pr.storyboard.exists():
        raise PipelineError(f"Chưa có storyboard.json trong {pr.dir} — chạy bước 'Tách kịch bản' trước.")
    try:
        return Storyboard.model_validate_json(pr.storyboard.read_text(encoding="utf-8"))
    except ValueError as e:
        raise PipelineError(f"storyboard.json không hợp lệ: {e}") from e


def save_storyboard(pr: Project, sb: Storyboard, *, timed: bool = False) -> Path:
    out = pr.timed if timed else pr.storyboard
    data = sb.model_dump_json(indent=2, exclude_none=not timed)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(out)
    return out


def load_render_storyboard(pr: Project) -> tuple[Storyboard, bool]:
    """Storyboard cho renderer: bản timed nếu còn khớp storyboard.json, không thì bản gốc. Trả (sb, có_timing)."""
    st = _State(pr)
    if pr.timed.exists() and st.get("audio").get("input") == _audio_input_hash(pr):
        return Storyboard.model_validate_json(pr.timed.read_text(encoding="utf-8")), True
    return load_storyboard(pr), False


# ======================================================================= state + log
class _State:
    def __init__(self, pr: Project) -> None:
        self.pr = pr
        try:
            self.data: dict[str, Any] = json.loads(pr.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}
        self.data.setdefault("steps", {})

    def get(self, step: str) -> dict[str, Any]:
        return self.data["steps"].get(step, {})

    def set(self, step: str, **kw: Any) -> None:
        self.data["steps"][step] = {"done": _now(), **kw}
        self.save()

    def clear(self, step: str) -> None:
        self.data["steps"].pop(step, None)
        self.save()

    def save(self) -> None:
        self.pr.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.pr.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.pr.state_file)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _sha(*parts: str | bytes) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(p.encode("utf-8") if isinstance(p, str) else p)
        h.update(b"\0")
    return h.hexdigest()


def _audio_input_hash(pr: Project) -> str:
    sb = pr.storyboard.read_bytes() if pr.storyboard.exists() else b""
    script = pr.script.read_bytes() if pr.script.exists() else b""   # khoảng nghỉ theo đoạn văn
    tts = json.dumps(config.get("tts", {}), sort_keys=True, ensure_ascii=False)
    mix = json.dumps(config.get("audio", {}), sort_keys=True, ensure_ascii=False)
    return _sha(sb, script, tts, mix, "audio-v2")


class _FileLogHandler(logging.Handler):
    """Chép cảnh báo/lỗi của các module storytoon.* vào log.txt của project trong lúc chạy."""

    def __init__(self, runner: "Runner") -> None:
        super().__init__(logging.INFO)
        self.runner = runner
        self.thread = threading.get_ident()

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("storytoon.pipeline"):
            return
        if record.levelno < logging.WARNING and threading.get_ident() != self.thread:
            return
        try:
            self.runner._write(f"[{record.levelname.lower()}] {record.name}: {record.getMessage()}")
        except Exception:  # noqa: BLE001
            pass


class Runner:
    """Ghi tiến độ vào log.txt + gọi callback."""

    def __init__(self, pr: Project, progress: ProgressCB | None = None) -> None:
        self.pr = pr
        self.cb = progress
        self.step = ""
        self._lock = threading.Lock()
        pr.dir.mkdir(parents=True, exist_ok=True)

    def _write(self, line: str) -> None:
        with self._lock, self.pr.log_file.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {line}\n")

    def __call__(self, msg: str, frac: float | None = None) -> None:
        self._write(f"[{self.step or '-'}] {msg}")
        log.info("[%s] %s", self.step, msg)
        if self.cb:
            try:
                self.cb(self.step, -1.0 if frac is None else max(0.0, min(1.0, frac)), msg)
            except Exception:  # noqa: BLE001 - callback UI lỗi không làm hỏng pipeline
                log.exception("progress callback lỗi")


# ======================================================================= bước 1: breakdown
def step_breakdown(pr: Project, say: Runner, *, force: bool = False, model: str | None = None) -> Storyboard:
    if not pr.script.exists() or not pr.script.read_text(encoding="utf-8").strip():
        raise PipelineError(f"Chưa có kịch bản: {pr.script}")
    from .script import BreakdownError, breakdown, storyboard_stats

    text = pr.script.read_text(encoding="utf-8")
    source_hash = _sha(text, 'gpt-script-v2')
    state = _State(pr)
    if pr.storyboard.exists() and not force and state.get('breakdown').get('input') == source_hash:
        say('Kịch bản không đổi — dùng storyboard.json đã lưu.',1.0)
        return load_storyboard(pr)
    from . import chatgpt
    generator, name = chatgpt.generate, 'GPT / ChatGPT'
    # Lưu từng đoạn đã tách xong; lần chạy sau (cùng kịch bản) chỉ tách tiếp các đoạn còn thiếu.
    ckpt_file = _breakdown_ckpt(pr)
    done_parts: list[dict] = list(_read_ckpt(pr, source_hash).get('parts', []))

    def save_part(i: int, n: int, dump: dict) -> None:
        done_parts[i:] = [dump]
        tmp = ckpt_file.with_suffix('.tmp')
        tmp.write_text(json.dumps({'input': source_hash, 'chunks': n, 'parts': done_parts},
                                  ensure_ascii=False), encoding='utf-8')
        tmp.replace(ckpt_file)
        say(f"Đã xong và lưu đoạn {i + 1}/{n}.", (i + 1) / max(1, n))

    say(f"Gửi kịch bản ({len(text)} ký tự) cho {name}…", 0.0)
    try:
        sb = breakdown(text, existing_characters=_existing_ids(paths.CHARACTERS, "character.json"),
                       existing_locations=_existing_ids(paths.LOCATIONS, "location.json"), model=model,
                       on_progress=lambda i, n, m: say(m, (i - 1) / max(1, n)),
                       generate_text=generator, provider_name=name,
                       done_parts=list(done_parts), on_part=save_part)
    except (BreakdownError, RuntimeError) as e:
        kept = (f" Đã lưu {len(done_parts)} đoạn xong — chạy lại sẽ tiếp tục từ đoạn {len(done_parts) + 1}."
                if done_parts else "")
        raise PipelineError(f"Tách kịch bản thất bại: {e}{kept}") from e
    from .asset_library import assign
    sb.style = 'cutout'
    assign(sb)
    if pr.script.read_text(encoding='utf-8') != text:
        raise PipelineError('Kịch bản vừa thay đổi trong lúc phân tích. Hãy cập nhật phân cảnh lại; bản cũ được giữ.')
    if pr.storyboard.exists():
        shutil.copy2(pr.storyboard, pr.storyboard.with_name("storyboard.bak.json"))
    save_storyboard(pr, sb)
    _State(pr).set('breakdown',input=source_hash)
    ckpt_file.unlink(missing_ok=True)
    say("Đã ghi storyboard.json — " + storyboard_stats(sb).summary(), 1.0)
    return sb


def _breakdown_ckpt(pr: Project) -> Path:
    return pr.dir / 'breakdown_parts.json'


def _read_ckpt(pr: Project, source_hash: str) -> dict:
    """Checkpoint các đoạn đã tách của đúng kịch bản này ({} nếu không có/không khớp)."""
    try:
        saved = json.loads(_breakdown_ckpt(pr).read_text(encoding='utf-8'))
        if saved.get('input') == source_hash and isinstance(saved.get('parts'), list):
            return saved
    except (OSError, ValueError, AttributeError):
        pass
    return {}


def breakdown_partial(pr: Project) -> tuple[Storyboard | None, int, int] | None:
    """Kết quả tách dở của kịch bản hiện tại: (storyboard tạm, số đoạn xong, tổng số đoạn).

    None nếu không có phần tách dở khớp với script.txt hiện tại.
    """
    if not pr.script.exists():
        return None
    saved = _read_ckpt(pr, _sha(pr.script.read_text(encoding='utf-8'), 'gpt-script-v2'))
    parts = saved.get('parts') or []
    if not parts:
        return None
    from .script.breakdown import preview_parts
    total = int(saved.get('chunks') or len(parts))
    return preview_parts(parts), len(parts), max(total, len(parts))


def _existing_ids(root: Path, meta: str) -> list[str]:
    return sorted(d.name for d in root.iterdir() if (d / meta).exists()) if root.exists() else []


# ======================================================================= bước 2: gán kho assets
@dataclass
class AssetReport:
    characters_assigned: list[str] = field(default_factory=list)
    locations_assigned: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def step_assets(sb: Storyboard, say: Runner, *, project_dir: Path | None = None,
                provider: Any = None, reassign: bool = False) -> AssetReport:
    from . import asset_library
    if provider not in (None, 'library'):
        raise PipelineError('Chỉ dùng kho assets có sẵn; tạo ảnh và tạo phần thiếu đã bị loại bỏ.')
    visible={c.id for shot in sb.shots for c in shot.characters}
    used={shot.location for shot in sb.shots}
    need_ai=reassign or any(c.id in visible and not c.asset_id for c in sb.characters) or any(
        loc.id in used and not loc.asset_id for loc in sb.locations)
    if need_ai:
        say('AI đối chiếu giới tính, độ tuổi, ngoại hình và bối cảnh với kho assets…', 0.1)
        asset_library.ai_assign(sb)
    notes=asset_library.assign(sb)
    asset_library.validate(sb)
    for note in notes:
        say(note)
    say('Đã gán đủ tài sản từ kho; không tạo ảnh hoặc bộ phận mới.',1.0)
    return AssetReport([c.asset_id for c in sb.characters if c.id in visible and c.asset_id],
                       [loc.asset_id for loc in sb.locations if loc.id in used and loc.asset_id],notes)


# ======================================================================= bước 3: audio
def step_audio(pr: Project, say: Runner, *, force: bool = False) -> Storyboard:
    st = _State(pr)
    h = _audio_input_hash(pr)
    if (not force and st.get("audio").get("input") == h and pr.timed.exists() and pr.soundtrack.exists()):
        say("Âm thanh không đổi — dùng lại.", 1.0)
        return Storyboard.model_validate_json(pr.timed.read_text(encoding="utf-8"))
    from .audio.mixer import build_soundtrack
    from .audio.timing import fill_timing, film_duration

    from .render.film import check_shot_ids

    sb = load_storyboard(pr)
    try:
        check_shot_ids(sb)
    except ValueError as e:
        raise PipelineError(str(e)) from e
    if not sb.shots:
        raise PipelineError("storyboard.json không có shot nào.")
    t0 = time.monotonic()
    n_lines = sum(len(s.lines) for s in sb.shots)
    say(f"Lồng tiếng {n_lines} câu + khớp khẩu hình…", 0.0)
    script_text = pr.script.read_text(encoding="utf-8") if pr.script.exists() else None
    fill_timing(sb, pr.dir, progress=lambda m, f: say(m, 0.85 * f), script_text=script_text)
    save_storyboard(pr, sb, timed=True)
    say(f"Trộn nhạc + hiệu ứng ({film_duration(sb):.1f} s)…", 0.9)
    build_soundtrack(sb, pr.dir, pr.soundtrack)
    st = _State(pr)
    st.set("audio", input=h, duration=film_duration(sb), seconds=round(time.monotonic() - t0, 1))
    say(f"Xong âm thanh: {film_duration(sb):.1f} s phim, {time.monotonic() - t0:.1f} s xử lý.", 1.0)
    return sb


# ======================================================================= bước 4: render
def _timed_or_audio(pr: Project, say: Runner) -> Storyboard:
    from . import asset_library
    source = load_storyboard(pr)
    try:
        asset_library.validate(source)
    except asset_library.MissingAssets:
        step_assets(source, say, project_dir=pr.dir)
        save_storyboard(pr, source)
    sb, timed = load_render_storyboard(pr)
    if timed and pr.soundtrack.exists():
        return sb
    say("Âm thanh chưa có hoặc đã cũ so với storyboard.json — chạy bước Âm thanh trước.")
    prev = say.step
    say.step = "audio"
    try:
        return step_audio(pr, say)
    finally:
        say.step = prev


def step_render(pr: Project, say: Runner, *, force: bool = False, workers: int | None = None) -> Path:
    from .render import render_film

    sb = _timed_or_audio(pr, say)
    t0 = time.monotonic()
    say(f"Dựng {len(sb.shots)} shot…", 0.0)
    render_film(sb, pr.dir, pr.final, soundtrack=pr.soundtrack if pr.soundtrack.exists() else None,
                workers=workers, force=force,
                progress=lambda d, n, sid: say(f"Shot {d}/{n}" + (f" ({sid})" if sid else ""), d / max(1, n)))
    dt = time.monotonic() - t0
    _State(pr).set("render", seconds=round(dt, 1), output=pr.final.name)
    say(f"Xong phim: {pr.final} ({dt:.1f} s).", 1.0)
    return pr.final


def render_shots(p: str | Path, shot_ids: Sequence[str], *, progress: ProgressCB | None = None) -> list[Path]:
    """Render lại một số shot (xem trước). Ghi shots/<id>.mp4 + .hash để render_film dùng lại."""
    from .render.compositor import render_shot
    from .render.encode import pick_encoder
    from .render.film import frame_counts, shot_hash

    pr = project(p)
    say = Runner(pr, progress)
    say.step = "render"
    sb = _timed_or_audio(pr, say)
    w, h, fps = int(config.get("render.width", 1920)), int(config.get("render.height", 1080)), int(config.get("render.fps", 30))
    counts = frame_counts(sb, fps)
    idx = {s.id: i for i, s in enumerate(sb.shots)}
    missing = [s for s in shot_ids if s not in idx]
    if missing:
        raise PipelineError(f"Không có shot: {', '.join(missing)}")
    outs = []
    pr.shots_dir.mkdir(parents=True, exist_ok=True)
    for k, sid in enumerate(shot_ids):
        i = idx[sid]
        out = pr.shots_dir / f"{sid}.mp4"
        say(f"Render shot {sid}…", k / len(shot_ids))
        render_shot(sb.shots[i], sb, pr.dir, out, width=w, height=h, fps=fps, n_frames=counts[i])
        (pr.shots_dir / f"{sid}.hash").write_text(
            shot_hash(sb.shots[i], sb, pr.dir, w, h, fps, counts[i], pick_encoder()), encoding="utf-8")
        outs.append(out)
    say(f"Xong {len(outs)} shot.", 1.0)
    return outs


def preview_shot(p: str | Path, shot_id: str, *, progress: ProgressCB | None = None) -> Path:
    """Shot kèm tiếng (đoạn soundtrack tương ứng) để xem trước trong UI: shots/<id>.preview.mp4."""
    from .audio.timing import shot_offsets
    from .render.encode import ffmpeg_exe

    pr = project(p)
    vid = render_shots(pr.dir, [shot_id], progress=progress)[0]
    sb, timed = load_render_storyboard(pr)
    if not (timed and pr.soundtrack.exists()):
        return vid
    i = [s.id for s in sb.shots].index(shot_id)
    off = shot_offsets(sb)[i]
    out = vid.with_suffix(".preview.mp4")
    import subprocess
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(vid),
                        "-ss", f"{off:.3f}", "-i", str(pr.soundtrack), "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(out)],
                       capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return out if r.returncode == 0 and out.exists() else vid


# ======================================================================= run
def run(p: str | Path, steps: Iterable[str] | None = None, *, force: bool | Iterable[str] = False,
        provider: Any = None, progress: ProgressCB | None = None, model: str | None = None,
        workers: int | None = None) -> dict[str, Any]:
    """Chạy các bước theo thứ tự chuẩn. force=True (mọi bước) hoặc tập tên bước cần làm lại.

    Resumable: storyboard.json đã có -> bỏ qua breakdown; âm thanh không đổi -> dùng lại; shot không đổi -> dùng lại
    (render_film so hash từng shot). Trả dict kết quả (đường dẫn phim, thời gian từng bước).
    """
    if provider not in (None, 'library'):
        raise PipelineError('Chỉ dùng kho assets có sẵn; không có provider tạo ảnh.')
    pr = project(p)
    want = list(steps) if steps else list(STEPS)
    bad = [s for s in want if s not in STEPS]
    if bad:
        raise PipelineError(f"Bước không hợp lệ: {bad} (hợp lệ: {', '.join(STEPS)})")
    forced = set(STEPS) if force is True else set(force or ())
    say = Runner(pr, progress)
    handler = _FileLogHandler(say)
    root_log = logging.getLogger("storytoon")
    root_log.addHandler(handler)
    if root_log.level == logging.NOTSET or root_log.level > logging.INFO:
        root_log.setLevel(logging.INFO)
    result: dict[str, Any] = {"project": str(pr.dir), "timings": {}}
    state = _State(pr)
    state.data["last_run"] = {"started": _now(), "steps": want, "status": "running"}
    state.save()
    say(f"=== Bắt đầu: {', '.join(STEP_LABELS[s] for s in STEPS if s in want)} — project {pr.name}")
    t_all = time.monotonic()
    try:
        if 'breakdown' not in want and any(s in want for s in ('assets','audio','render')):
            say.step='breakdown'
            step_breakdown(pr,say,model=model)
        for step in STEPS:
            if step not in want:
                continue
            say.step = step
            t0 = time.monotonic()
            if step == "breakdown":
                step_breakdown(pr, say, force=step in forced, model=model)
            elif step == "assets":
                mapped = load_storyboard(pr)
                try:
                    rep = step_assets(mapped, say, project_dir=pr.dir, provider=provider, reassign=step in forced)
                finally:
                    save_storyboard(pr, mapped)
                result["assets"] = rep.__dict__
                _State(pr).set("assets", **rep.__dict__)
            elif step == "audio":
                step_audio(pr, say, force=step in forced)
            elif step == "render":
                result["final"] = str(step_render(pr, say, force=step in forced, workers=workers))
            result["timings"][step] = round(time.monotonic() - t0, 1)
        say.step = ""
        say(f"=== Hoàn tất sau {time.monotonic() - t_all:.1f} s", 1.0)
        st = _State(pr)
        st.data["last_run"].update(status="done", finished=_now(), timings=result["timings"])
        st.save()
        return result
    except BaseException as e:
        say(f"LỖI: {e}")
        if isinstance(e, Exception):
            from . import errorlog
            errorlog.record(f"Bước {STEP_LABELS.get(say.step, say.step or '-')}", e, project=pr.name,
                            folder=pr.dir, steps=", ".join(want),
                            forced=", ".join(sorted(forced)) or None)
            say(f"Chi tiết lỗi đã ghi vào {errorlog.LOG_FILE}")
        st = _State(pr)
        st.data["last_run"].update(status="failed", finished=_now(), error=str(e)[:2000], step=say.step)
        st.save()
        raise
    finally:
        root_log.removeHandler(handler)

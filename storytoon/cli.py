"""StoryToon: script breakdown, library casting, audio and rendering."""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def _progress(step: str, frac: float, msg: str) -> None:
    pct = f"{frac * 100:5.1f}%" if frac >= 0 else "      "
    print(f"[{step or '-':9s}] {pct} {msg}", flush=True)


def cmd_new(a: argparse.Namespace) -> int:
    from .pipeline import new_project
    text = Path(a.script).read_text(encoding="utf-8") if a.script else ""
    pr = new_project(a.name, text)
    print(f"Đã tạo project: {pr.dir}\nViết kịch bản vào: {pr.script}")
    return 0


def _run_steps(a: argparse.Namespace, steps: list[str]) -> int:
    from .pipeline import run
    force = bool(getattr(a, "force", False))
    res = run(a.project, steps, force=force, provider=getattr(a, "provider", None), progress=_progress,
              model=getattr(a, "model", None), workers=getattr(a, "workers", None))
    print("Thời gian (s):", res.get("timings"))
    if res.get("final"):
        print("Phim:", res["final"])
    return 0


def cmd_render(a: argparse.Namespace) -> int:
    if a.shots:
        from .pipeline import render_shots
        outs = render_shots(a.project, [s.strip() for s in a.shots.split(",") if s.strip()], progress=_progress)
        for o in outs:
            print(o)
        return 0
    return _run_steps(a, ["render"])


def cmd_ui(a: argparse.Namespace) -> int:
    from .ui import main
    return main(["--port", str(a.port)] + (["--no-browser"] if a.no_browser else []))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="storytoon", description="StoryToon — kịch bản tiếng Việt thành phim hoạt hình 2D")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="tạo project mới")
    p.add_argument("name")
    p.add_argument("--script", help="chép kịch bản từ file .txt này")
    p.set_defaults(fn=cmd_new)

    def proj(name: str, help_: str, steps: list[str] | None, *, provider: bool = False, model: bool = False,
             workers: bool = False) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_)
        p.add_argument("project", help="tên project (trong projects/) hoặc đường dẫn")
        p.add_argument("--force", action="store_true", help="làm lại dù đã có kết quả")
        if provider:
            p.add_argument("--provider", choices=["library"], default=None, help="mặc định theo config.yaml")
        if model:
            p.add_argument("--model", default=None, help="model phân tích kịch bản")
        if workers:
            p.add_argument("--workers", type=int, default=None, help="số tiến trình render")
        if steps is not None:
            p.set_defaults(fn=lambda a, s=steps: _run_steps(a, s))
        return p

    proj("breakdown", "tách kịch bản bằng AI", ["breakdown"], model=True)
    proj("assets", "gán nhân vật và nền từ kho assets", ["assets"], provider=True)
    proj("audio", "lồng tiếng + khẩu hình + nhạc", ["audio"])
    p = proj("render", "dựng phim", None, workers=True)
    p.add_argument("--shots", default="", help="chỉ render các shot này, vd s001,s002")
    p.set_defaults(fn=cmd_render)
    p = proj("run", "chạy mọi bước", None, provider=True, model=True, workers=True)
    p.add_argument("--steps", default="", help="vd audio,render (mặc định: tất cả)")
    p.set_defaults(fn=lambda a: _run_steps(a, [s.strip() for s in a.steps.split(",") if s.strip()] or None))

    p = sub.add_parser("ui", help="mở giao diện")
    p.add_argument("--port", type=int, default=7860)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(fn=cmd_ui)
    return ap


def main(argv: list[str] | None = None) -> int:
    _utf8()
    from .tools_bin import add_bundled_to_path
    add_bundled_to_path()  # bản portable: runtime\ffmpeg cho cả thư viện tự gọi `ffmpeg`
    argv = list(sys.argv[1:] if argv is None else argv)
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    for h in logging.getLogger().handlers:   # pipeline bật INFO cho log.txt; console chỉ in cảnh báo
        h.setLevel(logging.INFO if a.verbose else logging.WARNING)
    try:
        return int(a.fn(a) or 0)
    except KeyboardInterrupt:
        print("Đã dừng.")
        return 130
    except Exception as e:  # noqa: BLE001
        from .asset_library import MissingAssets
        from .pipeline import PipelineError
        if isinstance(e, (PipelineError, MissingAssets)):
            print(f"Lỗi: {e}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())

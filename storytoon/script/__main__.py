"""python -m storytoon.script <script.txt> [-o storyboard.json] [--model M] [--stats-only]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..schema import Storyboard
from .. import config
from .breakdown import BreakdownError, breakdown
from .stats import storyboard_stats


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="storytoon.script", description="Tách kịch bản thành storyboard bằng ChatGPT")
    ap.add_argument("input", type=Path, help="script.txt, hoặc storyboard.json khi dùng --stats-only")
    ap.add_argument("-o", "--output", type=Path, help="mặc định: storyboard.json cạnh file input")
    ap.add_argument("--model", default=None)
    ap.add_argument("--stats-only", action="store_true", help="chỉ in thống kê của một storyboard.json")
    args = ap.parse_args(argv)

    if args.stats_only:
        sb = Storyboard.model_validate_json(args.input.read_text(encoding="utf-8"))
        print(storyboard_stats(sb).summary())
        return 0

    text = args.input.read_text(encoding="utf-8")
    out = args.output or args.input.with_name("storyboard.json")
    try:
        from ..chatgpt import generate
        sb = breakdown(text, model=args.model,
                       generate_text=generate, provider_name='ChatGPT',
                       on_progress=lambda i, n, msg: print(f"[{i}/{n}] {msg}", flush=True))
    except (BreakdownError, RuntimeError) as e:
        print(f"Lỗi: {e}", file=sys.stderr)
        return 1
    out.write_text(sb.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
    print(f"Đã ghi {out}")
    print(storyboard_stats(sb).summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

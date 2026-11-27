"""Đọc config.yaml (+ .env) thành dict. Dùng: from storytoon.config import cfg, get."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import yaml

from .paths import CONFIG_FILE, ROOT


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for raw in env.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@lru_cache(maxsize=1)
def cfg() -> dict[str, Any]:
    _load_dotenv()
    data = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}
    return data or {}


def get(path: str, default: Any = None) -> Any:
    """get("library.style", "cutout")"""
    cur: Any = cfg()
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur



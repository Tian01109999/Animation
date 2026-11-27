"""Text-provider settings. All visuals come from the local library."""
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Any
import yaml
from . import config, paths
log=logging.getLogger(__name__)
def load_config_file() -> dict[str, Any]:
    if not paths.CONFIG_FILE.exists():
        return {}
    return yaml.safe_load(paths.CONFIG_FILE.read_text(encoding="utf-8")) or {}


def save_settings(updates: dict[str, Any]) -> None:
    """Ghi các khoá dạng 'library.style' vào config.yaml (giữ nguyên khoá khác). Không bao giờ ghi API key."""
    data = load_config_file()
    for dotted, val in updates.items():
        if dotted.endswith("api_key"):
            continue
        cur = data
        keys = dotted.split(".")
        for k in keys[:-1]:
            if not isinstance(cur.get(k), dict):
                cur[k] = {}
            cur = cur[k]
        cur[keys[-1]] = val
    data.pop('gemini',None)
    data.pop('flow',None)
    data['script']={'provider':'chatgpt'}
    data['library']={'style':'cutout'}
    data['image_provider']='library'
    header='# Cấu hình StoryToon Desktop\n'
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=None)
    tmp = paths.CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(header + body, encoding="utf-8")
    tmp.replace(paths.CONFIG_FILE)
    config.cfg.cache_clear()


def setup_status() -> tuple[bool, list[str]]:
    todo=[]
    from . import chatgpt
    if not chatgpt.connected():
        todo.append('Chưa kết nối ChatGPT — bấm Đăng nhập ChatGPT (OAuth).')
    return not todo,todo

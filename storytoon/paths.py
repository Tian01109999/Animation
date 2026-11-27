"""Đường dẫn gốc của app (portable — mọi thứ tương đối theo thư mục chứa package)."""
from pathlib import Path
import os

ROOT = Path(os.environ.get('STORYTOON_DATA_ROOT') or Path(__file__).resolve().parent.parent).resolve()
ASSETS = ROOT / "assets"
CHARACTERS = ASSETS / "characters"
ACTIONS = ASSETS / "actions"
LOCATIONS = ASSETS / "locations"
INSERTS = ASSETS / "inserts"
FONTS = ASSETS / "fonts"
SFX = ASSETS / "sfx"
MUSIC = ASSETS / "music"
PROJECTS = ROOT / "projects"
RUNTIME = ROOT / "runtime"
LOGS = ROOT / "logs"
VOICE_PREVIEWS = ROOT / "cache" / "voice-previews"
CONFIG_FILE = ROOT / "config.yaml"

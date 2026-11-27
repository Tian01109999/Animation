"""One-time source migration to the existing-asset workflow."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
def edit(name, fn):
    p=ROOT/name
    p.write_text(fn(p.read_text(encoding='utf-8')),encoding='utf-8')

def cli(s):
    s='"""StoryToon: script breakdown, library casting, audio and rendering."""\n'+s[s.index('from __future__'):]
    s=s[:s.index('def cmd_flow_login')]+s[s.index('def cmd_ui'):]
    a=s.index('    sub.add_parser("flow-login"')
    b=s.index('    p = sub.add_parser("ui"',a)
    s=s[:a]+s[b:]
    a=s.index('    if argv[:1] == ["flow-recon"]:')
    b=s.index('    a = build_parser()',a)
    s=s[:a]+s[b:]
    s=s.replace('choices=["flow", "mock"]','choices=["library"]')
    s=s.replace('from .imagegen import ImageGenError','from .asset_library import MissingAssets')
    s=s.replace('(PipelineError, ImageGenError)','(PipelineError, MissingAssets)')
    s=s.replace('model Gemini','model phân tích kịch bản').replace('tách kịch bản bằng Gemini','tách kịch bản bằng AI')
    return s.replace('tạo tài sản còn thiếu','gán nhân vật và nền từ kho assets')
edit('storytoon/cli.py',cli)
edit('storytoon/render/__init__.py',lambda s:s[:s.index('def make_character')]+ '__all__ = ["render_shot", "render_film"]\n')
def location(s):
    a=s.index('def placeholder_bg('); b=s.index('@lru_cache',a)
    s=s[:a]+s[b:]
    a=s.index('    if placeholder:\n',s.index('def _load_location_cached'))
    b=s.index('    if not size:',a)
    s=s[:a]+'    if placeholder:\n        raise FileNotFoundError(f"Không có nền trong kho: {lid}")\n'+s[b:]
    a=s.index('    if placeholder:\n',s.index('def _load_insert_cached'))
    b=s.index('    size = ',a)
    return s[:a]+'    if placeholder:\n        raise FileNotFoundError(f"Không có ảnh chèn trong kho: {iid}")\n'+s[b:]
edit('storytoon/render/location.py',location)
def compositor(s):
    a=s.index('    def _draw_stool('); b=s.index('    def render_at(',a)
    return s[:a]+s[b:]
edit('storytoon/render/compositor.py',compositor)
edit('tests/desktop_test.py',lambda s:s.replace("'Tài sản'","'Kho assets'"))
backup=ROOT/'dist/_cache/before-library-mode'
for name in ['storytoon/imagegen','storytoon/render/puppetgen.py','storytoon/render/locgen.py']:
    source=ROOT/name
    dest=backup/name
    dest.parent.mkdir(parents=True,exist_ok=True)
    if source.is_dir():
        shutil.copytree(source,dest,dirs_exist_ok=True)
        shutil.rmtree(source)
    elif source.exists():
        shutil.copy2(source,dest)
        source.unlink()
print('Removed visual generation code; developer backup retained outside app payload.')

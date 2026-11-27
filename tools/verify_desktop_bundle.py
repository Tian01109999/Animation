"""Verify the delivered EXE overlay, complete runtime and absence of private state."""
from pathlib import Path
import hashlib
import struct
import sys
import zipfile

path = Path(__file__).resolve().parent.parent / 'dist' / 'StoryToon-Desktop-Portable.exe'
source_root=path.parent/'StoryToon-data' if '--assets-only' in sys.argv else path.parent.parent
with path.open('rb') as stream:
    stream.seek(-56, 2)
    length, = struct.unpack('<q', stream.read(8))
    expected = stream.read(32)
    assert stream.read(16) == b'STORYTOON-PKG001'
    assert 0 < length < path.stat().st_size - 56
    stream.seek(path.stat().st_size - 56 - length)
    digest, remaining = hashlib.sha256(), length
    while remaining:
        chunk = stream.read(min(1024 * 1024, remaining))
        assert chunk
        digest.update(chunk)
        remaining -= len(chunk)
    assert digest.digest() == expected, 'Payload digest does not match'
with zipfile.ZipFile(path) as archive:
    names = archive.namelist()
    assert len(names) == len(set(names)), 'Duplicate package entries'
    for source in ['storytoon/account.py', 'storytoon/ui.py',
                   'storytoon/script/breakdown.py', 'storytoon/asset_library.py',
                   'storytoon/chatgpt.py', 'storytoon/pipeline.py', 'storytoon/script/llm_schema.py']:
        assert archive.read(source) == (source_root / source).read_bytes(), source
    for required in ['StoryToon.exe', 'Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll',
                     'WebView2Loader.dll', 'runtime/python/python.exe', 'runtime/ffmpeg/ffmpeg.exe',
                     'runtime/ffmpeg/ffprobe.exe', 'storytoon/desktop_server.py']:
        assert required in names, required
    assert 'runtime/codex/codex.exe' in names
    for name in names:
        assert not name.startswith('storytoon/imagegen/'),name
        assert name not in ('storytoon/render/puppetgen.py','storytoon/render/locgen.py'),name
        assert not name.startswith(('logs/', 'runtime/chrome-profile/', 'runtime/desktop-webview/', 'assets/library/')), name
        assert Path(name).name not in {'.env', 'jobs.sqlite', 'flow_usage.json', 'auth.json'}, name
        assert 'chatgpt-account/' not in name, name
    import yaml
    config = yaml.safe_load(archive.read('config.yaml'))
    assert 'gemini' not in config
    assert not any(name.startswith('storytoon/gemini') for name in names)
    assert not any(name.startswith('runtime/python/Lib/site-packages/google/genai/') for name in names)
    assert 'flow' not in config
    assert config['image_provider']=='library'
    assert config['script']['provider'] == 'chatgpt'
    for asset in (source_root/'assets').rglob('*'):
        if asset.is_file() and asset.relative_to(source_root/'assets').parts[0] in ('characters','locations','inserts'):
            assert archive.read(asset.relative_to(source_root).as_posix())==asset.read_bytes(),asset
    assert archive.testzip() is None
print(f'OK: payload SHA256, archive CRC, runtime and clean configuration ({len(names)} files)')

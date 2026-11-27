"""Apply the verified library build while preserving projects, settings and login state."""
from pathlib import Path
from datetime import datetime
import hashlib,shutil,json,yaml

ROOT=Path(__file__).resolve().parents[1]
target=(ROOT/'dist/StoryToon-data').resolve()
assert target.is_relative_to((ROOT/'dist').resolve()) and (target/'runtime/python/python.exe').is_file()
backup=ROOT/'dist/_cache'/('installed-before-library-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
source_dir=(target/'storytoon').resolve()
assert source_dir.is_relative_to(target) and source_dir.name=='storytoon'
shutil.copytree(source_dir,backup/'storytoon')
shutil.copy2(target/'config.yaml',backup/'config.yaml')
shutil.copy2(target/'StoryToon.exe',backup/'StoryToon.exe')
project=target/'projects/demo/storyboard.json'
if project.exists():shutil.copy2(project,backup/'demo-storyboard.json')
shutil.rmtree(source_dir)
shutil.copytree(ROOT/'storytoon',source_dir,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for kind in ('characters','locations','inserts','actions','fonts','music','sfx'):
    shutil.copytree(ROOT/'assets'/kind,target/'assets'/kind,dirs_exist_ok=True)
shutil.copy2(ROOT/'dist/_cache/native-refresh/StoryToon.exe',target/'StoryToon.exe')
shutil.copy2(ROOT/'README.md',target/'README.md')
settings=yaml.safe_load((target/'config.yaml').read_text(encoding='utf-8'))
settings.pop('flow',None)
settings['image_provider']='library'
settings.setdefault('library',{})['style']='cutout'
(target/'config.yaml').write_text(yaml.safe_dump(settings,allow_unicode=True,sort_keys=False),encoding='utf-8')
mapped=ROOT/'runtime/library-live-check/storyboard.json'
if project.exists() and mapped.exists():
    original=json.loads(project.read_text(encoding='utf-8'))
    updated=json.loads(mapped.read_text(encoding='utf-8'))
    def dialogue(sb):return [(s['id'],[(l.get('speaker','narrator'),l['text']) for l in s.get('lines',[])]) for s in sb['shots']]
    assert dialogue(original)==dialogue(updated),'User changed the script during testing; do not overwrite.'
    assert [(c['id'],c['name']) for c in original['characters']]==[(c['id'],c['name']) for c in updated['characters']]
    shutil.copy2(mapped,project)
payload=ROOT/'dist/_cache/storytoon-desktop-payload.zip'
with payload.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
(target/'.bundle-id').write_text(digest,encoding='ascii')
print('Installed library build updated. Existing projects and account state preserved.')

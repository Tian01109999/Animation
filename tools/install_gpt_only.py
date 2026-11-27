"""Update only the GPT/UI code; retain all user projects and existing visual assets."""
from pathlib import Path
from datetime import datetime
import shutil,yaml
ROOT=Path(__file__).resolve().parents[1]
target=ROOT/'dist/StoryToon-data'
backup=ROOT/'dist/_cache'/('installed-before-gpt-only-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir()
files=['account.py','config.py','chatgpt.py','ui.py','pipeline.py','asset_library.py',
       'script/__init__.py','script/__main__.py','script/breakdown.py','script/prompts.py',
       'script/llm_schema.py','script/vocab.py']
for name in files:
 dest=target/'storytoon'/name
 saved=backup/'storytoon'/name;saved.parent.mkdir(parents=True,exist_ok=True)
 if dest.exists():shutil.copy2(dest,saved)
 shutil.copy2(ROOT/'storytoon'/name,dest)
for name in ['gemini_models.py','gemini_request.py']:
 source=target/'storytoon'/name
 if source.exists():shutil.move(str(source),str(backup/name))
 for pyc in (target/'storytoon/__pycache__').glob(Path(name).stem+'.*.pyc'):
  shutil.move(str(pyc),str(backup/pyc.name))
sdk=target/'runtime/python/Lib/site-packages'
for source in [sdk/'google/genai',*sdk.glob('google_genai-*.dist-info')]:
 if source.exists():shutil.move(str(source),str(backup/source.name))
for base in [ROOT,target]:
 p=base/'config.yaml';data=yaml.safe_load(p.read_text(encoding='utf-8')) or {}
 data.pop('gemini',None);data.pop('flow',None)
 data['script']={'provider':'chatgpt'};data['library']={'style':'cutout'};data['image_provider']='library'
 p.write_text(yaml.safe_dump(data,allow_unicode=True,sort_keys=False),encoding='utf-8')
 env=base/'.env'
 if env.exists():
  lines=[line for line in env.read_text(encoding='utf-8').splitlines() if line.strip().split('=',1)[0].strip()!='GEMINI_API_KEY']
  env.write_text('\n'.join(lines)+'\n',encoding='utf-8')
shutil.copy2(ROOT/'README.md',target/'README.md')
print('GPT-only update installed. Projects, visual library and ChatGPT session preserved.')

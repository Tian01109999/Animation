"""One-time non-destructive migration of installed desktop data to the root."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import shutil
import yaml

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'dist/StoryToon-data'
REPORT=ROOT/'runtime/root-migration.json'


def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def tree(path):
    return {p.relative_to(path).as_posix():digest(p) for p in path.rglob('*') if p.is_file()}


def relocate(value, old, new):
    if isinstance(value,dict):return {k:relocate(v,old,new) for k,v in value.items()}
    if isinstance(value,list):return [relocate(v,old,new) for v in value]
    if isinstance(value,str):
        normalized=value.replace('\\','/');prefix=old.as_posix()
        if normalized.lower().startswith(prefix.lower()+'/'):
            return new.as_posix()+normalized[len(prefix):]
    return value


def main():
    if REPORT.exists():raise RuntimeError('Migration already recorded; do not re-import automatically.')
    if not (OLD/'runtime/python/python.exe').is_file():raise RuntimeError('Old portable runtime missing')
    backup=ROOT/'runtime/migrations'/datetime.now().strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True)
    report={'root':str(ROOT),'projects':{},'assets_added':[],'same_id_assets_kept_from_root':[]}
    for kind in ('python','ffmpeg','rhubarb','codex'):
        src=OLD/'runtime'/kind;dst=ROOT/'runtime'/kind
        print('Copying portable runtime: '+kind,flush=True)
        if kind=='python' and dst.exists():raise RuntimeError('Root Python already exists; inspect before replacing')
        shutil.copytree(src,dst,dirs_exist_ok=True)
    for name in ('Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll',
                 'WebView2Loader.dll','WebView2-LICENSE.txt'):
        shutil.copy2(OLD/name,ROOT/name)
    for category in ('characters','locations'):
        for src in (OLD/'assets'/category).iterdir():
            if not src.is_dir():continue
            dst=ROOT/'assets'/category/src.name
            if not dst.exists():
                shutil.copytree(src,dst);report['assets_added'].append(category+'/'+src.name)
            elif tree(src)!=tree(dst):
                report['same_id_assets_kept_from_root'].append(category+'/'+src.name)
    for category in ('inserts','actions','fonts','music','sfx'):
        for src in (OLD/'assets'/category).rglob('*'):
            if not src.is_file():continue
            dst=ROOT/'assets'/category/src.relative_to(OLD/'assets'/category)
            if not dst.exists():
                dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
                report['assets_added'].append(dst.relative_to(ROOT/'assets').as_posix())
    for src in sorted((OLD/'projects').iterdir()):
        if not src.is_dir():continue
        dst=ROOT/'projects'/src.name
        if dst.exists() and tree(src)==tree(dst):
            report['projects'][src.name]=dst.name
            continue
        if dst.exists():
            dst=dst.with_name(src.name+'_portable');n=2
            while dst.exists():dst=dst.with_name(src.name+'_portable_'+str(n));n+=1
        print('Preserving project: '+src.name+' -> '+dst.name,flush=True)
        shutil.copytree(src,dst)
        assert tree(src)==tree(dst), 'Project copy incomplete'
        for file in dst.rglob('*.json'):
            try:data=json.loads(file.read_text(encoding='utf-8'))
            except (ValueError,UnicodeError):continue
            updated=relocate(data,src,dst)
            if updated!=data:file.write_text(json.dumps(updated,ensure_ascii=False,indent=2),encoding='utf-8')
        report['projects'][src.name]=dst.name
    config=ROOT/'config.yaml'
    if config.exists():shutil.copy2(config,backup/'config.source.yaml')
    settings=yaml.safe_load((OLD/'config.yaml').read_text(encoding='utf-8')) or {}
    settings.pop('gemini',None);settings.pop('flow',None)
    settings['script']={'provider':'chatgpt'};settings['library']={'style':'cutout'}
    settings['image_provider']='library'
    settings.setdefault('app',{})['default_project']=report['projects'].get('demo','demo')
    config.write_text(yaml.safe_dump(settings,allow_unicode=True,sort_keys=False),encoding='utf-8')
    # The existing LocalAppData ChatGPT home is reused; credentials are not copied.
    shutil.copytree(OLD/'logs',ROOT/'logs/portable-before-root',dirs_exist_ok=True)
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Migration recorded: '+str(REPORT),flush=True)


if __name__=='__main__':main()

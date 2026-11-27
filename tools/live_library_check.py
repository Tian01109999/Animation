"""Exercise the logged-in text AI and renderer without modifying the user's project."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from storytoon import asset_library as lib,chatgpt
from storytoon.schema import Storyboard
from storytoon.render.compositor import ShotRenderer,render_shot
from storytoon.render.skutil import save_png

out=ROOT/'runtime/library-live-check'
out.mkdir(exist_ok=True)
sb=Storyboard.model_validate_json((ROOT/'dist/StoryToon-data/projects/demo/storyboard.json').read_text(encoding='utf-8'))
if '--render-only' in sys.argv:
    sb=Storyboard.model_validate_json((out/'storyboard.json').read_text(encoding='utf-8'))
before=[(s.id,[(l.speaker,l.text) for l in s.lines]) for s in sb.shots]
names=[(c.id,c.name,c.gender,c.age) for c in sb.characters]
if '--render-only' not in sys.argv:
    print('ChatGPT OAuth connected:',chatgpt.connected(),flush=True)
    print('Sending existing 25-shot story for library-only casting...',flush=True)
    lib.ai_assign(sb)
notes=lib.assign(sb)
lib.validate(sb)
assert before==[(s.id,[(l.speaker,l.text) for l in s.lines]) for s in sb.shots]
assert names==[(c.id,c.name,c.gender,c.age) for c in sb.characters]
(out/'storyboard.json').write_text(sb.model_dump_json(indent=2),encoding='utf-8')
print('PASS: all story identities and dialogue preserved; all 25 shots use existing assets.',flush=True)
for n in notes: print(n,flush=True)
shots=[next(s for s in sb.shots if s.characters),next(s for s in sb.shots if s.location.startswith('insert:'))]
for i,shot in enumerate(shots):
    shot=shot.model_copy(deep=True,update={'duration':2.0,'min_duration':2.0})
    r=ShotRenderer(shot,sb,None,width=960,height=540,fps=24,watermark='')
    save_png(r.frame(12),out/f'frame-{i}.png')
    render_shot(shot,sb,out,out/f'shot-{i}.mp4',width=640,height=360,fps=24,n_frames=48)
print('PASS: two real MP4 shots encoded from the warehouse.',flush=True)

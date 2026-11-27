"""One-time source migration to library-only visuals; keeps narrative and account data."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=ROOT/'storytoon/pipeline.py'
    s=p.read_text(encoding='utf-8')
    a=s.index('# ======================================================================= bước 2: assets')
    b=s.index('# ======================================================================= bước 3: audio',a)
    s=s[:a]+'''# ======================================================================= bước 2: gán kho assets
@dataclass
class AssetReport:
    characters_assigned: list[str] = field(default_factory=list)
    locations_assigned: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def step_assets(sb: Storyboard, say: Runner, *, project_dir: Path | None = None,
                provider: Any = None, reassign: bool = False) -> AssetReport:
    from . import asset_library
    if provider not in (None, 'library'):
        raise PipelineError('Chỉ dùng kho assets có sẵn; tạo ảnh và tạo phần thiếu đã bị loại bỏ.')
    visible={c.id for shot in sb.shots for c in shot.characters}
    used={shot.location for shot in sb.shots}
    need_ai=reassign or any(c.id in visible and not c.asset_id for c in sb.characters) or any(
        loc.id in used and not loc.asset_id for loc in sb.locations)
    if need_ai:
        say('AI đối chiếu giới tính, độ tuổi, ngoại hình và bối cảnh với kho assets…', 0.1)
        asset_library.ai_assign(sb)
    notes=asset_library.assign(sb)
    asset_library.validate(sb)
    for note in notes:
        say(note)
    say('Đã gán đủ tài sản từ kho; không tạo ảnh hoặc bộ phận mới.',1.0)
    return AssetReport([c.asset_id for c in sb.characters if c.id in visible and c.asset_id],
                       [loc.asset_id for loc in sb.locations if loc.id in used and loc.asset_id],notes)


'''+s[b:]
    s=s.replace('    if pr.storyboard.exists():\n        shutil.copy2', '    from .asset_library import assign\n    assign(sb)\n    if pr.storyboard.exists():\n        shutil.copy2',1)
    s=s.replace('    sb, timed = load_render_storyboard(pr)\n    if timed', '''    from . import asset_library
    source = load_storyboard(pr)
    try:
        asset_library.validate(source)
    except asset_library.MissingAssets:
        step_assets(source, say, project_dir=pr.dir)
        save_storyboard(pr, source)
    sb, timed = load_render_storyboard(pr)
    if timed''',1)
    s=s.replace('    pr = project(p)\n    want = list(steps)', "    if provider not in (None, 'library'):\n        raise PipelineError('Chỉ dùng kho assets có sẵn; không có provider tạo ảnh.')\n    pr = project(p)\n    want = list(steps)",1)
    s=s.replace('                rep = step_assets(load_storyboard(pr), say, project_dir=pr.dir, provider=provider)', '''                mapped = load_storyboard(pr)
                rep = step_assets(mapped, say, project_dir=pr.dir, provider=provider, reassign=step in forced)
                save_storyboard(pr, mapped)''')
    p.write_text(s,encoding='utf-8')
    p=ROOT/'storytoon/account.py';s=p.read_text(encoding='utf-8')
    a=s.index('def read_env()');b=s.index('def setup_status()')
    body=s[a:b]
    body=body.replace('    header = (', "    data.pop('flow', None)\n    data['image_provider'] = 'library'\n    header = (",1)
    p.write_text('''"""Text-provider settings. All visuals come from the local library."""
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Any
import yaml
from . import config, paths
log=logging.getLogger(__name__)
ENV_FILE=paths.ROOT/'.env'

'''+body+'''def setup_status() -> tuple[bool, list[str]]:
    todo=[]
    if config.get('script.provider','chatgpt')=='chatgpt':
        from . import chatgpt
        if not chatgpt.connected():
            todo.append('Chưa kết nối ChatGPT — bấm Đăng nhập ChatGPT (OAuth).')
    elif not has_gemini_key():
        todo.append('Chưa có Gemini API key cho công cụ tách kịch bản đã chọn.')
    return not todo,todo
''',encoding='utf-8')
    p=ROOT/'storytoon/ui.py';s=p.read_text(encoding='utf-8')
    a=s.index('WARNING_MD = (');b=s.index('SHOT_HEADERS =',a);s=s[:a]+s[b:]
    a=s.index('def _provider_name()');b=s.index('# ======================================================================= tab: tài khoản',a);s=s[:a]+s[b:]
    a=s.index('    gr.Markdown("## Tài khoản Google Flow")');b=s.index('    gr.Markdown("## Gemini API key',a);s=s[:a]+s[b:]
    a=s.index('    gr.Markdown("## Cài đặt")');b=s.index('# ======================================================================= tab: kịch bản',a)
    s=s[:a]+'''    gr.Markdown('## Kho hình ảnh và lồng tiếng')
    gr.Markdown('Hình ảnh chỉ lấy từ kho. AI chọn nhân vật/bối cảnh có sẵn; không tạo ảnh hoặc phần còn thiếu.')
    style=gr.Radio([('Nhân vật cutout','cutout'),('Người que','stick')],value=config.get('library.style','cutout'),label='Phong cách câu chuyện mới')
    with gr.Row():
        v_nar=gr.Dropdown(VOICES,value=config.get('tts.narrator_voice') or VOICES[0],label='Giọng người kể')
        v_m=gr.Dropdown(VOICES,value=config.get('tts.default_male') or VOICES[0],label='Giọng nam')
        v_f=gr.Dropdown(VOICES,value=config.get('tts.default_female') or VOICES[1],label='Giọng nữ')
    with gr.Row():
        rate=gr.Textbox(value=config.get('tts.rate') or '+0%',label='Tốc độ đọc')
        watermark=gr.Textbox(value=config.get('render.watermark') or 'StoryToon',label='Tên kênh')
        gemini_model=gr.Textbox(value=config.get('gemini.model') or 'gemini-3.8-flash',label='Model Gemini (nếu chọn Gemini)')
    save_msg=gr.Markdown()
    def save(st,nar,m,f,rt,wm,gm):
        account.save_settings({'library.style':st,'image_provider':'library','tts.narrator_voice':nar,
          'tts.default_male':m,'tts.default_female':f,'tts.rate':rt,'render.watermark':wm,'gemini.model':gm})
        return 'Đã lưu. Hình ảnh chỉ lấy trong kho assets.'
    gr.Button('💾 Lưu cài đặt').click(save,inputs=[style,v_nar,v_m,v_f,rate,watermark,gemini_model],outputs=save_msg)


'''+s[b:]
    a=s.index('def _library_items()');b=s.index('# ======================================================================= tab: xuất phim',a)
    s=s[:a]+ASSETS_UI+s[b:]
    s=s.replace('        provider = gr.Radio(["flow", "mock"], value=_provider_name(), label="Nguồn ảnh")\n','')
    s=s.replace('def do_run(p: str | None, st: list[str], prov: str, frc: bool)', 'def do_run(p: str | None, st: list[str], frc: bool)')
    s=s.replace('                                provider=prov, progress=_progress_to(say))','                                progress=_progress_to(say))')
    s=s.replace('inputs=[proj, steps, provider, force]','inputs=[proj, steps, force]')
    s=s.replace('with gr.Tab("Tài sản", id="assets"):', 'with gr.Tab("Kho assets", id="assets"):')
    p.write_text(s,encoding='utf-8')


ASSETS_UI='''def _assets_md(p):
    from . import asset_library
    sb=_sb_or_none(p)
    if sb is None:
        return 'Chọn project có storyboard để xem bản gán assets.'
    data=asset_library.catalog()
    chars={e['id']:e for e in data['characters']}
    locs={e['id']:e for e in data['locations']}
    rows=['| Loại | Nhân vật / địa điểm trong truyện | Asset đã gán |','|---|---|---|']
    for c in sb.characters:
        rows.append(f"| Nhân vật | {c.name} · {c.gender}/{c.age} | {chars.get(c.asset_id,{}).get('label','Chưa gán')} |")
    for loc in sb.locations:
        rows.append(f"| Bối cảnh | {loc.name} | {locs.get(loc.asset_id,{}).get('label','Chưa gán')} |")
    try:
        asset_library.validate(sb)
        rows.append('\\n✅ Đủ tài sản trong kho, sẵn sàng dựng phim.')
    except asset_library.MissingAssets as exc:
        rows.append('\\n⚠️ '+str(exc))
    return '\\n'.join(rows)


def build_assets_tab(proj,app):
    from . import asset_library
    gr.Markdown('## Kho assets dùng lại cho nhiều câu chuyện')
    gr.Markdown('Nhân vật được phân loại theo giới tính, tuổi, tóc, trang phục và động tác. Tên/vai trong truyện độc lập với asset. Chân dung chỉ dùng trung/cận cảnh. Không tạo ảnh hoặc phần thiếu.')
    info=gr.Markdown()
    with gr.Row():
        auto=gr.Button('🧠 AI phân tích và gán assets trong kho',variant='primary')
        refresh=gr.Button('🔄 Kiểm tra / làm mới kho')
    logbox=gr.Textbox(label='Kết quả gán assets',lines=6,interactive=False)
    with gr.Row():
        kind=gr.Radio([('Nhân vật','characters'),('Bối cảnh','locations'),('Ảnh chèn','inserts')],value='characters',label='Loại asset')
        search=gr.Textbox(label='Lọc theo giới tính / tuổi / tóc / trang phục / từ khóa')
    gallery=gr.Gallery(label='Assets hiện có',columns=5,height=520,allow_preview=True)
    with gr.Row():
        target=gr.Dropdown(label='Nhân vật / địa điểm cần gán',choices=[])
        choice=gr.Dropdown(label='Chọn asset có sẵn',choices=[])
        use=gr.Button('Dùng asset này')
    detail=gr.Markdown()
    def reload(p,k='characters',query=''):
        sb=_sb_or_none(p)
        options=[] if sb is None else [('Nhân vật · '+c.name,'c:'+c.id) for c in sb.characters]+[('Bối cảnh · '+loc.name,'l:'+loc.id) for loc in sb.locations]
        entries=asset_library.catalog().get(k,[])
        tokens=asset_library._tokens(query)
        entries=[e for e in entries if e['ready'] and (not tokens or tokens <= asset_library._tokens(e['label']+' '+e.get('description','')+' '+str(e.get('gender',''))+' '+str(e.get('age',''))))]
        return _assets_md(p),[(e['preview'],e['label']) for e in entries],gr.update(choices=options,value=options[0][1] if options else None)
    def candidates(p,selected):
        sb=_sb_or_none(p)
        if not selected or sb is None:
            return gr.update(choices=[],value=None),''
        category='characters' if selected.startswith('c:') else 'locations'
        definition=sb.character(selected[2:]) if category=='characters' else sb.location(selected[2:])
        entries=asset_library.catalog()[category]
        if category=='characters':
            entries=[e for e in entries if e.get('gender')==definition.gender]
        choices=[(e['label'],e['id']) for e in entries if e['ready']]
        value=definition.asset_id if any(i==definition.asset_id for _,i in choices) else None
        return gr.update(choices=choices,value=value),'Tên nhân vật trong câu chuyện vẫn được giữ nguyên.'
    def apply(p,selected,asset):
        if not (p and selected and asset):
            return 'Chọn nhân vật/bối cảnh và asset trước.',gr.update()
        pr=pipeline.project(p)
        sb=pipeline.load_storyboard(pr)
        definition=sb.character(selected[2:]) if selected.startswith('c:') else sb.location(selected[2:])
        definition.asset_id=asset
        pipeline.save_storyboard(pr,sb)
        return 'Đã lưu bản gán cho câu chuyện này.',_assets_md(p)
    def assign(p):
        if not p:
            yield 'Chọn project trước.',gr.update()
            return
        def work(say):
            return pipeline.run(p,['assets'],force=['assets'],progress=_progress_to(say))
        for text,result in _stream(work):
            yield text,_assets_md(p) if result is not None else gr.update()
    gr.on([proj.change,app.load,refresh.click,kind.change,search.submit],reload,inputs=[proj,kind,search],outputs=[info,gallery,target])
    target.change(candidates,inputs=[proj,target],outputs=[choice,detail])
    auto.click(assign,inputs=proj,outputs=[logbox,info])
    use.click(apply,inputs=[proj,target,choice],outputs=[logbox,info])


'''

if __name__=='__main__':
    main()

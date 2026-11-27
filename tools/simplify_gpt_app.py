"""Migrate the UI and script parser to ChatGPT only."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
backup=ROOT/'dist/_cache/before-gpt-only'
backup.mkdir(exist_ok=True)
def edit(name,fn):
 p=ROOT/name
 dest=backup/name;dest.parent.mkdir(parents=True,exist_ok=True)
 if not dest.exists():shutil.copy2(p,dest)
 p.write_text(fn(p.read_text(encoding='utf-8')),encoding='utf-8')

def ui(s):
 a=s.index('    script_provider =');b=s.index('    with gr.Row():',a);s=s[:a]+s[b:]
 s=s.replace("'Studio dùng tài khoản ChatGPT để nhận storyboard JSON; không cần Gemini API key. '","'Studio dùng tài khoản ChatGPT để tự phân tích và lưu storyboard. '")
 s=s.replace("        gpt_check = gr.Button('Kiểm tra ChatGPT')","        gpt_check = gr.Button('Kiểm tra ChatGPT')\n        gpt_logout = gr.Button('Đăng xuất GPT')")
 a=s.index('    gr.Markdown("## Gemini API key');b=s.index("    gr.Markdown('## Kho hình ảnh",a);s=s[:a]+s[b:]
 s=s.replace("    style=gr.Radio([('Nhân vật cutout','cutout'),('Người que','stick')],value=config.get('library.style','cutout'),label='Phong cách câu chuyện mới')\n",'')
 s=s.replace("        gemini_model=gr.Textbox(value=config.get('gemini.model') or 'gemini-3.8-flash',label='Model Gemini (nếu chọn Gemini)')\n",'')
 s=s.replace('def save(st,nar,m,f,rt,wm,gm):','def save(nar,m,f,rt,wm):').replace("'library.style':st","'library.style':'cutout'").replace(",'gemini.model':gm",'').replace('[style,v_nar,v_m,v_f,rate,watermark,gemini_model]','[v_nar,v_m,v_f,rate,watermark]')
 s=s.replace('    gpt_check.click(chatgpt.status, outputs=gpt_status)',"    gpt_check.click(chatgpt.status, outputs=gpt_status)\n    def logout_gpt():\n        return chatgpt.logout(),0.0,gr.update(active=False)\n    gpt_logout.click(logout_gpt,outputs=[gpt_status,gpt_deadline,gpt_timer])\n    gpt_status.attach_load_event(chatgpt.status,None)")
 # Remove the manual JSON editor and its preview controls entirely.
 a=s.index('def build_storyboard_tab(');b=s.index('def _assets_md(',a);s=s[:a]+s[b:]
 s=s.replace('            with gr.Tab("Storyboard", id="storyboard"):\n                build_storyboard_tab(proj, app)\n','')
 a=s.index("        if config.get('script.provider'");b=s.index('        save(p, text)',a);s=s[:a]+s[b:]
 a=s.index('        if ("breakdown" in st');b=s.index('        def work(say:',a);s=s[:a]+s[b:]
 s=s.replace('return pipeline.run(p, ["breakdown"], force=True, progress=_progress_to(say))','return pipeline.run(p, ["breakdown"], progress=_progress_to(say))')
 s=s.replace('    btn_save.click(save, inputs=[proj, script], outputs=logbox)','    gr.on([btn_save.click,script.blur],do_break,inputs=[proj,script],outputs=[logbox,stats,table],concurrency_id="script-sync",concurrency_limit=1)')
 s=s.replace('outputs=[logbox, stats, table])','outputs=[logbox, stats, table],concurrency_id="script-sync",concurrency_limit=1)')
 s=s.replace('"💾 Lưu kịch bản"','"💾 Lưu kịch bản và cập nhật phân cảnh"').replace('"✂️ Tách kịch bản"','"🔄 Cập nhật phân cảnh"')
 s=s.replace('    with gr.Row():\n        new_name', '    gr.Markdown("Kịch bản tự lưu và cập nhật phân cảnh khi rời ô nhập. Không cần sửa JSON; bản phân cảnh được lưu tự động.")\n    with gr.Row():\n        new_name')
 return s
edit('storytoon/ui.py',ui)

def parser(s):
 s='"""Parse and validate ChatGPT storyboard output."""\n'+s[s.index('from __future__'):]
 s=s.replace('from .. import config, gemini_models, gemini_request','from .. import config').replace('DEFAULT_MODEL = gemini_models.DEFAULT_MODEL','DEFAULT_MODEL = ""')
 a=s.index('class _ModelsAPI');b=s.index('_FENCE_RE =',a);s=s[:a]+s[b:]
 a=s.index('def _call_api(');b=s.index('def breakdown_chunk(',a);s=s[:a]+s[b:]
 s=s.replace('GenAIClient | None','Any').replace('provider_name: str = "Gemini"','provider_name: str = "ChatGPT"')
 s=s.replace('    cfg = _make_config(temperature) if generate_text is None else None','    if generate_text is None:\n        from ..chatgpt import generate\n        generate_text = generate')
 a=s.index('        if generate_text is not None:');b=s.index('        try:',a);s=s[:a]+'        text = generate_text(contents)\n'+s[b:]
 a=s.index('    """Tách kịch bản thành Storyboard.');b=s.index('    if not script_text',a);s=s[:a]+'    """Convert a script through ChatGPT, with an injectable text generator for tests."""\n'+s[b:]
 a=s.index('    model = model or config.get(');b=s.index('    kw =',a);s=s[:a]+'    model = model or ""\n'+s[b:]
 return s.replace('Gọi Gemini','Gọi ChatGPT')
edit('storytoon/script/breakdown.py',parser)
def account(s):
 a=s.index('ENV_FILE=');b=s.index('def load_config_file',a);s=s[:a]+s[b:]
 a=s.index('    if isinstance(data.get("gemini")');b=s.index('    body =',a)
 s=s[:a]+"    data.pop('gemini',None)\n    data.pop('flow',None)\n    data['script']={'provider':'chatgpt'}\n    data['library']={'style':'cutout'}\n    data['image_provider']='library'\n    header='# Cấu hình StoryToon Desktop\\n'\n"+s[b:]
 a=s.index('    if config.get(',s.index('def setup_status'));s=s[:a]+"    from . import chatgpt\n    if not chatgpt.connected():\n        todo.append('Chưa kết nối ChatGPT — bấm Đăng nhập ChatGPT (OAuth).')\n    return not todo,todo\n"
 return s
edit('storytoon/account.py',account)
edit('storytoon/config.py',lambda s:s[:s.index('def gemini_api_key')])
def pipe(s):
 a=s.index("    use_chatgpt =");b=s.index('    say(f"Gửi kịch bản',a)
 s=s[:a]+"    from . import chatgpt\n    generator, name = chatgpt.generate, 'GPT / ChatGPT'\n"+s[b:]
 return s.replace('Gemini tạo hoặc tự sửa tay','GPT tự động tạo')
edit('storytoon/pipeline.py',pipe)
for name in ('gemini_models.py','gemini_request.py'):
 src=ROOT/'storytoon'/name
 if src.exists():shutil.move(str(src),str(backup/name))
print('ChatGPT-only parser/settings and automatic storyboard UI migrated.')

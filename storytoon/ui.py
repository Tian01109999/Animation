"""Giao diện Gradio (tiếng Việt):  runtime\\venv\\Scripts\\python.exe -m storytoon.ui [--port 7860] [--no-browser]

Tab: Tài khoản & Cài đặt · Kịch bản · Storyboard · Tài sản · Xuất phim.
Việc lâu (AI phân tích, lồng tiếng, render) chạy trong luồng riêng; log được đẩy dần lên giao diện.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator

# Tắt telemetry/analytics của Gradio + Hugging Face (không gửi gì ra ngoài khi mở app).
# Phải đặt TRƯỚC khi import gradio.
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["DO_NOT_TRACK"] = "1"

import gradio as gr  # noqa: E402

from . import account, activity, chatgpt, config, errorlog, paths, pipeline
from .schema import Storyboard

log = logging.getLogger("storytoon.ui")

SHOT_HEADERS = ["Shot", "Địa điểm", "Khung", "Camera", "Nhân vật", "Lời", "Thẻ", "Giây"]


# ======================================================================= tiện ích
def _stream(work: Callable[[Callable[[str], None]], Any], *, done: Callable[[Any], Any] | None = None
            ) -> Iterator[tuple[str, Any]]:
    """Chạy work(say) trong luồng riêng, yield (log tích luỹ, kết quả|None) cho tới khi xong."""
    q: queue.Queue[str] = queue.Queue()
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            with activity.work():
                box["result"] = work(q.put)
        except Exception as e:  # noqa: BLE001
            box["error"] = e
            errorlog.record("Giao diện — tác vụ chạy nền", e,
                            task=getattr(work, "__qualname__", None))

    th = threading.Thread(target=target, daemon=True)
    th.start()
    lines: list[str] = []
    last = 0.0
    while th.is_alive() or not q.empty():
        try:
            lines.append(q.get(timeout=0.4))
        except queue.Empty:
            pass
        if time.monotonic() - last > 0.5 or not th.is_alive():
            last = time.monotonic()
            yield "\n".join(lines[-300:]), None
    if "error" in box:
        lines.append(f"❌ LỖI: {box['error']}")
        lines.append(f"Chi tiết lỗi đã ghi vào {errorlog.LOG_FILE}")
        yield "\n".join(lines[-300:]), None
        return
    yield "\n".join(lines[-300:]), (done(box.get("result")) if done else box.get("result"))


def _progress_to(say: Callable[[str], None]) -> pipeline.ProgressCB:
    def cb(step: str, frac: float, msg: str) -> None:
        pct = f"{frac * 100:3.0f}% " if frac >= 0 else ""
        say(f"[{pipeline.STEP_LABELS.get(step, step or '—')}] {pct}{msg}")
    return cb


def _sb_or_none(proj: str | None) -> Storyboard | None:
    if not proj:
        return None
    try:
        return pipeline.load_storyboard(pipeline.project(proj))
    except pipeline.PipelineError:
        return None


def shot_rows(sb: Storyboard | None) -> list[list[Any]]:
    if sb is None:
        return []
    rows = []
    for s in sb.shots:
        chars = ", ".join(f"{c.id}({c.action})" for c in s.characters)
        text = " / ".join(f"{ln.speaker}: {ln.text}" for ln in s.lines)
        rows.append([s.id, s.location, s.framing, s.camera, chars, text,
                     ", ".join(o.kind for o in s.overlays), round(s.duration or 0, 1) or ""])
    return rows


def _stats(sb: Storyboard | None) -> str:
    if sb is None:
        return "_Chưa có storyboard._"
    from .script import storyboard_stats
    return "**" + sb.title + "** — " + storyboard_stats(sb).summary()


def _partial_view(proj: str | None, *, running: bool = False) -> tuple[str, list[list[Any]]] | None:
    """(thông báo, các dòng shot) của phần tách dở khớp kịch bản hiện tại, hoặc None."""
    if not proj:
        return None
    try:
        part = pipeline.breakdown_partial(pipeline.project(proj))
    except Exception:  # noqa: BLE001 - chỉ là bản xem trước
        log.exception("Không đọc được phần tách dở")
        return None
    if not part:
        return None
    sb, done, total = part
    if running:
        msg = f"**Đang tách kịch bản: xong {done}/{total} đoạn** — bảng dưới là kết quả tạm thời."
    elif done < total:
        msg = (f"**Tách dở: đã xong {done}/{total} đoạn** (bảng dưới là kết quả tạm). "
               f"Bấm **Tách kịch bản** để làm tiếp từ đoạn {done + 1}, không phải làm lại từ đầu.")
    else:
        msg = f"**Đã tách đủ {total}/{total} đoạn nhưng chưa lưu xong.** Bấm **Tách kịch bản** để hoàn tất."
    return msg, shot_rows(sb)


def _projects_update(value: str | None = None) -> Any:
    ps = pipeline.list_projects()
    return gr.update(choices=ps, value=value if value in ps else (ps[0] if ps else None))


# ======================================================================= tab: tài khoản & cài đặt
def build_settings_tab(app) -> None:
    gr.HTML('<p><a href="/account" target="_self">Tài khoản 24Media · Đăng xuất</a></p>')
    gr.Markdown('## ChatGPT · tách kịch bản bằng GPT')
    gr.Markdown('Đăng nhập ChatGPT qua OAuth chính thức của Codex trong trình duyệt. '
                'Studio dùng tài khoản ChatGPT để tự phân tích và lưu storyboard. '
                'Phiên được Codex lưu trên máy và tự làm mới. Đây không phải tự động thao tác trang chatgpt.com.')
    with gr.Row():
        gpt_login = gr.Button('🔑 Đăng nhập ChatGPT (OAuth)', variant='primary')
        gpt_check = gr.Button('Kiểm tra ChatGPT')
        gpt_logout = gr.Button('Đăng xuất GPT')
    gpt_status = gr.Markdown('Chọn **Đăng nhập ChatGPT (OAuth)** để kết nối tài khoản.')
    gpt_timer = gr.Timer(5, active=False)
    gpt_deadline = gr.State(0.0)

    def login_gpt():
        try:
            return chatgpt.start_login(), time.monotonic() + 600, gr.update(active=True)
        except (OSError, RuntimeError) as exc:
            return str(exc), 0.0, gr.update(active=False)

    def poll_gpt(deadline):
        message = chatgpt.status()
        return message, gr.update(active=not message.startswith('✅') and time.monotonic() < deadline)

    gpt_login.click(login_gpt, outputs=[gpt_status, gpt_deadline, gpt_timer])
    gpt_check.click(chatgpt.status, outputs=gpt_status)
    def logout_gpt():
        return chatgpt.logout(),0.0,gr.update(active=False)
    gpt_logout.click(logout_gpt,outputs=[gpt_status,gpt_deadline,gpt_timer])
    app.load(chatgpt.status,outputs=gpt_status)
    gpt_timer.tick(poll_gpt, inputs=gpt_deadline, outputs=[gpt_status, gpt_timer], concurrency_limit=1)
    gr.Markdown('## Kho hình ảnh và lồng tiếng')
    gr.Markdown('Hình ảnh chỉ lấy từ kho. AI chọn nhân vật/bối cảnh có sẵn; không tạo ảnh hoặc phần còn thiếu.')
    from .audio import voices
    from .audio.preview import get_preview
    initial_engine = config.get('tts.engine', 'edge')
    if initial_engine not in ('edge', 'capcut'):
        initial_engine = 'edge'
    initial_language = config.get('tts.language', 'vi')
    if initial_language not in voices.SAMPLES:
        initial_language = 'vi'
    initial_choices = voices.choices(initial_engine, initial_language)
    with gr.Row():
        engine_pick = gr.Dropdown(voices.ENGINES, value=initial_engine, label='Bộ tạo giọng')
        language_pick = gr.Dropdown(voices.LANGUAGES, value=initial_language, label='Ngôn ngữ giọng đọc')
    gr.Markdown('Ngôn ngữ lọc danh sách giọng đọc; không tự dịch kịch bản. Giọng bên dưới áp dụng theo vai và giới tính nhân vật. '
                'Kho CapCut tiếng Thái hiện chỉ có giọng nữ; bạn vẫn có thể chọn giọng phù hợp cho vai nam.')
    with gr.Row():
        v_nar=gr.Dropdown(initial_choices,value=voices.selected(initial_engine,initial_language,config.get('tts.narrator_voice')),label='Giọng người kể')
        v_m=gr.Dropdown(initial_choices,value=voices.selected(initial_engine,initial_language,config.get('tts.default_male'),'nam'),label='Giọng nhân vật nam')
        v_f=gr.Dropdown(initial_choices,value=voices.selected(initial_engine,initial_language,config.get('tts.default_female'),'nu'),label='Giọng nhân vật nữ')
    sample_text = gr.Textbox(value=voices.SAMPLES[initial_language], label='Nội dung nghe thử (cố định)', lines=2, interactive=False)
    gr.Markdown('Mỗi giọng chỉ tạo mẫu ở lần nghe đầu, sau đó phát lại mẫu đã lưu trên máy. Đổi tốc độ dùng lại mẫu gốc.')
    with gr.Row():
        sample_role = gr.Dropdown([('Người kể', 'narrator'), ('Nhân vật nam', 'male'), ('Nhân vật nữ', 'female')],
                                  value='narrator', label='Nghe thử giọng')
        sample_button = gr.Button('▶ Nghe thử')
    sample_audio = gr.Audio(label='Giọng đọc thử', interactive=False, type='filepath', autoplay=True)
    def refresh_voices(eng, lang, nar, male, female):
        options = voices.choices(eng, lang)
        return [gr.update(choices=options, value=voices.selected(eng,lang,current,gender))
                for current, gender in ((nar,'nam'),(male,'nam'),(female,'nu'))] + [voices.SAMPLES[lang]]
    for picker in (engine_pick, language_pick):
        picker.change(refresh_voices, inputs=[engine_pick,language_pick,v_nar,v_m,v_f],
                      outputs=[v_nar,v_m,v_f,sample_text], queue=False)
    with gr.Row():
        rate=gr.Textbox(value=config.get('tts.rate') or '+0%',label='Tốc độ đọc (-50% đến +100%)')
        watermark=gr.Textbox(value=config.get('render.watermark') or 'StoryToon',label='Tên kênh')
    save_msg=gr.Markdown()
    def preview(eng,lang,nar,m,f,role,rt):
        voice = {'narrator':nar,'male':m,'female':f}[role]
        try:
            with activity.work():
                output = get_preview(eng,lang,voice,rt)
        except Exception as exc:
            raise gr.Error(str(exc)) from exc
        return str(output)
    sample_button.click(preview,inputs=[engine_pick,language_pick,v_nar,v_m,v_f,sample_role,rate],
                        outputs=sample_audio,concurrency_limit=1)
    def save(eng,lang,nar,m,f,rt,wm):
        if activity.busy():
            raise gr.Error('Đợi tác vụ đang chạy hoàn tất trước khi đổi cài đặt giọng đọc.')
        try:
            rt = voices.validate_settings(eng,lang,nar,m,f,rt)
        except ValueError as exc:
            raise gr.Error(str(exc)) from exc
        account.save_settings({'library.style':'cutout','image_provider':'library','tts.narrator_voice':nar,
          'tts.engine':eng,'tts.language':lang,'tts.use_character_voices':False,
          'tts.default_male':m,'tts.default_female':f,'tts.rate':rt,'render.watermark':wm})
        return 'Đã lưu bộ đọc, ngôn ngữ và giọng. Lần chạy Âm thanh tiếp theo sẽ cập nhật theo lựa chọn mới.'
    gr.Button('💾 Lưu cài đặt').click(save,inputs=[engine_pick,language_pick,v_nar,v_m,v_f,rate,watermark],outputs=save_msg)


# ======================================================================= tab: kịch bản
def build_script_tab(proj: gr.Dropdown, app: gr.Blocks) -> tuple[gr.Dataframe, gr.Markdown]:
    gr.Markdown("Kịch bản tự lưu và cập nhật phân cảnh khi rời ô nhập. Không cần sửa JSON; bản phân cảnh được lưu tự động.")
    with gr.Row():
        new_name = gr.Textbox(label="Tên project mới", placeholder="vd: Bánh bao nửa đêm", scale=3)
        btn_new = gr.Button("➕ Tạo project", scale=1)
    script = gr.Textbox(label="Kịch bản (tiếng Việt)", lines=18, max_lines=40,
                        placeholder="Dán kịch bản vào đây. Mỗi chương bắt đầu bằng 'Chương N'…")
    with gr.Row():
        btn_save = gr.Button("💾 Lưu kịch bản và cập nhật phân cảnh")
        btn_break = gr.Button("🔄 Cập nhật phân cảnh", variant="primary")
    logbox = gr.Textbox(label="Tiến độ", lines=6, interactive=False, autoscroll=True)
    stats = gr.Markdown()
    table = gr.Dataframe(headers=SHOT_HEADERS, label="Danh sách shot", interactive=False, wrap=True)

    def load(p: str | None) -> tuple[str, str, list]:
        if not p:
            return "", "_Chưa chọn project._", []
        pr = pipeline.project(p)
        text = pr.script.read_text(encoding="utf-8") if pr.script.exists() else ""
        partial = _partial_view(p)          # tách dở của kịch bản hiện tại → ưu tiên hiện phần đã có
        if partial:
            return text, partial[0], partial[1]
        sb = _sb_or_none(p)
        return text, _stats(sb), shot_rows(sb)

    def create(name: str) -> tuple[Any, str]:
        if not (name or "").strip():
            return gr.update(), "Nhập tên project trước."
        pr = pipeline.new_project(name.strip())
        return _projects_update(pr.name), f"Đã tạo project {pr.name}."

    def save(p: str | None, text: str) -> str:
        if not p:
            return "Chưa chọn project."
        pipeline.project(p).script.write_text(text or "", encoding="utf-8")
        return "Đã lưu script.txt."

    def do_break(p: str | None, text: str) -> Iterator[tuple[str, Any, Any]]:
        if not p:
            yield "Chưa chọn project.", gr.update(), gr.update()
            return
        save(p, text)

        def work(say: Callable[[str], None]) -> Any:
            return pipeline.run(p, ["breakdown"], progress=_progress_to(say))

        ckpt = pipeline.project(p).dir / "breakdown_parts.json"

        def ckpt_stamp() -> float:
            try:
                return ckpt.stat().st_mtime_ns
            except OSError:
                return 0

        seen = 0.0                           # chạy lại sau lỗi → hiện ngay các đoạn đã có
        finished = False
        logtext = ""
        for logtext, res in _stream(work):
            if res is not None:
                finished = True
                sb = _sb_or_none(p)
                yield logtext, _stats(sb), shot_rows(sb)
                continue
            stamp = ckpt_stamp()
            if stamp and stamp != seen:      # vừa xong thêm 1 đoạn → hiện ngay các shot đã có
                seen = stamp
                partial = _partial_view(p, running=True)
                if partial:
                    yield logtext, partial[0], partial[1]
                    continue
            yield logtext, gr.update(), gr.update()
        if not finished:                     # lỗi giữa chừng → giữ các đoạn đã xong, hướng dẫn làm tiếp
            partial = _partial_view(p)
            if partial:
                yield logtext, partial[0], partial[1]

    gr.on([proj.change, app.load], load, inputs=proj, outputs=[script, stats, table])
    btn_new.click(create, inputs=new_name, outputs=[proj, logbox])
    def sync_changed_script(p,text):
        pr=pipeline.project(p) if p else None
        if not pr or (pr.script.exists() and pr.script.read_text(encoding='utf-8')==(text or '')):
            yield gr.update(),gr.update(),gr.update()
            return
        yield from do_break(p,text)
    script.blur(sync_changed_script,inputs=[proj,script],outputs=[logbox,stats,table],concurrency_id="script-sync",concurrency_limit=1)
    btn_save.click(do_break,inputs=[proj,script],outputs=[logbox,stats,table],concurrency_id="script-sync",concurrency_limit=1)
    btn_break.click(do_break, inputs=[proj, script], outputs=[logbox, stats, table],concurrency_id="script-sync",concurrency_limit=1)
    return table, stats


# ======================================================================= tab: storyboard
def _assets_md(p):
    from . import asset_library
    sb=_sb_or_none(p)
    if sb is None:
        return 'Chọn project có storyboard để xem bản gán assets.'
    data=asset_library.catalog()
    chars={e['id']:e for e in data['characters']}
    locs={e['id']:e for e in data['locations']}
    rows=['| Loại | Nhân vật / địa điểm trong truyện | Asset đã gán |','|---|---|---|']
    for c in sb.characters:
        entry=chars.get(c.asset_id)
        rows.append(f"| Nhân vật | {c.name} · {c.gender}/{c.age} | {asset_library.caption(entry) if entry else 'Chưa gán'} |")
    for loc in sb.locations:
        rows.append(f"| Bối cảnh | {loc.name} | {locs.get(loc.asset_id,{}).get('label','Chưa gán')} |")
    try:
        asset_library.validate(sb)
        rows.append('\n✅ Đủ tài sản trong kho, sẵn sàng dựng phim.')
    except asset_library.MissingAssets as exc:
        rows.append('\n⚠️ '+str(exc))
    return '\n'.join(rows)


def _trait_choices():
    from . import asset_library
    try:
        found=sorted({t for e in asset_library.catalog()['characters'] for t in e.get('traits',[])})
    except Exception:
        found=[]
    return [(f"{asset_library.VI_TRAIT.get(t,t.replace('_',' '))} / {t}",t) for t in found]


def build_assets_tab(proj,app):
    from . import asset_library
    gr.Markdown('## Kho assets dùng lại cho nhiều câu chuyện')
    gr.Markdown('Nhân vật được phân loại theo giới tính, tuổi, tóc, trang phục và động tác. Tên/vai trong truyện độc lập với asset. Chân dung chỉ dùng trung/cận cảnh. Chọn asset sẽ tự lưu vào storyboard.json của project và cập nhật bảng gán bên trên; file asset dùng chung trong kho không bị sửa.')
    info=gr.Markdown()
    with gr.Row():
        auto=gr.Button('🧠 AI phân tích và gán assets trong kho',variant='primary')
        refresh=gr.Button('🔄 Kiểm tra / làm mới kho')
    logbox=gr.Textbox(label='Kết quả gán assets',lines=6,interactive=False)
    with gr.Row():
        kind=gr.Radio([('Nhân vật','characters'),('Bối cảnh','locations'),('Ảnh chèn','inserts')],value='characters',label='Loại asset')
        search=gr.Textbox(label='Từ khoá (Việt/Anh, có hoặc không dấu: kính / glasses, tóc xoăn / curly, ma / ghost…)')
    with gr.Row():
        f_gender=gr.Radio([('Tất cả',''),('Nam','male'),('Nữ','female')],value='',label='Giới tính')
        f_age=gr.Radio([('Tất cả',''),('Trẻ em','child'),('Trẻ','young'),('Người lớn','adult'),('Lớn tuổi','old')],value='',label='Độ tuổi')
        f_tags=gr.Dropdown(label='Đặc điểm (trait)',choices=_trait_choices(),multiselect=True,value=[])
        f_back=gr.Checkbox(False,label='Chỉ asset có góc sau lưng')
    gallery=gr.Gallery(label='Assets hiện có',columns=5,height=520,allow_preview=True)
    with gr.Row():
        target=gr.Dropdown(label='Nhân vật / địa điểm cần gán',choices=[])
        choice=gr.Dropdown(label='Chọn asset có sẵn',choices=[])
        use=gr.Button('Lưu gán asset')
    detail=gr.Markdown()
    def reload(p,k='characters',query='',gender='',age='',tags=None,back=False):
        sb=_sb_or_none(p)
        options=[] if sb is None else [('Nhân vật · '+c.name,'c:'+c.id) for c in sb.characters]+[('Bối cảnh · '+loc.name,'l:'+loc.id) for loc in sb.locations]
        entries=asset_library.catalog().get(k,[])
        people=k=='characters'
        entries=asset_library.filter_entries(entries,query=query or '',gender=(gender or None) if people else None,
                                             age=(age or None) if people else None,tags=(tags or ()) if people else (),
                                             back_view=bool(back) and people)
        return _assets_md(p),[(e['preview'],asset_library.caption(e)) for e in entries],gr.update(choices=options,value=options[0][1] if options else None)
    def candidates(p,selected):
        sb=_sb_or_none(p)
        if not selected or sb is None:
            return gr.update(choices=[],value=None),''
        category='characters' if selected.startswith('c:') else 'locations'
        definition=sb.character(selected[2:]) if category=='characters' else sb.location(selected[2:])
        entries=asset_library.catalog()[category]
        if category=='characters':
            actions={c.action for shot in sb.shots for c in shot.characters if c.id==definition.id}
            style='stick' if 'stick' in sb.style.lower() else 'cutout'
            entries=[e for e in entries if asset_library._compatible(definition,e,actions)
                     and e.get('style')==style]
            entries=sorted(entries,key=lambda e:-asset_library.score_character(definition,e))
        else:
            style='stick' if 'stick' in sb.style.lower() else 'cutout'
            entries=[e for e in entries if e.get('ready') and e.get('style')==style]
        choices=[(asset_library.caption(e) if category=='characters' else e['label'],e['id']) for e in entries if e['ready']]
        value=definition.asset_id if any(i==definition.asset_id for _,i in choices) else None
        return gr.update(choices=choices,value=value),'Tên nhân vật trong câu chuyện vẫn được giữ nguyên.'
    def apply(p,selected,asset):
        if not (p and selected and asset):
            return 'Chọn nhân vật/bối cảnh và asset trước.',gr.update(),'Chưa lưu thay đổi.'
        pr=pipeline.project(p)
        sb=pipeline.load_storyboard(pr)
        category='characters' if selected.startswith('c:') else 'locations'
        definition=sb.character(selected[2:]) if category=='characters' else sb.location(selected[2:])
        if definition is None:
            return 'Không tìm thấy nhân vật/địa điểm trong storyboard.',_assets_md(p),'Không lưu thay đổi.'
        entry=next((e for e in asset_library.catalog()[category] if e['id']==asset and e.get('ready')),None)
        style='stick' if 'stick' in sb.style.lower() else 'cutout'
        if entry is None or entry.get('style')!=style:
            return 'Asset không còn trong kho hoặc khác phong cách; chưa lưu.',_assets_md(p),'Hãy tải lại danh sách asset.'
        if category=='characters':
            actions={c.action for shot in sb.shots for c in shot.characters if c.id==definition.id}
            if not asset_library._compatible(definition,entry,actions):
                return 'Asset không phù hợp giới tính, độ tuổi hoặc động tác của nhân vật; chưa lưu.',_assets_md(p),'Chọn asset tương thích.'
        definition.asset_id=asset
        pipeline.save_storyboard(pr,sb)
        message=f'Đã gán “{entry["label"]}” cho “{definition.name}” và lưu storyboard.json. Asset dùng chung trong kho không bị sửa.'
        return message,_assets_md(p),message
    def assign(p):
        if not p:
            yield 'Chọn project trước.',gr.update()
            return
        def work(say):
            return pipeline.run(p,['assets'],force=['assets'],progress=_progress_to(say))
        for text,result in _stream(work):
            yield text,_assets_md(p) if result is not None else gr.update()
    gr.on([proj.change,app.load,refresh.click,kind.change,search.submit,f_gender.change,f_age.change,f_tags.change,f_back.change],
          reload,inputs=[proj,kind,search,f_gender,f_age,f_tags,f_back],outputs=[info,gallery,target])
    target.change(candidates,inputs=[proj,target],outputs=[choice,detail])
    auto.click(assign,inputs=proj,outputs=[logbox,info])
    choice.input(apply,inputs=[proj,target,choice],outputs=[logbox,info,detail],concurrency_id='asset-manual-assign',concurrency_limit=1)
    use.click(apply,inputs=[proj,target,choice],outputs=[logbox,info,detail],concurrency_id='asset-manual-assign',concurrency_limit=1)


# ======================================================================= tab: xuất phim
def build_export_tab(proj: gr.Dropdown, app: gr.Blocks) -> None:
    gr.Markdown("Chạy lần lượt: **Tách kịch bản** (bỏ qua nếu đã có storyboard) → **Tài sản** → **Âm thanh** → "
                "**Dựng phim**. Bước nào đã xong và không đổi sẽ được dùng lại.")
    with gr.Row():
        steps = gr.CheckboxGroup(choices=[(pipeline.STEP_LABELS[s], s) for s in pipeline.STEPS],
                                 value=list(pipeline.STEPS), label="Các bước")
        force = gr.Checkbox(False, label="Làm lại từ đầu (bỏ cache)")
    btn_run = gr.Button("▶️ Chạy tất cả", variant="primary")
    logbox = gr.Textbox(label="Nhật ký", lines=14, max_lines=30, interactive=False, autoscroll=True)
    video = gr.Video(label="Phim hoàn chỉnh (final.mp4)", interactive=False)

    def load(p: str | None) -> Any:
        if not p:
            return None
        f = pipeline.project(p).final
        return str(f) if f.exists() else None

    def do_run(p: str | None, st: list[str], frc: bool) -> Iterator[tuple[str, Any]]:
        if not p:
            yield "Chưa chọn project.", gr.update()
            return
        def work(say: Callable[[str], None]) -> Any:
            return pipeline.run(p, st or None, force=[s for s in st if s != "breakdown"] if frc else False,
                                progress=_progress_to(say))

        for logtext, res in _stream(work):
            if res is None:
                yield logtext, gr.update()
            else:
                t = res.get("timings", {})
                yield (logtext + "\n\nThời gian: " + ", ".join(f"{pipeline.STEP_LABELS[k]} {v:.0f}s" for k, v in t.items()),
                       res.get("final") or load(p))

    gr.on([proj.change, app.load], load, inputs=proj, outputs=video)
    btn_run.click(do_run, inputs=[proj, steps, force], outputs=[logbox, video])


# ======================================================================= app
def build_project_manager(proj, app):
    revision=gr.State(0)
    pending=gr.State('')
    request=gr.Textbox(elem_id='project-delete-request',container=False,interactive=True)
    trigger=gr.Button('Yêu cầu xóa project',elem_id='project-delete-trigger')
    with gr.Group(visible=False) as confirmation:
        warning=gr.Markdown()
        with gr.Row():
            confirm=gr.Button('Xóa vĩnh viễn project',variant='stop')
            cancel=gr.Button('Hủy')
    message=gr.Markdown()

    def request_delete(payload):
        name=json.loads(payload)['name']
        if name not in pipeline.list_projects():
            raise gr.Error('Project không còn tồn tại. Hãy tải lại danh sách.')
        return name,gr.update(visible=True),f'**Xóa project “{name}” khỏi máy?** Toàn bộ kịch bản, âm thanh và video trong project sẽ bị xóa. Thao tác không thể hoàn tác.'

    def remove(name,current,version):
        try:
            pipeline.delete_project(name)
        except (OSError,RuntimeError) as exc:
            return gr.update(),version,gr.update(visible=True),name,f'❌ {exc}'
        choices=pipeline.list_projects()
        selected=current if current in choices else (choices[0] if choices else None)
        return gr.update(choices=choices,value=selected),version+1,gr.update(visible=False),'',f'Đã xóa project “{name}” khỏi máy.'

    cancel.click(lambda:(gr.update(visible=False),''),outputs=[confirmation,pending])
    confirm.click(remove,inputs=[pending,proj,revision],outputs=[proj,revision,confirmation,pending,message])
    trigger.click(request_delete,inputs=request,outputs=[pending,confirmation,warning],js='() => [globalThis.storytoonDeletePayload]')


def build_app() -> gr.Blocks:
    ok, todo = account.setup_status()
    picker_js=Path(__file__).with_name('project_picker.js').read_text(encoding='utf-8')
    picker_css='''#project-delete-request,#project-delete-trigger {display:none!important}
    #project-picker [role="option"] {display:flex;align-items:center;gap:8px}
    #project-picker .project-trash {margin-left:auto;display:inline-flex;align-items:center;justify-content:center;
    flex-shrink:0;padding:5px 7px;border:0;border-radius:5px;background:transparent;color:#ef7070;cursor:pointer}
    #project-picker .project-trash:hover,#project-picker .project-trash:focus-visible {background:#ef444425;color:#ff9494;outline:1px solid #ef7070}'''
    with gr.Blocks(title="StoryToon") as app:
        gr.Markdown("# 🎬 StoryToon — kịch bản tiếng Việt thành phim hoạt hình 2D")
        if not ok:
            gr.Markdown("**Cần cài đặt:** " + " · ".join(todo))
        ps = pipeline.list_projects()
        preferred = config.get('app.default_project', 'demo')
        proj = gr.Dropdown(choices=ps, value=(preferred if preferred in ps else (ps[0] if ps else None)),
                           label="Project", allow_custom_value=False,elem_id='project-picker')
        build_project_manager(proj,app)
        with gr.Tabs(selected="settings" if not ok else "script"):
            with gr.Tab("Tài khoản & Cài đặt", id="settings"):
                build_settings_tab(app)
            with gr.Tab("Kịch bản", id="script"):
                build_script_tab(proj, app)
            with gr.Tab("Kho assets", id="assets"):
                build_assets_tab(proj, app)
            with gr.Tab("Xuất phim", id="export"):
                build_export_tab(proj, app)
    app.css=picker_css
    app.js=picker_js
    return app


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="storytoon.ui")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    errorlog.install()
    from .tools_bin import add_bundled_to_path
    add_bundled_to_path()  # bản portable: runtime\ffmpeg cho cả thư viện tự gọi `ffmpeg`
    app = build_app()
    app.queue(default_concurrency_limit=2)
    app.launch(server_name="127.0.0.1", server_port=a.port, inbrowser=not a.no_browser,
               allowed_paths=[str(paths.ROOT)], show_error=True,css=app.css,js=app.js)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

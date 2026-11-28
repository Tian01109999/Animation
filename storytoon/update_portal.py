"""In-app update page: shows what changed, downloads + installs in the background, then restarts the app."""
import asyncio
import html
import secrets
from urllib.parse import parse_qs

from fastapi import Request
from starlette.responses import HTMLResponse, JSONResponse

from . import updater

RESTART_MESSAGE = 'storytoon:restart-after-update'

_STYLE = ('body{background:#141922;color:#edf0f5;font:16px "Segoe UI",sans-serif;max-width:760px;margin:50px auto;'
          'padding:24px;line-height:1.6}a{color:#bbee8d}button{padding:12px 20px;margin:8px 8px 8px 0;cursor:pointer;'
          'border:0;border-radius:6px;background:#2c3a4f;color:#fff;font-size:15px}button.primary{background:#5d9b2f}'
          '.notes{background:#1d2430;border:1px solid #2f3b4d;border-radius:8px;padding:16px 20px;white-space:pre-wrap}'
          '.muted{color:#9aa6b8}.bar{height:14px;background:#1d2430;border:1px solid #2f3b4d;border-radius:7px;overflow:hidden}'
          '.bar>div{height:100%;width:0;background:#5d9b2f;transition:width .4s}')

# Progress page: polls /updates/status, shows a bar, asks the desktop shell to restart when installed.
_PROGRESS = """
<h2 id="title">Đang cập nhật StoryToon {version}</h2>
<p id="label">Đang bắt đầu tải…</p>
<div class="bar"><div id="fill"></div></div>
<p class="muted" id="hint">Vui lòng không đóng ứng dụng. Bạn có thể tiếp tục xem nhưng không nên chạy tác vụ mới.</p>
<p id="retry" hidden><a href="/updates">Thử lại</a></p>
<script>
(() => {
  const mb = n => (n / 1048576).toFixed(0) + ' MB';
  const $ = id => document.getElementById(id);
  let restarted = false;
  function restart() {
    if (restarted) return; restarted = true;
    $('title').textContent = 'Đã cài xong bản mới';
    $('label').textContent = 'StoryToon đang tự khởi động lại…';
    $('fill').style.width = '100%';
    $('hint').textContent = '';
    const shell = window.chrome && window.chrome.webview;
    if (shell) shell.postMessage('""" + RESTART_MESSAGE + """');
    setTimeout(() => { $('hint').textContent = 'Nếu ứng dụng chưa tự mở lại, hãy đóng StoryToon và mở lại.'; },
               shell ? 15000 : 0);
  }
  async function poll() {
    let s;
    try { s = await (await fetch('/updates/status', {cache: 'no-store'})).json(); }
    catch (e) { setTimeout(poll, 1500); return; }
    if (s.state === 'done') { restart(); return; }
    if (s.state === 'error') {
      $('title').textContent = 'Cập nhật chưa hoàn tất';
      $('label').textContent = s.message + ' Ứng dụng vẫn dùng được bình thường.';
      $('hint').textContent = ''; $('retry').hidden = false; return;
    }
    let pct = 0, text = 'Đang chuẩn bị…';
    if (s.stage === 'download') {
      pct = s.total ? s.done / s.total * 80 : 0;
      text = 'Đang tải gói cập nhật: ' + mb(s.done) + (s.total ? ' / ' + mb(s.total) : '');
    } else if (s.stage === 'verify') { pct = 82; text = 'Đang kiểm tra gói tải về…'; }
    else if (s.stage === 'install') {
      pct = 85 + (s.total ? s.done / s.total * 15 : 0);
      text = 'Đang cài đặt: ' + s.done + ' / ' + s.total + ' tệp';
    }
    $('fill').style.width = pct.toFixed(1) + '%';
    $('label').textContent = text + ' (' + pct.toFixed(0) + '%)';
    setTimeout(poll, 1000);
  }
  poll();
})();
</script>"""


def attach(app, desktop_token: str):
    updater.cleanup_previous()

    @app.get('/__desktop__/updates')
    async def desktop_check(request: Request):
        if not secrets.compare_digest(request.headers.get('X-StoryToon-Desktop', ''), desktop_token):
            return JSONResponse({'error': 'Forbidden'}, status_code=403)
        return JSONResponse(await asyncio.to_thread(updater.check_release), headers={'Cache-Control': 'no-store'})

    @app.get('/__desktop__/update-state')
    async def desktop_state(request: Request):
        if not secrets.compare_digest(request.headers.get('X-StoryToon-Desktop', ''), desktop_token):
            return JSONResponse({'error': 'Forbidden'}, status_code=403)
        return JSONResponse(updater.job_status(), headers={'Cache-Control': 'no-store'})

    def page(body: str):
        csrf = secrets.token_urlsafe(32)
        response = HTMLResponse('<!doctype html><html lang="vi"><meta charset="utf-8"><title>Cập nhật StoryToon</title>'
                                f'<style>{_STYLE}</style><h1>Cập nhật StoryToon</h1>'
                                f'<p class="muted">Phiên bản đang dùng: {html.escape(updater.__version__)}</p>'
                                + body.replace('{csrf}', csrf) +
                                '<p><a href="/">Quay lại StoryToon</a></p></html>')
        response.set_cookie('storytoon_update_csrf', csrf, httponly=True, samesite='strict', max_age=1800)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    def form(buttons: str, auto: bool = False) -> str:
        script = '<script>document.getElementById("update-form").submit()</script>' if auto else ''
        return (f'<form id="update-form" method="post"><input type="hidden" name="csrf" value="{{csrf}}">'
                f'<input type="hidden" name="action" value="{"install" if auto else "check"}">{buttons}</form>{script}')

    def progress_body(version: str) -> str:
        return _PROGRESS.replace('{version}', html.escape(version))

    def status_body(result: dict, auto: bool = False) -> str:
        if result['error']:
            return f'<p>{html.escape(result["error"])}</p>' + form('<button name="action" value="check">Kiểm tra lại</button>')
        if not result['available']:
            return '<p>StoryToon đã ở phiên bản mới nhất.</p>' + form(
                '<button name="action" value="check">Kiểm tra lại</button>')
        version = html.escape(result['version'])
        notes = html.escape(result['notes'] or 'Cải thiện và sửa lỗi.')
        return (f'<h2>Có bản mới {version}</h2><h3>Nội dung thay đổi</h3><div class="notes">{notes}</div>'
                '<p class="muted">App sẽ tự tải, cài đặt và khởi động lại. Dự án, cấu hình và tài khoản được giữ nguyên.</p>'
                + form(f'<input type="hidden" name="version" value="{version}">'
                       '<button class="primary" name="action" value="install">Cập nhật ngay</button>', auto=auto))

    @app.get('/updates/status')
    async def job():
        return JSONResponse(updater.job_status(), headers={'Cache-Control': 'no-store'})

    @app.get('/updates')
    async def show(request: Request):
        current = updater.job_status()
        if current['state'] in ('running', 'done'):
            return page(progress_body(current['version']))
        result = await asyncio.to_thread(updater.check_release)
        return page(status_body(result, auto=request.query_params.get('start') == '1' and result['available']))

    @app.post('/updates')
    async def change(request: Request):
        body = await request.body()
        if len(body) > 4096:
            return HTMLResponse('Yêu cầu quá dài.', status_code=400)
        data = parse_qs(body.decode('utf-8', errors='replace'))
        get = lambda key: data.get(key, [''])[-1]
        csrf = request.cookies.get('storytoon_update_csrf', '')
        if not csrf or not secrets.compare_digest(csrf, data.get('csrf', [''])[0]):
            return HTMLResponse('Phiên xác nhận không hợp lệ.', status_code=403)
        current = updater.job_status()
        if current['state'] in ('running', 'done'):
            return page(progress_body(current['version']))
        if get('action') == 'install':
            result = await asyncio.to_thread(updater.check_release)
            if not result['available'] or result['version'] != get('version'):
                return page(status_body(result))
            updater.start_install(result['version'])
            return page(progress_body(result['version']))
        return page(status_body(await asyncio.to_thread(updater.check_release)))

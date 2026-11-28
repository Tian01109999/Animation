"""In-app update page: shows what changed in the new version and installs it."""
import asyncio
import html
import secrets
from urllib.parse import parse_qs

from fastapi import Request
from starlette.responses import HTMLResponse, JSONResponse

from . import updater

_STYLE = ('body{background:#141922;color:#edf0f5;font:16px "Segoe UI",sans-serif;max-width:760px;margin:50px auto;'
          'padding:24px;line-height:1.6}a{color:#bbee8d}button{padding:12px 20px;margin:8px 8px 8px 0;cursor:pointer;'
          'border:0;border-radius:6px;background:#2c3a4f;color:#fff;font-size:15px}button.primary{background:#5d9b2f}'
          '.notes{background:#1d2430;border:1px solid #2f3b4d;border-radius:8px;padding:16px 20px;white-space:pre-wrap}'
          '.muted{color:#9aa6b8}')


def attach(app, desktop_token: str):
    updater.cleanup_previous()

    @app.get('/__desktop__/updates')
    async def desktop_check(request: Request):
        if not secrets.compare_digest(request.headers.get('X-StoryToon-Desktop', ''), desktop_token):
            return JSONResponse({'error': 'Forbidden'}, status_code=403)
        return JSONResponse(await asyncio.to_thread(updater.check_release), headers={'Cache-Control': 'no-store'})

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

    def form(buttons: str) -> str:
        return f'<form method="post"><input type="hidden" name="csrf" value="{{csrf}}">{buttons}</form>'

    def status_body(result: dict) -> str:
        if result['error']:
            return f'<p>{html.escape(result["error"])}</p>' + form('<button name="action" value="check">Kiểm tra lại</button>')
        if not result['available']:
            return '<p>StoryToon đã ở phiên bản mới nhất.</p>' + form(
                '<button name="action" value="check">Kiểm tra lại</button>')
        version = html.escape(result['version'])
        notes = html.escape(result['notes'] or 'Cải thiện và sửa lỗi.')
        return (f'<h2>Có bản mới {version}</h2><h3>Nội dung thay đổi</h3><div class="notes">{notes}</div>'
                '<p class="muted">Bản cập nhật thay mã ứng dụng và kho assets. Dự án, cấu hình và tài khoản được giữ nguyên.</p>'
                + form(f'<input type="hidden" name="version" value="{version}">'
                       '<button class="primary" name="action" value="install">Cập nhật ngay</button>'))

    @app.get('/updates')
    async def show():
        return page(status_body(await asyncio.to_thread(updater.check_release)))

    @app.post('/updates')
    async def change(request: Request):
        body = await request.body()
        if len(body) > 4096:
            return HTMLResponse('Yêu cầu quá dài.', status_code=400)
        data = parse_qs(body.decode('utf-8', errors='replace'))
        get = lambda key: data.get(key, [''])[0]
        csrf = request.cookies.get('storytoon_update_csrf', '')
        if not csrf or not secrets.compare_digest(csrf, get('csrf')):
            return HTMLResponse('Phiên xác nhận không hợp lệ.', status_code=403)
        if get('action') == 'install':
            result = await asyncio.to_thread(updater.check_release)
            if not result['available'] or result['version'] != get('version'):
                return page(status_body(result))
            try:
                done = await asyncio.to_thread(updater.download_and_install, result['version'])
            except (OSError, ValueError, KeyError) as exc:
                return page(f'<p>Cập nhật chưa hoàn tất: {html.escape(str(exc))}</p>'
                            '<p>Ứng dụng vẫn dùng được; hãy thử lại sau.</p>'
                            + form('<button name="action" value="check">Thử lại</button>'))
            return page(f'<h2>Đã cập nhật lên {html.escape(done["version"])}</h2>'
                        '<p><b>Hãy đóng StoryToon và mở lại</b> để dùng bản mới.</p>')
        return page(status_body(await asyncio.to_thread(updater.check_release)))

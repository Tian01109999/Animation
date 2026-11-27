"""Public assets update information inside the authenticated desktop app."""
import asyncio
import html
import secrets
from urllib.parse import parse_qs

from fastapi import Request
from starlette.responses import HTMLResponse, JSONResponse

from . import updater


def attach(app, desktop_token: str):
    @app.get('/__desktop__/updates')
    async def desktop_check(request: Request):
        if not secrets.compare_digest(request.headers.get('X-StoryToon-Desktop', ''), desktop_token):
            return JSONResponse({'error': 'Forbidden'}, status_code=403)
        return JSONResponse(await asyncio.to_thread(updater.check_release), headers={'Cache-Control': 'no-store'})

    def page(message=''):
        csrf = secrets.token_urlsafe(32)
        response = HTMLResponse('''<!doctype html><html lang="vi"><meta charset="utf-8">
<title>Cập nhật StoryToon</title><style>body{background:#141922;color:#edf0f5;font:16px "Segoe UI",sans-serif;max-width:720px;margin:60px auto;padding:24px;line-height:1.6}a{color:#bbee8d}input,button{padding:12px;margin:8px 0}input[type=password]{width:95%;background:#202835;color:white;border:1px solid #536176}button{cursor:pointer}</style>
<h1>Cập nhật assets</h1><p>Phiên bản app: ''' + html.escape(updater.__version__) + ''' · Kho assets: ''' + html.escape(updater.assets_version()) + '''</p>
<p>Kho tải công khai: <a href="https://github.com/''' + updater.REPOSITORY + '''/releases">''' + updater.REPOSITORY + '''</a>. Không cần token hoặc tài khoản GitHub để cập nhật.</p>
<p>App tự kiểm tra kho assets lúc mở và mỗi 4 giờ. Khi có assets mới, cửa sổ thông báo tự hiện và bạn có thể mở trang tải. Đóng app, giải nén ZIP vào thư mục chứa EXE và đồng ý ghi đè các file trùng trong assets, rồi mở lại. Không cần tải lại ứng dụng hoặc runtime.</p>
<p>Gói chỉ bổ sung hoặc thay thế file trong assets. File riêng không trùng tên được giữ lại; dự án và cấu hình không nằm trong gói. Sao lưu kho hiện tại trước khi giải nén nếu bạn đã sửa các asset có sẵn.</p>
<p>''' + message + '''</p><form method="post"><input type="hidden" name="csrf" value="''' + csrf + '''">
<button name="action" value="check">Kiểm tra ngay</button></form><p><a href="/">Quay lại StoryToon</a></p></html>''')
        response.set_cookie('storytoon_update_csrf', csrf, httponly=True, samesite='strict', max_age=600)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.get('/updates')
    def settings():
        return page()

    @app.post('/updates')
    async def change(request: Request):
        body = await request.body()
        if len(body) > 4096:
            return HTMLResponse('Yêu cầu quá dài.', status_code=400)
        form = parse_qs(body.decode('utf-8', errors='replace'))
        get = lambda key: form.get(key, [''])[0]
        csrf = request.cookies.get('storytoon_update_csrf', '')
        if not csrf or not secrets.compare_digest(csrf, get('csrf')):
            return HTMLResponse('Phiên xác nhận không hợp lệ.', status_code=403)
        try:
            result = await asyncio.to_thread(updater.check_release)
            if result['error']:
                return page(html.escape(result['error']))
            if result['available']:
                return page('Có assets mới ' + html.escape(result['version']) + ': <a href="' + html.escape(result['url'], quote=True) + '">Tải gói assets</a>')
            return page('Kho assets đã ở phiên bản mới nhất.')
        except (OSError, ValueError):
            return page('Không kiểm tra được cập nhật. Vui lòng thử lại sau.')

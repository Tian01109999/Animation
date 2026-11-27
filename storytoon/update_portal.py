"""Authenticated update settings. Credentials never appear in HTML or responses."""
import asyncio
import html
import secrets
from urllib.parse import parse_qs

from fastapi import Request
from starlette.responses import HTMLResponse, JSONResponse

from . import updater, secure_store


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
<p>Repository riêng tư: <a href="https://github.com/''' + updater.REPOSITORY + '''/releases">''' + updater.REPOSITORY + '''</a>.</p>
<p>App kiểm tra kho assets lúc mở và mỗi 4 giờ. Khi có assets mới, tải file StoryToon-Assets trên trang phát hành. Đóng app, giải nén ZIP vào thư mục chứa EXE và đồng ý ghi đè các file trùng trong assets, rồi mở lại. Không cần tải lại ứng dụng hoặc runtime.</p>
<p>Gói chỉ bổ sung hoặc thay thế file trong assets. File riêng không trùng tên được giữ lại; dự án và cấu hình không nằm trong gói. Sao lưu kho hiện tại trước khi giải nén nếu bạn đã sửa các asset có sẵn.</p>
<p>Để đọc bản phát hành private, tạo fine-grained GitHub token với quyền <b>Contents: Read-only</b> cho repository này. Tài khoản GitHub phải được cấp quyền vào repository. Token được mã hóa bằng Windows DPAPI trên máy này, độc lập với tài khoản đăng nhập 24Media.</p>
<p>''' + message + '''</p><form method="post"><input type="hidden" name="csrf" value="''' + csrf + '''">
<input type="password" name="token" autocomplete="off" placeholder="GitHub token (chỉ nhập khi muốn lưu hoặc thay đổi)">
<button name="action" value="save">Lưu token</button> <button name="action" value="check">Kiểm tra ngay</button>
<button name="action" value="remove">Xóa token trên máy</button></form><p><a href="/">Quay lại StoryToon</a></p></html>''')
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
            if get('action') == 'remove':
                secure_store.remove(updater.STORE)
                return page('Đã xóa GitHub token trên máy này.')
            if get('action') == 'save':
                updater.save_token(get('token'))
            result = await asyncio.to_thread(updater.check_release)
            if result['error']:
                return page(html.escape(result['error']))
            if result['available']:
                return page('Có assets mới ' + html.escape(result['version']) + ': <a href="' + html.escape(result['url'], quote=True) + '">Tải gói assets</a>')
            return page('Kho assets đã ở phiên bản mới nhất.')
        except (OSError, ValueError):
            return page('Không lưu được GitHub token. Kiểm tra giá trị và quyền lưu trên Windows.')

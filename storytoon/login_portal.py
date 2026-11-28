"""24Media login gate for the desktop UI, file routes and Gradio APIs."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import html
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import parse_qs

from fastapi import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import auth_24media as auth, secure_store

COOKIE = 'storytoon_24media'
STORE = '24media-session.dat'
MAX_AGE = 30 * 24 * 3600


@dataclass
class Entry:
    session: auth.AuthSession
    checked: float
    expires: float
    remember: bool


class LoginPortal:
    def __init__(self):
        self.config = auth.FirebaseConfig.load(Path(__file__).resolve().parent)
        self.sessions: dict[str, Entry] = {}
        self.lock = threading.RLock()
        self.failures: list[float] = []

    def _persist(self, sid: str, entry: Entry):
        secure_store.write(STORE, {'sid': sid, 'project': self.config.project_id,
                                   'expires': entry.expires, 'session': asdict(entry.session)})

    def login(self, email: str, password: str, remember: bool) -> str:
        with self.lock:
            now = time.time()
            self.failures = [t for t in self.failures if now-t < 60]
            if len(self.failures) >= 5:
                raise auth.AuthError('Đăng nhập quá nhiều lần. Vui lòng đợi một phút.')
            try:
                session = auth.sign_in(self.config, email.strip(), password)
            except auth.AuthError:
                self.failures.append(now)
                raise
            sid = secrets.token_urlsafe(32)
            entry = Entry(session, now, now+MAX_AGE if remember else now+86400, remember)
            if remember:
                self._persist(sid, entry)
            else:
                secure_store.remove(STORE)
            self.sessions.clear()
            self.sessions[sid] = entry
            self.failures.clear()
            return sid

    def validate(self, sid: str | None) -> auth.AuthSession | None:
        if not sid or len(sid) > 128:
            return None
        with self.lock:
            entry = self.sessions.get(sid)
            if entry is None:
                try:
                    saved = secure_store.read(STORE)
                    if (saved.get('project') != self.config.project_id or
                        not secrets.compare_digest(str(saved.get('sid','')),sid) or
                        float(saved.get('expires',0)) <= time.time()):
                        return None
                    entry = Entry(auth.AuthSession(**saved['session']), 0, float(saved['expires']), True)
                except (OSError, ValueError, TypeError, KeyError):
                    return None
            if entry.expires <= time.time():
                self.logout(sid)
                return None
            if time.time()-entry.checked >= 300:
                try:
                    entry.session = auth.refresh_access(self.config,entry.session)
                except auth.AccessDenied:
                    self.logout(sid)
                    raise
                entry.checked = time.time()
                if entry.remember:
                    self._persist(sid,entry)
            self.sessions[sid] = entry
            return entry.session

    def logout(self, sid: str):
        with self.lock:
            self.sessions.pop(sid,None)
            try:
                saved=secure_store.read(STORE)
                if secrets.compare_digest(str(saved.get('sid','')),sid):
                    secure_store.remove(STORE)
            except (OSError,ValueError):
                secure_store.remove(STORE)


def login_page(message: str = '', status: int = 200) -> HTMLResponse:
    csrf=secrets.token_urlsafe(32)
    response=HTMLResponse('''<!doctype html><html lang="vi"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Đăng nhập 24Media · StoryToon</title>
<style>body{margin:0;background:#141922;color:#edf0f5;font:16px "Segoe UI",sans-serif;display:grid;min-height:100vh;place-items:center}
main{width:min(420px,85vw);padding:36px;background:#202835;border:1px solid #3b4759;border-radius:18px}
h1{font-size:26px}p{color:#bcc7d6;line-height:1.6}label{display:block;margin-top:18px}input[type=email],input[type=password]{box-sizing:border-box;width:100%;padding:12px;border:1px solid #536176;border-radius:8px;background:#141922;color:white;font:inherit;margin-top:8px}
button{width:100%;margin-top:22px;border:0;border-radius:8px;padding:13px;background:#bbee8d;color:#182319;font-size:16px;font-weight:600;cursor:pointer}.error{color:#ffb3a9}</style>
<main data-storytoon-login><h1>Đăng nhập 24Media</h1><p>Dùng tài khoản email và mật khẩu đã được cấp trong 24Media Account Manager để mở StoryToon.</p>
<p class="error">''' + html.escape(message) + '''</p><form method="post" action="/account/login">
<input type="hidden" name="csrf" value="''' + csrf + '''">
<label>Email<input type="email" name="email" autocomplete="username" required maxlength="254"></label>
<label>Mật khẩu<input type="password" name="password" autocomplete="current-password" required maxlength="1024"></label>
<label><input type="checkbox" name="remember" value="yes" checked> Ghi nhớ đăng nhập trên máy này</label>
<button type="submit">Đăng nhập</button></form><p>Tài khoản cần được cấp quyền và liên kết đúng PC. Liên hệ quản trị viên nếu chưa có tài khoản.</p></main></html>''',status_code=status)
    response.set_cookie('storytoon_csrf',csrf,httponly=True,samesite='strict',max_age=600)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Frame-Options']='DENY'
    return response


def attach(app, portal: LoginPortal):
    @app.middleware('http')
    async def gate(request: Request, call_next):
        if request.url.path in ('/account/login','/__desktop__/status','/__desktop__/updates','/__desktop__/update-state'):
            return await call_next(request)
        try:
            session=await asyncio.to_thread(portal.validate,request.cookies.get(COOKIE))
        except auth.AuthError as exc:
            return login_page(str(exc),401) if 'text/html' in request.headers.get('accept','') else JSONResponse({'error':str(exc)},status_code=401)
        if session is None:
            if request.url.path=='/' or 'text/html' in request.headers.get('accept',''):
                return RedirectResponse('/account/login',status_code=303)
            return JSONResponse({'error':'Vui lòng đăng nhập 24Media.'},status_code=401)
        request.state.account=session.email
        return await call_next(request)

    @app.get('/account/login')
    def show_login():
        return login_page()

    @app.post('/account/login')
    async def sign_in(request: Request):
        body=await request.body()
        if len(body)>8192:
            return login_page('Yêu cầu đăng nhập quá dài.',400)
        form=parse_qs(body.decode('utf-8',errors='replace'))
        value=lambda key: form.get(key,[''])[0]
        csrf=request.cookies.get('storytoon_csrf','')
        if not csrf or not secrets.compare_digest(csrf,value('csrf')):
            return login_page('Phiên đăng nhập đã hết hạn. Hãy thử lại.',403)
        try:
            sid=await asyncio.to_thread(portal.login,value('email'),value('password'),value('remember')=='yes')
        except auth.AuthError as exc:
            return login_page(str(exc),401)
        except OSError:
            return login_page('Không lưu được phiên đăng nhập trên Windows.',500)
        response=RedirectResponse('/',status_code=303)
        response.set_cookie(COOKIE,sid,httponly=True,samesite='strict',max_age=MAX_AGE if value('remember')=='yes' else None)
        response.delete_cookie('storytoon_csrf')
        return response

    @app.get('/account')
    def account_page(request: Request):
        csrf=secrets.token_urlsafe(32)
        response=HTMLResponse('<meta charset="utf-8"><h2>Tài khoản 24Media</h2><p>'+html.escape(request.state.account)+
            '</p><form method="post" action="/account/logout"><input type="hidden" name="csrf" value="'+csrf+
            '"><button>Đăng xuất 24Media</button></form><p><a href="/">Quay lại StoryToon</a></p>')
        response.set_cookie('storytoon_csrf',csrf,httponly=True,samesite='strict',max_age=600)
        response.headers['Cache-Control']='no-store'
        return response

    @app.post('/account/logout')
    async def sign_out(request: Request):
        from . import activity
        if activity.busy():
            return HTMLResponse('Đợi tác vụ đang chạy hoàn tất trước khi đăng xuất.',status_code=409)
        form=parse_qs((await request.body()).decode('utf-8',errors='replace'))
        csrf=request.cookies.get('storytoon_csrf','')
        if not csrf or not secrets.compare_digest(csrf,form.get('csrf',[''])[0]):
            return JSONResponse({'error':'Phiên xác nhận không hợp lệ.'},status_code=403)
        await asyncio.to_thread(portal.logout,request.cookies.get(COOKIE,''))
        response=RedirectResponse('/account/login',status_code=303)
        response.delete_cookie(COOKIE)
        return response

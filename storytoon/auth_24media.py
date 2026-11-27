"""Firebase email/password sign-in and owner-controlled app access checks."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class AuthError(Exception):
    """A login error safe to show to the user."""


class AccessDenied(AuthError):
    """The owner has not granted this account access."""


class NetworkUnavailable(AuthError):
    """The entitlement service could not be reached."""


class _DeviceBindingMissing(Exception):
    """The account has not been bound to a PC yet."""


class _DeviceBindingRace(Exception):
    """Another PC created the account's binding first."""


@dataclass(frozen=True)
class FirebaseConfig:
    project_id: str
    api_key: str

    @classmethod
    def load(cls, bundle_dir: Path) -> "FirebaseConfig":
        path = bundle_dir / "firebase_auth.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise AuthError("Ứng dụng chưa được cấu hình đăng nhập. Hãy liên hệ quản trị viên.") from exc
        project_id = value.get("project_id") if isinstance(value, dict) else None
        api_key = value.get("api_key") if isinstance(value, dict) else None
        if not isinstance(project_id, str) or not project_id.strip() or not isinstance(api_key, str) or not api_key.strip():
            raise AuthError("Cấu hình đăng nhập chưa đầy đủ. Hãy liên hệ quản trị viên.")
        return cls(project_id.strip(), api_key.strip())


@dataclass(frozen=True)
class AuthSession:
    uid: str
    email: str
    id_token: str
    refresh_token: str


def _request_json(
    url: str,
    *,
    body: dict[str, Any] | None = None,
    form: dict[str, str] | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    elif form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urlencode(form).encode("ascii")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=data, headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            result = json.load(response)
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read(65536).decode("utf-8"))
            code = detail.get("error", {}).get("message", "")
        except (UnicodeDecodeError, ValueError, AttributeError):
            code = ""
        if "firestore.googleapis.com" in url and "/documents/app_devices" in url:
            if exc.code == 404:
                raise _DeviceBindingMissing from exc
            if exc.code == 409:
                raise _DeviceBindingRace from exc
            if exc.code == 403:
                raise AuthError(
                    "Firebase chưa bật giới hạn một PC. Hãy publish firestore.rules mới trước khi đăng nhập."
                ) from exc
        if exc.code in (403, 404) and "firestore.googleapis.com" in url:
            raise AccessDenied("Tài khoản chưa được cấp quyền truy cập hoặc đã bị khóa.") from exc
        if code in {"EMAIL_NOT_FOUND", "INVALID_PASSWORD", "INVALID_LOGIN_CREDENTIALS", "MISSING_PASSWORD"}:
            raise AuthError("Email hoặc mật khẩu không đúng.") from exc
        if code in {"USER_DISABLED", "USER_NOT_FOUND", "TOKEN_EXPIRED", "INVALID_REFRESH_TOKEN"}:
            raise AccessDenied("Tài khoản đã bị khóa hoặc thu hồi. Hãy liên hệ quản trị viên.") from exc
        if code == "TOO_MANY_ATTEMPTS_TRY_LATER":
            raise AuthError("Đăng nhập quá nhiều lần. Vui lòng thử lại sau.") from exc
        if exc.code >= 500:
            raise NetworkUnavailable("Dịch vụ đăng nhập đang gián đoạn. Vui lòng thử lại sau.") from exc
        raise AuthError("Không thể xác minh tài khoản. Vui lòng thử lại sau.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise NetworkUnavailable("Không kết nối được dịch vụ đăng nhập. Hãy kiểm tra Internet.") from exc
    if not isinstance(result, dict):
        raise AuthError("Dịch vụ đăng nhập trả về dữ liệu không hợp lệ.")
    return result


def _windows_device_hash() -> str:
    """Hash Windows' stable machine identifier; never send the raw registry value."""
    if os.name != "nt":
        raise AuthError("Giới hạn đăng nhập này chỉ hỗ trợ Windows.")
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
    except (ImportError, OSError) as exc:
        raise AuthError("Không xác định được PC này. Hãy liên hệ quản trị viên.") from exc
    if not isinstance(machine_guid, str) or not machine_guid.strip():
        raise AuthError("Không xác định được PC này. Hãy liên hệ quản trị viên.")
    value = "24media-srt-device-v1:" + machine_guid.strip().casefold()
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def check_device_binding(config: FirebaseConfig, uid: str, token: str) -> None:
    project = quote(config.project_id, safe="")
    documents = f"https://firestore.googleapis.com/v1/projects/{project}/databases/(default)/documents"
    device_url = documents + "/app_devices/" + quote(uid, safe="")
    device_hash = _windows_device_hash()

    def read_binding() -> str:
        document = _request_json(device_url, token=token)
        value = document.get("fields", {}).get("device_hash", {}).get("stringValue")
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise AccessDenied("Bản ghi PC của tài khoản không hợp lệ. Hãy liên hệ quản trị viên.")
        return value

    try:
        registered_hash = read_binding()
    except _DeviceBindingMissing:
        create_url = documents + "/app_devices?" + urlencode({"documentId": uid})
        body = {"fields": {"device_hash": {"stringValue": device_hash}}}
        try:
            _request_json(create_url, body=body, token=token)
            return
        except _DeviceBindingRace:
            # Concurrent first logins are resolved by Firestore: the first
            # create wins, and later requests must match that stored binding.
            registered_hash = read_binding()

    if registered_hash != device_hash:
        raise AccessDenied(
            "Tài khoản này đã được liên kết với một PC khác. Hãy liên hệ quản trị viên để chuyển PC."
        )


def sign_in(config: FirebaseConfig, email: str, password: str) -> AuthSession:
    endpoint = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=" + quote(config.api_key)
    result = _request_json(endpoint, body={"email": email, "password": password, "returnSecureToken": True})
    uid = result.get("localId")
    token = result.get("idToken")
    refresh_token = result.get("refreshToken")
    if not all(isinstance(value, str) and value for value in (uid, token, refresh_token)):
        raise AuthError("Dịch vụ đăng nhập trả về dữ liệu không hợp lệ.")
    check_access(config, uid, token)
    return AuthSession(uid=uid, email=str(result.get("email") or email), id_token=token, refresh_token=refresh_token)


def check_access(config: FirebaseConfig, uid: str, token: str) -> None:
    doc_url = (
        "https://firestore.googleapis.com/v1/projects/"
        + quote(config.project_id, safe="")
        + "/databases/(default)/documents/app_access/"
        + quote(uid, safe="")
    )
    document = _request_json(doc_url, token=token)
    if document.get("fields", {}).get("enabled", {}).get("booleanValue") is not True:
        raise AccessDenied("Tài khoản chưa được cấp quyền truy cập hoặc đã bị khóa.")
    check_device_binding(config, uid, token)


def refresh_access(config: FirebaseConfig, session: AuthSession) -> AuthSession:
    endpoint = "https://securetoken.googleapis.com/v1/token?key=" + quote(config.api_key)
    result = _request_json(endpoint, form={"grant_type": "refresh_token", "refresh_token": session.refresh_token})
    uid = result.get("user_id")
    token = result.get("id_token")
    refresh_token = result.get("refresh_token")
    if uid != session.uid or not isinstance(token, str) or not token or not isinstance(refresh_token, str) or not refresh_token:
        raise AccessDenied("Phiên đăng nhập không còn hợp lệ.")
    check_access(config, uid, token)
    return AuthSession(uid=uid, email=session.email, id_token=token, refresh_token=refresh_token)

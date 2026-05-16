from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Flask, session
from flask_login import LoginManager, login_user


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from classroom_app.core.auth import AdminUser
from config import Config


DEFAULT_BASE_URL = "http://127.0.0.1:5000"
EXPECTED_DEFAULT_MODE = "image"
EXPECTED_STUDENT_MODEL = "behavior.pt"
EXPECTED_TEACHER_MODEL = "head.pt"


def load_admin_username(root: Path = ROOT) -> str:
    admin_config_path = root / "data" / "admin_config.json"
    payload = json.loads(admin_config_path.read_text(encoding="utf-8"))
    username = str(payload.get("username") or "").strip()
    if not username:
        raise RuntimeError(f"Admin username is missing in {admin_config_path}")
    return username


def build_authenticated_cookie(username: str | None = None) -> tuple[str, str]:
    resolved_username = username or load_admin_username()
    app = Flask(__name__)
    app.secret_key = Config.SECRET_KEY
    app.config["SESSION_COOKIE_NAME"] = Config.SESSION_COOKIE_NAME
    LoginManager(app)
    with app.test_request_context("/"):
        login_user(AdminUser(resolved_username))
        serializer = app.session_interface.get_signing_serializer(app)
        if serializer is None:
            raise RuntimeError("Failed to create Flask session serializer")
        return app.config["SESSION_COOKIE_NAME"], serializer.dumps(dict(session))


def open_authenticated_session(base_url: str = DEFAULT_BASE_URL, username: str | None = None) -> requests.Session:
    parsed = urlparse(base_url)
    hostname = parsed.hostname or "127.0.0.1"
    cookie_name, cookie_value = build_authenticated_cookie(username=username)
    session_client = requests.Session()
    session_client.cookies.set(cookie_name, cookie_value, domain=hostname, path="/")
    session_client.headers.update({"User-Agent": "demo-runtime-contract/1.0"})
    return session_client


def _api_request(session_client: requests.Session, base_url: str, path: str, timeout: float = 30) -> dict:
    response = session_client.get(f"{base_url}{path}", timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        error = payload.get("error") or {}
        raise RuntimeError(f"{path} failed: [{error.get('code')}] {error.get('message')}")
    return payload.get("data") or {}


def read_demo_entry_contract(base_url: str = DEFAULT_BASE_URL) -> dict:
    with open_authenticated_session(base_url=base_url) as session_client:
        settings = _api_request(session_client, base_url, "/api/user/settings")
        models = _api_request(session_client, base_url, "/api/models/info")
    return {
        "default_mode": settings.get("settings", {}).get("default_mode"),
        "student": models.get("student") or {},
        "teacher": models.get("teacher") or {},
    }


def evaluate_demo_entry_contract(snapshot: dict) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if snapshot.get("default_mode") != EXPECTED_DEFAULT_MODE:
        issues.append(f"default_mode={snapshot.get('default_mode')!r} (expected {EXPECTED_DEFAULT_MODE!r})")

    for role, expected_model in (
        ("student", EXPECTED_STUDENT_MODEL),
        ("teacher", EXPECTED_TEACHER_MODEL),
    ):
        info = snapshot.get(role) or {}
        if info.get("selection_source") != "env_default":
            issues.append(f"{role}.selection_source={info.get('selection_source')!r} (expected 'env_default')")
        if bool(info.get("selection_locked")):
            issues.append(f"{role}.selection_locked={info.get('selection_locked')!r} (expected False)")
        if info.get("selection_relative_path") != expected_model:
            issues.append(
                f"{role}.selection_relative_path={info.get('selection_relative_path')!r} "
                f"(expected {expected_model!r})"
            )
    return not issues, issues


def inspect_demo_entry_contract(base_url: str = DEFAULT_BASE_URL) -> dict:
    try:
        snapshot = read_demo_entry_contract(base_url=base_url)
    except Exception as exc:
        return {
            "ok": False,
            "issues": [f"runtime contract probe failed: {exc}"],
            "snapshot": None,
        }
    ok, issues = evaluate_demo_entry_contract(snapshot)
    return {
        "ok": ok,
        "issues": issues,
        "snapshot": snapshot,
    }

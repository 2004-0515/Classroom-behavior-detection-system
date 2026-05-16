from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from isolated_env import create_and_apply_isolated_runtime


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Smoke-check the main pages and critical DOM presence without mutating real app state.
def configure_temp_environment(with_admin: bool):
    runtime, _ = create_and_apply_isolated_runtime(
        "ui-smoke",
        admin_username="ui_admin" if with_admin else None,
        admin_password="ui_password_123" if with_admin else None,
        model_folder=ROOT / "models",
    )
    return runtime.root


def assert_contains(text: str, needles: list[str], label: str):
    for needle in needles:
        if needle not in text:
            raise AssertionError(f"{label} missing marker: {needle}")


def assert_regex(text: str, patterns: list[str], label: str):
    import re

    for pattern in patterns:
        if not re.search(pattern, text):
            raise AssertionError(f"{label} missing pattern: {pattern}")


def run_login_setup_smoke():
    temp_root = configure_temp_environment(with_admin=False)
    try:
        from classroom_app import create_app

        app = create_app()
        with app.test_client() as client:
            response = client.get("/login")
            html = response.get_data().decode("utf-8", errors="replace")
            if response.status_code != 200:
                raise AssertionError(f"GET /login expected 200, got {response.status_code}")
            assert_contains(
                html,
                [
                    "<form method=\"POST\" class=\"login-form\">",
                    "inline-error",
                    "scripts/init_local_admin.py",
                ],
                "login_setup_page",
            )
        return "login_setup_page: True"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def run_dashboard_smoke():
    temp_root = configure_temp_environment(with_admin=True)
    try:
        from classroom_app import create_app

        app = create_app()
        with app.test_client() as client:
            unauth = client.get("/", follow_redirects=False)
            if unauth.status_code not in {302, 401}:
                raise AssertionError(f"GET / unauth expected redirect/auth failure, got {unauth.status_code}")

            login = client.post("/api/auth/login", json={"username": "ui_admin", "password": "ui_password_123"})
            if login.status_code != 200:
                raise AssertionError(f"login api expected 200, got {login.status_code}")

            response = client.get("/")
            html = response.get_data().decode("utf-8", errors="replace")
            if response.status_code != 200:
                raise AssertionError(f"GET / expected 200, got {response.status_code}")
            assert_contains(
                html,
                [
                    'id="app"',
                    'id="logoutBtn"',
                    'id="settingsBtn"',
                    'data-mode="image"',
                    'data-mode="batch"',
                    'data-mode="video"',
                    'data-mode="webcam"',
                    'id="webcamControls"',
                    'id="webcamDiagnostics"',
                    'id="probeWebcamBtn"',
                    'id="startWebcamBtn"',
                    'id="stopWebcamBtn"',
                    'id="dropzone"',
                    'id="stopTaskBtn"',
                    'id="randomCallBtn"',
                    'id="openDetailBtn"',
                    'id="detailModal"',
                    'id="modelLibraryModal"',
                    'id="settingsModal"',
                    'id="historyExportSelectedBtn"',
                    'id="historySelectionMeta"',
                ],
                "dashboard_page",
            )
            assert_regex(
                html,
                [
                    r'src="/static/app/main\.js(?:\?v=[^"]+)?"',
                    r'href="/static/css/app\.css(?:\?v=[^"]+)?"',
                ],
                "dashboard_page",
            )

            session = client.get("/api/auth/session")
            session_payload = session.get_json()["data"]
            if not session_payload.get("authenticated"):
                raise AssertionError("session api should report authenticated after login")
        return "dashboard_page: True"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main():
    results = [run_login_setup_smoke(), run_dashboard_smoke()]
    print("UI 烟测结果:")
    for line in results:
        print(f"- {line}")


if __name__ == "__main__":
    main()

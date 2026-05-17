from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from isolated_env import create_and_apply_isolated_runtime


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Contract smoke only: exercise login/session and key interaction toggles without claiming full browser UX coverage.
def configure_temp_environment():
    runtime, _ = create_and_apply_isolated_runtime(
        "interaction-smoke",
        admin_username="interaction_admin",
        admin_password="interaction_password_123",
        model_folder=ROOT / "models",
    )
    return runtime.root


def assert_contains(text: str, needles: list[str], label: str):
    for needle in needles:
        if needle not in text:
            raise AssertionError(f"{label} missing marker: {needle}")


def verify_auth_flow():
    temp_root = configure_temp_environment()
    try:
        from classroom_app import create_app

        app = create_app()
        with app.test_client() as client:
            session_before = client.get("/api/auth/session")
            if session_before.get_json()["data"].get("authenticated"):
                raise AssertionError("session should be anonymous before login")

            login = client.post(
                "/api/auth/login",
                json={"username": "interaction_admin", "password": "interaction_password_123"},
            )
            if login.status_code != 200:
                raise AssertionError(f"login api expected 200, got {login.status_code}")

            session_after_login = client.get("/api/auth/session").get_json()["data"]
            if not session_after_login.get("authenticated"):
                raise AssertionError("session should be authenticated after login")

            logout = client.post("/api/auth/logout")
            if logout.status_code != 200:
                raise AssertionError(f"logout api expected 200, got {logout.status_code}")

            session_after_logout = client.get("/api/auth/session").get_json()["data"]
            if session_after_logout.get("authenticated"):
                raise AssertionError("session should be anonymous after logout")
        return "auth_flow: True"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def verify_frontend_contracts():
    main_js = (ROOT / "static" / "app" / "main.js").read_text(encoding="utf-8")
    store_js = (ROOT / "static" / "app" / "store.js").read_text(encoding="utf-8")

    assert_contains(
        main_js,
        [
            'image: {',
            'title: "单图检测工作台"',
            'batch: {',
            'title: "批量图片检测工作台"',
            'video: {',
            'title: "视频检测工作台"',
            'webcam: {',
            'title: "实时巡检工作台"',
            'const VALID_MODES = new Set(["image", "batch", "video", "webcam"])',
            'function getInitialMode(defaultMode)',
            'new URLSearchParams(window.location.search).get("audit_mode")',
            'els.pickFileBtn.classList.toggle("hidden", mode === "webcam")',
            'els.webcamControls.classList.toggle("hidden", mode !== "webcam")',
            'els.runBtn.classList.toggle("hidden", mode === "webcam")',
            'async function stopCurrentVideoTask()',
            'async function openDetailViewer()',
            'async function randomCallCurrentFrame()',
            'async function saveSettings()',
            'function openCurrentModelDialog()',
            'selection_locked',
            '模型已由当前启动入口固定',
            'async function startBrowserWebcamFallback(reason = "")',
            'async function stopBrowserWebcamFallback()',
            'await request("/api/auth/logout", { method: "POST" })',
            'window.location.href = "/login"',
            'els.historyExportSelectedBtn.disabled = totalSelected === 0 || exporting',
            'els.historyExportSelectedBtn.textContent = exporting ? "正在导出..." : "导出选中报告"',
            'window.open(response.data.zip_url, "_blank", "noopener")',
        ],
        "main_js_contract",
    )
    assert_contains(
        store_js,
        [
            'selectedHistoryIds: []',
            'exportingHistoryReports: false',
            'notifications: []',
        ],
        "store_js_contract",
    )
    return "frontend_contracts: True"


def verify_demo_model_entry_contract():
    temp_root = configure_temp_environment()
    student_env = str(ROOT / "models" / "behavior.pt")
    teacher_env = str(ROOT / "models" / "head.pt")
    previous_student = os.environ.get("STUDENT_MODEL_PATH")
    previous_teacher = os.environ.get("TEACHER_MODEL_PATH")
    try:
        os.environ["STUDENT_MODEL_PATH"] = student_env
        os.environ["TEACHER_MODEL_PATH"] = teacher_env

        from classroom_app import create_app

        app = create_app()
        with app.test_client() as client:
            login = client.post(
                "/api/auth/login",
                json={"username": "interaction_admin", "password": "interaction_password_123"},
            )
            if login.status_code != 200:
                raise AssertionError(f"login api expected 200, got {login.status_code}")

            info = client.get("/api/models/info")
            if info.status_code != 200:
                raise AssertionError(f"models info expected 200, got {info.status_code}")
            info_payload = info.get_json()["data"]
            student_info = info_payload.get("student") or {}
            teacher_info = info_payload.get("teacher") or {}
            if student_info.get("selection_source") != "env_default" or student_info.get("selection_locked"):
                raise AssertionError(f"student model should be startup-default and unlocked, got: {student_info}")
            if teacher_info.get("selection_source") != "env_default" or teacher_info.get("selection_locked"):
                raise AssertionError(f"teacher model should be startup-default and unlocked, got: {teacher_info}")

            load = client.post(
                "/api/models/load",
                json={"type": "student", "model": "behavior02.pt"},
            )
            if load.status_code != 200:
                raise AssertionError(f"demo model switch expected 200, got {load.status_code}")
            switched = client.get("/api/models/info")
            if switched.status_code != 200:
                raise AssertionError(f"models info after switch expected 200, got {switched.status_code}")
            switched_student = switched.get_json()["data"].get("student") or {}
            if switched_student.get("selection_source") != "manual_selection":
                raise AssertionError(f"student model should become manual_selection after switch, got: {switched_student}")
            if switched_student.get("selection_relative_path") != "behavior02.pt":
                raise AssertionError(f"student model should switch to behavior02.pt, got: {switched_student}")
        return "demo_model_entry_contract: True"
    finally:
        if previous_student is None:
            os.environ.pop("STUDENT_MODEL_PATH", None)
        else:
            os.environ["STUDENT_MODEL_PATH"] = previous_student
        if previous_teacher is None:
            os.environ.pop("TEACHER_MODEL_PATH", None)
        else:
            os.environ["TEACHER_MODEL_PATH"] = previous_teacher
        shutil.rmtree(temp_root, ignore_errors=True)


def verify_demo_default_mode_override():
    temp_root = configure_temp_environment()
    previous_default_mode = os.environ.get("UI_DEFAULT_MODE")
    try:
        os.environ["UI_DEFAULT_MODE"] = "image"

        from classroom_app import create_app

        app = create_app()
        with app.test_client() as client:
            login = client.post(
                "/api/auth/login",
                json={"username": "interaction_admin", "password": "interaction_password_123"},
            )
            if login.status_code != 200:
                raise AssertionError(f"login api expected 200, got {login.status_code}")

            settings = client.post(
                "/api/user/settings",
                json={
                    "default_mode": "batch",
                    "auto_scan_models": False,
                    "show_confidence": False,
                    "show_bbox_labels": False,
                },
            )
            if settings.status_code != 200:
                raise AssertionError(f"user settings expected 200, got {settings.status_code}")

            resolved = client.get("/api/user/settings")
            if resolved.status_code != 200:
                raise AssertionError(f"user settings read expected 200, got {resolved.status_code}")
            payload = resolved.get_json()["data"]["settings"]
            if payload.get("default_mode") != "image":
                raise AssertionError(f"demo default mode override expected image, got: {payload}")
        return "demo_default_mode_override: True"
    finally:
        if previous_default_mode is None:
            os.environ.pop("UI_DEFAULT_MODE", None)
        else:
            os.environ["UI_DEFAULT_MODE"] = previous_default_mode
        shutil.rmtree(temp_root, ignore_errors=True)


def verify_settings_and_detection_contracts():
    temp_root = configure_temp_environment()
    try:
        from classroom_app import create_app

        app = create_app()
        image_path = next((ROOT / "testfile").glob("*.jpg"), None)
        if image_path is None:
            raise RuntimeError("testfile/ 中缺少图片样例")

        with app.test_client() as client:
            login = client.post(
                "/api/auth/login",
                json={"username": "interaction_admin", "password": "interaction_password_123"},
            )
            if login.status_code != 200:
                raise AssertionError(f"login api expected 200, got {login.status_code}")

            settings = client.post(
                "/api/user/settings",
                json={
                    "default_mode": "batch",
                    "auto_scan_models": False,
                    "show_confidence": False,
                    "show_bbox_labels": False,
                },
            )
            if settings.status_code != 200:
                raise AssertionError(f"user settings expected 200, got {settings.status_code}")
            payload = settings.get_json()["data"]["settings"]
            if payload.get("default_mode") != "batch" or payload.get("show_bbox_labels") is not False:
                raise AssertionError("user settings payload mismatch")

            models_info = client.get("/api/user/config/last-models")
            if models_info.status_code != 200:
                raise AssertionError(f"last models expected 200, got {models_info.status_code}")
            last_models = models_info.get_json()["data"]["last_models"]
            for role in ("student", "teacher"):
                ref = last_models.get(role)
                if not ref or ":" in ref or ref.startswith("/"):
                    raise AssertionError(f"{role} model ref should be stored as workspace-relative path, got: {ref}")

            import base64

            frame_payload = client.post(
                "/api/detect/frame",
                json={"image": "data:image/jpeg;base64," + base64.b64encode(image_path.read_bytes()).decode("ascii")},
            )
            if frame_payload.status_code != 200:
                raise AssertionError(f"detect frame expected 200, got {frame_payload.status_code}")

            import io

            detect = client.post(
                "/api/detect/image",
                data={"file": (io.BytesIO(image_path.read_bytes()), image_path.name), "confidence": "0.25", "iou": "0.45"},
                content_type="multipart/form-data",
            )
            if detect.status_code != 200:
                raise AssertionError(f"detect image expected 200, got {detect.status_code}")
            task_id = detect.get_json()["data"]["task_id"]
            detections = client.get(f"/api/tasks/{task_id}/detections?frame_number=0")
            if detections.status_code != 200:
                raise AssertionError(f"task detections expected 200, got {detections.status_code}")
            detections_payload = detections.get_json()["data"]
            if "student_detections" not in detections_payload or "teacher_detections" not in detections_payload:
                raise AssertionError("task detections payload missing keys")
        return "settings_and_detection_contracts: True"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main():
    results = [
        verify_auth_flow(),
        verify_frontend_contracts(),
        verify_demo_model_entry_contract(),
        verify_demo_default_mode_override(),
        verify_settings_and_detection_contracts(),
    ]
    print("交互烟测结果:")
    for line in results:
        print(f"- {line}")


if __name__ == "__main__":
    main()

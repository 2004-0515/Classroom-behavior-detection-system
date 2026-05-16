from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import time
from pathlib import Path

from isolated_env import create_and_apply_isolated_runtime

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


ADMIN_USERNAME = "audit_admin"
ADMIN_PASSWORD = "audit_password_123"


def configure_temp_environment(prefix: str, with_admin: bool = True) -> Path:
    runtime, _ = create_and_apply_isolated_runtime(
        prefix,
        admin_username=ADMIN_USERNAME if with_admin else None,
        admin_password=ADMIN_PASSWORD if with_admin else None,
        model_folder=ROOT / "models",
    )
    return runtime.root


def file_fingerprint(path: Path) -> dict:
    if not path.exists():
        return {"exists": False}
    if path.is_dir():
        return {
            "exists": True,
            "files": sum(1 for item in path.rglob("*") if item.is_file()),
        }
    payload = path.read_bytes()
    return {"exists": True, "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def snapshot_real_state() -> dict:
    return {
        "admin_config": file_fingerprint(ROOT / "data" / "admin_config.json"),
        "user_config": file_fingerprint(ROOT / "data" / "user_config.json"),
        "database": file_fingerprint(ROOT / "data" / "detections.db"),
        "uploads": file_fingerprint(ROOT / "uploads"),
        "outputs": file_fingerprint(ROOT / "outputs"),
    }


def assert_status(response, expected: int, label: str) -> dict:
    actual = response.status_code
    if actual != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, got {actual}")
    return {"label": label, "status": actual}


def assert_error(response, expected_status: int, expected_code: str, label: str) -> dict:
    assert_status(response, expected_status, label)
    payload = response.get_json()
    code = ((payload or {}).get("error") or {}).get("code")
    if code != expected_code:
        raise AssertionError(f"{label}: expected error code {expected_code!r}, got {code!r}")
    return {"label": label, "status": expected_status, "code": code}


def login(client) -> None:
    response = client.post("/api/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert_status(response, 200, "admin login")


def run_setup_and_auth_edges() -> list[dict]:
    temp_root = configure_temp_environment("audit-no-admin", with_admin=False)
    try:
        from classroom_app import create_app

        app = create_app()
        with app.test_client() as client:
            checks = [
                assert_status(client.get("/login"), 200, "login setup page"),
                assert_error(
                    client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}),
                    503,
                    "setup_required",
                    "api login before setup",
                ),
            ]
            response = client.get("/api/dashboard/overview", follow_redirects=False)
            if response.status_code not in {302, 401}:
                raise AssertionError(f"protected dashboard should redirect or reject, got {response.status_code}")
            checks.append({"label": "protected dashboard requires login", "status": response.status_code})
            return checks
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def run_admin_validation_edges() -> list[dict]:
    temp_root = configure_temp_environment("audit-admin-validation", with_admin=False)
    try:
        from classroom_app.services.config_service import ConfigService

        service = ConfigService()
        checks = []
        for username, password, label in [
            ("ab", "strong_password_123", "short admin username rejected"),
            ("valid_admin", "1234567", "short admin password rejected"),
        ]:
            try:
                service.bootstrap_admin(username, password)
            except ValueError:
                checks.append({"label": label, "status": "rejected"})
            else:
                raise AssertionError(f"{label}: expected ValueError")
        return checks
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def run_upload_and_api_edges() -> list[dict]:
    temp_root = configure_temp_environment("audit-api-edges", with_admin=True)
    try:
        from classroom_app import create_app

        app = create_app()
        with app.test_client() as client:
            login(client)
            checks = [
                assert_error(client.post("/api/detect/image", data={}), 400, "missing_file", "image upload requires file"),
                assert_error(
                    client.post("/api/detect/image", data={"file": (io.BytesIO(b"not image"), "bad.txt")}),
                    400,
                    "unsupported_file",
                    "image upload rejects unsupported extension",
                ),
                assert_error(
                    client.post("/api/detect/batch", data={"files": [(io.BytesIO(b"bad"), "bad.txt")]}),
                    400,
                    "unsupported_file",
                    "batch upload rejects unsupported extension",
                ),
                assert_error(
                    client.post("/api/detect/frame", json={}),
                    400,
                    "missing_image",
                    "frame detection requires image payload",
                ),
                assert_error(
                    client.get("/api/tasks/not-a-task"),
                    404,
                    "task_not_found",
                    "missing task detail returns 404",
                ),
                assert_error(
                    client.post("/api/tasks/reports/batch", json={"task_ids": []}),
                    400,
                    "bad_request",
                    "empty batch report selection rejected",
                ),
                assert_error(
                    client.post("/api/streams/webcam/browser-session/stop", json={}),
                    400,
                    "webcam_unready",
                    "browser webcam stop requires task id",
                ),
            ]
            diagnostics = client.get("/api/streams/webcam/diagnostics?camera_index=99")
            assert_status(diagnostics, 200, "webcam diagnostics endpoint")
            payload = diagnostics.get_json()["data"]
            checks.append(
                {
                    "label": "webcam diagnostics returns selected or attempts",
                    "selected": bool(payload.get("selected")),
                    "attempts": len(payload.get("attempts") or []),
                }
            )
            return checks
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def run_sample_effect_audit() -> dict:
    temp_root = configure_temp_environment("audit-sample-effect", with_admin=True)
    sample = ROOT / "testfile" / "0014012.jpg"
    if not sample.exists():
        sample = next((ROOT / "testfile").glob("*.jpg"), None)
    if not sample:
        raise AssertionError("No sample image found under testfile")
    try:
        from classroom_app import create_app

        app = create_app()
        start = time.perf_counter()
        with app.test_client() as client:
            login(client)
            with sample.open("rb") as handle:
                response = client.post("/api/detect/image", data={"file": (handle, sample.name)})
            assert_status(response, 200, "sample image detection")
            task_id = response.get_json()["data"]["task_id"]
            detail = client.get(f"/api/tasks/{task_id}")
            assert_status(detail, 200, "sample image task detail")
            payload = detail.get_json()["data"]
            report = client.get(f"/api/tasks/{task_id}/report")
            assert_status(report, 200, "sample image report generation")
        duration = time.perf_counter() - start
        return {
            "sample": str(sample.relative_to(ROOT)),
            "duration_seconds": round(duration, 2),
            "task_id": task_id,
            "total_detections": payload.get("total_detections"),
            "student_behavior_stats": payload.get("student_behavior_stats"),
            "teacher_behavior_stats": payload.get("teacher_behavior_stats"),
            "average_confidence": payload.get("average_confidence"),
        }
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def run() -> dict:
    before = snapshot_real_state()
    results = {
        "setup_and_auth_edges": run_setup_and_auth_edges(),
        "admin_validation_edges": run_admin_validation_edges(),
        "upload_and_api_edges": run_upload_and_api_edges(),
        "sample_effect_audit": run_sample_effect_audit(),
    }
    after = snapshot_real_state()
    if before != after:
        raise AssertionError("Real data/output state changed during isolated audit")
    results["real_state_unchanged"] = True
    return results


def main() -> int:
    try:
        results = run()
    except Exception as exc:
        print(f"审计失败: {exc}")
        return 1
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("高标准边界审计通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

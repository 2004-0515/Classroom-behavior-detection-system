from __future__ import annotations

import json
import mimetypes
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo_runtime_contract import load_admin_username, open_authenticated_session, read_demo_entry_contract


START_SCRIPT = ROOT / "start_demo_session.bat"
ARTIFACT_DIR = ROOT / "docs" / "_artifacts"
SUMMARY_PATH = ARTIFACT_DIR / "real-demo-service-audit.json"
OUT_LOG_PATH = ARTIFACT_DIR / "real-demo-service-audit.out.log"
ERR_LOG_PATH = ARTIFACT_DIR / "real-demo-service-audit.err.log"
BATCH_ZIP_PATH = ARTIFACT_DIR / "real-demo-service-audit-batch.zip"
BASE_URL = "http://127.0.0.1:5000"
SAMPLE_IMAGE = ROOT / "testfile" / "0014012.jpg"
BATCH_IMAGES = [
    ROOT / "testfile" / "0009008.jpg",
    ROOT / "testfile" / "0009013.jpg",
    ROOT / "testfile" / "0009022.jpg",
]
VIDEO_SAMPLE = ROOT / "testfile" / "QQ202618-01246-HD.mp4"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def require_path(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Required file is missing: {path}")
    return path

def is_current_demo_running() -> bool:
    try:
        response = requests.get(f"{BASE_URL}/", timeout=2)
        return response.ok and ("课堂行为检测控制台" in response.text or "课堂行为检测" in response.text)
    except requests.RequestException:
        return False


def tail_text(path: Path, lines: int = 80) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def wait_for_demo_ready(process: subprocess.Popen[str] | None, timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds
    last_error: str | None = None
    while time.time() < deadline:
        if process is not None and process.poll() is not None:
            break
        try:
            response = requests.get(f"{BASE_URL}/api/auth/session", timeout=3)
            if response.status_code == 200:
                return
            last_error = f"unexpected status {response.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(1.0)
    message = "Real demo service did not become ready on http://127.0.0.1:5000"
    if last_error:
        message += f" ({last_error})"
    out_tail = tail_text(OUT_LOG_PATH)
    err_tail = tail_text(ERR_LOG_PATH)
    if out_tail:
        message += f"\n--- stdout tail ---\n{out_tail}"
    if err_tail:
        message += f"\n--- stderr tail ---\n{err_tail}"
    raise RuntimeError(message)

def api_request(
    session_client: requests.Session,
    method: str,
    path: str,
    *,
    expected_status: int = 200,
    timeout: float = 60,
    **kwargs,
):
    response = session_client.request(method, f"{BASE_URL}{path}", timeout=timeout, **kwargs)
    if response.status_code != expected_status:
        raise AssertionError(
            f"{method.upper()} {path} expected {expected_status}, got {response.status_code}: "
            f"{response.text[:400]}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise AssertionError(f"{method.upper()} {path} did not return JSON: {exc}") from exc
    if not payload.get("success"):
        error = payload.get("error") or {}
        raise AssertionError(
            f"{method.upper()} {path} failed: [{error.get('code')}] {error.get('message')}"
        )
    return payload.get("data")


def download_file(session_client: requests.Session, relative_url: str, output_path: Path) -> int:
    with session_client.get(f"{BASE_URL}{relative_url}", timeout=90) as response:
        if response.status_code != 200:
            raise AssertionError(f"download failed for {relative_url}: {response.status_code}")
        output_path.write_bytes(response.content)
    return output_path.stat().st_size


def guess_mime(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def detect_image_task(session_client: requests.Session) -> dict:
    with SAMPLE_IMAGE.open("rb") as file_obj:
        data = api_request(
            session_client,
            "POST",
            "/api/detect/image",
            files={"file": (SAMPLE_IMAGE.name, file_obj, guess_mime(SAMPLE_IMAGE))},
            data={"confidence": "0.25", "iou": "0.45"},
            timeout=120,
        )
    task_id = str(data["task_id"])
    detail = api_request(session_client, "GET", f"/api/tasks/{task_id}")
    report = api_request(session_client, "GET", f"/api/tasks/{task_id}/report", timeout=120)
    report_html = session_client.get(f"{BASE_URL}{report['report_url']}", timeout=60)
    if report_html.status_code != 200:
        raise AssertionError(f"report HTML unavailable: {report_html.status_code}")
    html = report_html.text
    for marker in ("课堂行为检测报告", "学生行为分析"):
        if marker not in html:
            raise AssertionError(f"report HTML missing marker: {marker}")
    if not detail.get("assets", {}).get("result"):
        raise AssertionError("image task missing result asset")
    return {
        "task_id": task_id,
        "result": detail["assets"]["result"],
        "report_url": report["report_url"],
        "report_filename": report["report_filename"],
        "total_detections": detail.get("total_detections"),
    }


def detect_batch_task(session_client: requests.Session) -> dict:
    file_handles = [path.open("rb") for path in BATCH_IMAGES]
    try:
        files = [("files", (path.name, handle, guess_mime(path))) for path, handle in zip(BATCH_IMAGES, file_handles)]
        data = api_request(
            session_client,
            "POST",
            "/api/detect/batch",
            files=files,
            data={"confidence": "0.25", "iou": "0.45"},
            timeout=180,
        )
    finally:
        for handle in file_handles:
            handle.close()
    task_id = str(data["task_id"])
    detail = api_request(session_client, "GET", f"/api/tasks/{task_id}")
    results = detail.get("assets", {}).get("results", [])
    if len(results) < len(BATCH_IMAGES):
        raise AssertionError(f"batch task results too short: {len(results)}")
    return {
        "task_id": task_id,
        "result_count": len(results),
        "report_url": detail.get("assets", {}).get("report"),
        "total_detections": detail.get("total_detections"),
    }


def wait_for_video_feed_chunk(session_client: requests.Session, task_id: str, timeout_seconds: int = 20) -> int:
    deadline = time.time() + timeout_seconds
    last_error: str | None = None
    while time.time() < deadline:
        try:
            with session_client.get(
                f"{BASE_URL}/api/streams/video/{task_id}/feed",
                stream=True,
                timeout=(3, 10),
            ) as response:
                if response.status_code != 200:
                    last_error = f"status {response.status_code}"
                else:
                    collected = bytearray()
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            collected.extend(chunk)
                            if b"Content-Type: image/jpeg" in collected:
                                return len(collected)
                            if len(collected) >= 16384:
                                break
                    if collected:
                        raise AssertionError("video feed payload did not expose jpeg multipart marker")
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.6)
    raise AssertionError(f"video feed did not yield frame chunk in time: {last_error or 'no chunk'}")


def wait_for_task(session_client: requests.Session, task_id: str, timeout_seconds: int = 300) -> dict:
    deadline = time.time() + timeout_seconds
    last_task: dict | None = None
    while time.time() < deadline:
        last_task = api_request(session_client, "GET", f"/api/tasks/{task_id}")
        if last_task.get("status") != "processing":
            return last_task
        time.sleep(1.5)
    raise AssertionError(f"task {task_id} did not finish within {timeout_seconds}s: {last_task}")


def detect_video_task(session_client: requests.Session) -> dict:
    with VIDEO_SAMPLE.open("rb") as file_obj:
        data = api_request(
            session_client,
            "POST",
            "/api/detect/video",
            files={"file": (VIDEO_SAMPLE.name, file_obj, guess_mime(VIDEO_SAMPLE))},
            data={"confidence": "0.25", "iou": "0.45", "frame_skip": "8"},
            timeout=240,
        )
    task_id = str(data["task_id"])
    first_chunk_size = wait_for_video_feed_chunk(session_client, task_id)
    task = wait_for_task(session_client, task_id, timeout_seconds=360)
    if task.get("status") != "completed":
        raise AssertionError(f"video task did not complete successfully: {task.get('status')}")
    result_video = task.get("assets", {}).get("result")
    if not result_video or not result_video.lower().endswith(".mp4"):
        raise AssertionError(f"video task missing mp4 result asset: {task.get('assets')}")
    return {
        "task_id": task_id,
        "status": task.get("status"),
        "processed_frames": task.get("processed_frames"),
        "total_frames": task.get("total_frames"),
        "total_detections": task.get("total_detections"),
        "result": result_video,
        "report_url": task.get("assets", {}).get("report"),
        "first_feed_chunk_bytes": first_chunk_size,
    }


def export_batch_reports(session_client: requests.Session, task_ids: list[str]) -> dict:
    data = api_request(
        session_client,
        "POST",
        "/api/tasks/reports/batch",
        json={"task_ids": task_ids},
        timeout=180,
    )
    file_size = download_file(session_client, data["zip_url"], BATCH_ZIP_PATH)
    with zipfile.ZipFile(BATCH_ZIP_PATH) as archive:
        names = set(archive.namelist())
        if "readme.txt" not in names or "manifest.csv" not in names:
            raise AssertionError(f"batch report archive missing manifest files: {sorted(names)}")
        html_count = len([name for name in names if name.startswith("report-") and name.endswith(".html")])
        if html_count < len(task_ids):
            raise AssertionError(f"batch report archive HTML count too small: {html_count}")
    return {
        "report_count": data.get("report_count"),
        "zip_filename": data.get("zip_filename"),
        "zip_url": data.get("zip_url"),
        "downloaded_size": file_size,
    }


def verify_recent_history(session_client: requests.Session, expected_task_ids: list[str]) -> dict:
    tasks = api_request(session_client, "GET", "/api/tasks/recent?limit=10").get("tasks") or []
    task_ids = [str(item.get("task_id")) for item in tasks]
    missing = [task_id for task_id in expected_task_ids if task_id not in task_ids]
    if missing:
        raise AssertionError(f"recent history missing expected tasks: {missing}")
    return {
        "count": len(tasks),
        "top_task_ids": task_ids[:5],
    }


def verify_dashboard_contract(session_client: requests.Session) -> dict:
    response = session_client.get(f"{BASE_URL}/", timeout=30)
    if response.status_code != 200:
        raise AssertionError(f"dashboard page status: {response.status_code}")
    html = response.text
    for marker in ("课堂行为检测", "reportLink", "historyExportSelectedBtn"):
        if marker not in html:
            raise AssertionError(f"dashboard HTML missing marker: {marker}")
    runtime = read_demo_entry_contract(base_url=BASE_URL)
    student = runtime.get("student") or {}
    teacher = runtime.get("teacher") or {}
    return {
        "default_mode": runtime.get("default_mode"),
        "student_selection_source": student.get("selection_source"),
        "teacher_selection_source": teacher.get("selection_source"),
        "student_locked": student.get("selection_locked"),
        "teacher_locked": teacher.get("selection_locked"),
        "student_relative_path": student.get("selection_relative_path"),
        "teacher_relative_path": teacher.get("selection_relative_path"),
    }


def verify_model_switch_contract(session_client: requests.Session) -> dict:
    before = api_request(session_client, "GET", "/api/models/info")
    api_request(
        session_client,
        "POST",
        "/api/models/load",
        json={"type": "student", "model": "behavior02.pt"},
        timeout=120,
    )
    switched = api_request(session_client, "GET", "/api/models/info")
    api_request(
        session_client,
        "POST",
        "/api/models/load",
        json={"type": "student", "model": "behavior.pt"},
        timeout=120,
    )
    restored = api_request(session_client, "GET", "/api/models/info")
    if switched.get("student", {}).get("selection_source") != "manual_selection":
        raise AssertionError(f"student model did not become manual_selection: {switched.get('student')}")
    if switched.get("student", {}).get("selection_relative_path") != "behavior02.pt":
        raise AssertionError(f"student model did not switch to behavior02.pt: {switched.get('student')}")
    if restored.get("student", {}).get("selection_relative_path") != "behavior.pt":
        raise AssertionError(f"student model did not restore to behavior.pt: {restored.get('student')}")
    return {
        "before": before.get("student", {}),
        "switched": switched.get("student", {}),
        "restored": restored.get("student", {}),
    }


def verify_webcam_contract(session_client: requests.Session) -> dict:
    diagnostics = api_request(session_client, "GET", "/api/streams/webcam/diagnostics?camera_index=0", timeout=30)
    attempts = diagnostics.get("attempts") or []
    if not attempts:
        raise AssertionError("webcam diagnostics returned no attempts")
    result = {
        "diagnostics": diagnostics,
        "started": False,
    }
    if not diagnostics.get("selected"):
        return result

    start = api_request(
        session_client,
        "POST",
        "/api/streams/webcam/start",
        json={"camera_index": 0, "confidence": 0.25, "iou": 0.45},
        timeout=60,
    )
    webcam_task_id = str(start["task_id"])
    metrics = None
    deadline = time.time() + 60
    while time.time() < deadline:
        metrics = api_request(session_client, "GET", "/api/streams/webcam/metrics", timeout=15)
        if int(metrics.get("processed_frames") or 0) > 0:
            break
        time.sleep(1.2)
    if not metrics or int(metrics.get("processed_frames") or 0) <= 0:
        raise AssertionError(f"webcam metrics never showed processed frames: {metrics}")

    stop = api_request(session_client, "POST", "/api/streams/webcam/stop", timeout=60)
    stopped_task = wait_for_task(session_client, webcam_task_id, timeout_seconds=120)
    assets = stopped_task.get("assets") or {}
    if not assets.get("original") or not assets.get("result"):
        raise AssertionError(f"stopped webcam task missing persisted assets: {assets}")
    result.update(
        {
            "started": True,
            "start": start,
            "metrics": metrics,
            "stop": stop,
            "task": {
                "task_id": stopped_task.get("task_id"),
                "status": stopped_task.get("status"),
                "processed_frames": stopped_task.get("processed_frames"),
                "total_frames": stopped_task.get("total_frames"),
                "total_detections": stopped_task.get("total_detections"),
                "assets": assets,
            },
        }
    )
    return result


def start_demo_process() -> tuple[subprocess.Popen[str], object, object]:
    stdout_file = OUT_LOG_PATH.open("w", encoding="utf-8", errors="replace")
    stderr_file = ERR_LOG_PATH.open("w", encoding="utf-8", errors="replace")
    process = subprocess.Popen(
        ["cmd", "/c", str(START_SCRIPT)],
        cwd=ROOT,
        stdout=stdout_file,
        stderr=stderr_file,
        creationflags=CREATE_NO_WINDOW,
        text=True,
    )
    return process, stdout_file, stderr_file


def main() -> int:
    require_path(START_SCRIPT)
    require_path(SAMPLE_IMAGE)
    require_path(VIDEO_SAMPLE)
    for batch_path in BATCH_IMAGES:
        require_path(batch_path)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    reused_existing = is_current_demo_running()
    process: subprocess.Popen[str] | None = None
    stdout_file = None
    stderr_file = None
    summary: dict[str, object] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "base_url": BASE_URL,
        "reused_existing_service": reused_existing,
    }
    try:
        if not reused_existing:
            process, stdout_file, stderr_file = start_demo_process()
        wait_for_demo_ready(process)

        with open_authenticated_session(base_url=BASE_URL, username=load_admin_username()) as session_client:
            dashboard = verify_dashboard_contract(session_client)
            if dashboard["default_mode"] != "image":
                raise AssertionError(f"demo default mode expected image, got: {dashboard}")
            if dashboard["student_selection_source"] != "env_default" or dashboard["student_locked"]:
                raise AssertionError(f"student model entry contract mismatch: {dashboard}")
            if dashboard["teacher_selection_source"] != "env_default" or dashboard["teacher_locked"]:
                raise AssertionError(f"teacher model entry contract mismatch: {dashboard}")

            model_switch = verify_model_switch_contract(session_client)
            image = detect_image_task(session_client)
            batch = detect_batch_task(session_client)
            video = detect_video_task(session_client)
            history = verify_recent_history(session_client, [image["task_id"], batch["task_id"], video["task_id"]])
            batch_export = export_batch_reports(session_client, [image["task_id"], batch["task_id"], video["task_id"]])
            webcam = verify_webcam_contract(session_client)

            summary.update(
                {
                    "dashboard": dashboard,
                    "model_switch": model_switch,
                    "image": image,
                    "batch": batch,
                    "video": video,
                    "history": history,
                    "batch_export": batch_export,
                    "webcam": webcam,
                    "artifacts": {
                        "summary": SUMMARY_PATH.relative_to(ROOT).as_posix(),
                        "stdout_log": OUT_LOG_PATH.relative_to(ROOT).as_posix(),
                        "stderr_log": ERR_LOG_PATH.relative_to(ROOT).as_posix(),
                        "batch_zip": BATCH_ZIP_PATH.relative_to(ROOT).as_posix(),
                    },
                }
            )
            SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        if stdout_file:
            stdout_file.close()
        if stderr_file:
            stderr_file.close()
        if process is not None and process.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
            )


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import base64
import copy
import io
import json
import shutil
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from isolated_env import create_and_apply_isolated_runtime


ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_PATH = ROOT / "docs" / "_artifacts" / "hardening-contracts.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from classroom_app.core.errors import ReportError, StreamError, TaskExecutionError
from classroom_app.services.stream_service import StreamService
from classroom_app.services.task_service import TaskService
from verify_report_archive import assert_batch_archive_contract as verify_batch_archive_contract
from verify_report_archive import assert_report_html_contract
from verify_report_archive import build_archive_expectations


ADMIN_USERNAME = "hardening_admin"
ADMIN_PASSWORD = "hardening_pass_123"


def configure_temp_environment():
    runtime, config = create_and_apply_isolated_runtime(
        "hardening-contracts",
        admin_username=ADMIN_USERNAME,
        admin_password=ADMIN_PASSWORD,
        model_folder=ROOT / "models",
    )
    return runtime.root, config


def assert_status(response, expected: int, label: str) -> dict:
    if response.status_code != expected:
        raise AssertionError(
            f"{label}: expected HTTP {expected}, got {response.status_code}: "
            f"{response.get_data(as_text=True)[:400]}"
        )
    return {"label": label, "status": expected}


def assert_error(response, expected_status: int, expected_code: str, label: str) -> dict:
    assert_status(response, expected_status, label)
    payload = response.get_json() or {}
    error = payload.get("error") or {}
    if error.get("code") != expected_code:
        raise AssertionError(f"{label}: expected error code {expected_code!r}, got {error.get('code')!r}")
    return {"label": label, "status": expected_status, "code": expected_code}


def login(client) -> None:
    response = client.post("/api/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert_status(response, 200, "admin login")


def load_sample_images() -> list[Path]:
    samples = sorted((ROOT / "testfile").glob("*.jpg"))
    if len(samples) < 2:
        raise RuntimeError("testfile/ 中至少需要 2 张 JPG 样例")
    return samples


def detect_image_task(client, image_path: Path) -> str:
    response = client.post(
        "/api/detect/image",
        data={
            "file": (io.BytesIO(image_path.read_bytes()), image_path.name),
            "confidence": "0.25",
            "iou": "0.45",
        },
        content_type="multipart/form-data",
    )
    assert_status(response, 200, f"detect image {image_path.name}")
    return response.get_json()["data"]["task_id"]


def detect_batch_task(client, image_paths: list[Path]) -> str:
    response = client.post(
        "/api/detect/batch",
        data={
            "files": [(io.BytesIO(path.read_bytes()), path.name) for path in image_paths],
            "confidence": "0.25",
            "iou": "0.45",
        },
        content_type="multipart/form-data",
    )
    assert_status(response, 200, "detect batch")
    return response.get_json()["data"]["task_id"]


def load_task_payload(client, task_id: str) -> dict:
    response = client.get(f"/api/tasks/{task_id}")
    assert_status(response, 200, f"task detail {task_id}")
    return response.get_json()["data"]


def build_data_url(image_path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(image_path.read_bytes()).decode("ascii")


def require_task_status(client, task_id: str, expected_status: str, label: str) -> dict:
    payload = load_task_payload(client, task_id)
    if payload.get("status") != expected_status:
        raise AssertionError(f"{label}: expected task status {expected_status!r}, got {payload.get('status')!r}")
    return payload


def require_report_meta(config, report_filename: str) -> tuple[Path, dict]:
    report_path = config.OUTPUT_FOLDER / report_filename
    meta_path = report_path.with_name(report_path.name + ".meta.json")
    if not report_path.exists():
        raise AssertionError(f"report file missing: {report_path.name}")
    if not meta_path.exists():
        raise AssertionError(f"report metadata missing: {meta_path.name}")
    return report_path, json.loads(meta_path.read_text(encoding="utf-8"))


def load_task_summary(client, task_id: str) -> dict:
    response = client.get(f"/api/tasks/{task_id}/summary")
    assert_status(response, 200, f"task summary {task_id}")
    return response.get_json()["data"]


def ensure_generated_report(client, config, task_id: str, label: str) -> dict:
    summary = load_task_summary(client, task_id)
    response = client.get(f"/api/tasks/{task_id}/report")
    assert_status(response, 200, label)
    report_payload = response.get_json()["data"]
    report_path, report_meta = require_report_meta(config, report_payload["report_filename"])
    report_validation = assert_report_html_contract(summary, report_path.read_text(encoding="utf-8"), label)
    return {
        "summary": summary,
        "report_payload": report_payload,
        "report_path": report_path,
        "report_meta": report_meta,
        "report_validation": report_validation,
    }


def run_route_contracts() -> dict:
    temp_root, config = configure_temp_environment()
    try:
        from classroom_app import create_app

        app = create_app()
        services = app.extensions["services"]
        sample_images = load_sample_images()

        with app.test_client() as client:
            login(client)
            results: dict[str, object] = {}

            original_create_task = services.tasks.db.create_task
            try:
                services.tasks.db.create_task = lambda *args, **kwargs: False
                results["browser_start_task_create_failure"] = assert_error(
                    client.post("/api/streams/webcam/browser-session/start"),
                    500,
                    "task_create_failed",
                    "browser webcam start surfaces task creation failure",
                )
            finally:
                services.tasks.db.create_task = original_create_task

            browser_start = client.post("/api/streams/webcam/browser-session/start")
            assert_status(browser_start, 200, "browser webcam start for report_not_ready")
            processing_task_id = browser_start.get_json()["data"]["task_id"]
            results["processing_report_block"] = assert_error(
                client.get(f"/api/tasks/{processing_task_id}/report"),
                409,
                "report_not_ready",
                "processing task report blocked",
            )

            empty_start = client.post("/api/streams/webcam/browser-session/start")
            assert_status(empty_start, 200, "browser webcam start for empty session")
            empty_task_id = empty_start.get_json()["data"]["task_id"]
            results["browser_empty_session"] = assert_error(
                client.post(
                    "/api/streams/webcam/browser-session/stop",
                    json={
                        "task_id": empty_task_id,
                        "processed_frames": 0,
                        "total_frames": 0,
                        "total_detections": 0,
                        "average_confidence": 0.0,
                        "duration": 0.0,
                    },
                ),
                409,
                "webcam_session_empty",
                "browser webcam empty stop blocked",
            )
            require_task_status(client, empty_task_id, "failed", "browser empty session task")

            invalid_start = client.post("/api/streams/webcam/browser-session/start")
            assert_status(invalid_start, 200, "browser webcam start for invalid image")
            invalid_task_id = invalid_start.get_json()["data"]["task_id"]
            invalid_frame = client.post(
                "/api/detect/frame",
                json={
                    "image": build_data_url(sample_images[0]),
                    "tracking_session_id": invalid_task_id,
                },
            )
            assert_status(invalid_frame, 200, "browser webcam capture before invalid image stop")
            results["browser_invalid_image"] = assert_error(
                client.post(
                    "/api/streams/webcam/browser-session/stop",
                    json={
                        "task_id": invalid_task_id,
                        "student_behavior_stats": {"reading": 1},
                        "teacher_behavior_stats": {"head": 1},
                        "total_detections": 2,
                        "average_confidence": 0.7,
                        "duration": 1.2,
                        "processed_frames": 1,
                        "total_frames": 1,
                        "original_image": "not-base64",
                        "annotated_image": "not-base64",
                    },
                ),
                400,
                "webcam_session_invalid_image",
                "browser webcam invalid image blocked",
            )
            require_task_status(client, invalid_task_id, "failed", "browser invalid image task")

            valid_start = client.post("/api/streams/webcam/browser-session/start")
            assert_status(valid_start, 200, "browser webcam start for valid session")
            valid_browser_task_id = valid_start.get_json()["data"]["task_id"]
            valid_frame = client.post(
                "/api/detect/frame",
                json={
                    "image": build_data_url(sample_images[0]),
                    "tracking_session_id": valid_browser_task_id,
                },
            )
            assert_status(valid_frame, 200, "browser webcam capture before valid stop")
            valid_browser_stop = client.post(
                "/api/streams/webcam/browser-session/stop",
                json={
                    "task_id": valid_browser_task_id,
                    "student_behavior_stats": {"reading": 2},
                    "teacher_behavior_stats": {"head": 1},
                    "total_detections": 3,
                    "average_confidence": 0.7,
                    "duration": 2.6,
                    "processed_frames": 3,
                    "total_frames": 3,
                    "original_image": build_data_url(sample_images[0]),
                    "annotated_image": build_data_url(sample_images[0]),
                },
            )
            assert_status(valid_browser_stop, 200, "browser webcam valid stop")
            valid_browser_payload = require_task_status(
                client,
                valid_browser_task_id,
                "completed",
                "browser valid session task",
            )
            if not valid_browser_payload.get("assets", {}).get("original") or not valid_browser_payload.get("assets", {}).get("result"):
                raise AssertionError("browser webcam valid session missing saved assets")
            results["browser_valid_session"] = {
                "task_id": valid_browser_task_id,
                "processed_frames": valid_browser_payload.get("processed_frames"),
            }

            report_task_id = detect_image_task(client, sample_images[0])
            report_contract = ensure_generated_report(client, config, report_task_id, "single report ready")
            report_payload = report_contract["report_payload"]
            report_path = report_contract["report_path"]
            report_meta = report_contract["report_meta"]
            report_mtime_before = report_path.stat().st_mtime_ns
            time.sleep(1.1)
            report_ready_again = client.get(f"/api/tasks/{report_task_id}/report")
            assert_status(report_ready_again, 200, "single report reused")
            report_payload_again = report_ready_again.get_json()["data"]
            if report_payload_again["report_filename"] != report_payload["report_filename"]:
                raise AssertionError("report filename changed between identical requests")
            if report_path.stat().st_mtime_ns != report_mtime_before:
                raise AssertionError("report was regenerated instead of reused")
            results["report_reuse"] = {
                "task_id": report_task_id,
                "report_filename": report_payload["report_filename"],
                "fingerprint": report_meta.get("fingerprint"),
            }

            missing_asset_task_id = detect_image_task(client, sample_images[1])
            missing_asset_payload = load_task_payload(client, missing_asset_task_id)
            missing_result_url = missing_asset_payload.get("assets", {}).get("result")
            if not missing_result_url:
                raise AssertionError("missing-asset task did not produce a result asset before deletion")
            missing_result_path = config.OUTPUT_FOLDER / Path(missing_result_url).name
            missing_result_path.unlink(missing_ok=True)
            results["report_asset_missing"] = assert_error(
                client.get(f"/api/tasks/{missing_asset_task_id}/report"),
                500,
                "report_asset_missing",
                "report blocks missing asset",
            )

            batch_task_id = detect_batch_task(client, sample_images[:2])
            batch_report_contract = ensure_generated_report(client, config, batch_task_id, "batch task report ready")
            batch_export = client.post("/api/tasks/reports/batch", json={"task_ids": [report_task_id, batch_task_id]})
            assert_status(batch_export, 200, "batch report export")
            batch_payload = batch_export.get_json()["data"]
            zip_path = config.OUTPUT_FOLDER / batch_payload["zip_filename"]
            if not zip_path.exists():
                raise AssertionError("batch export zip missing")
            with zipfile.ZipFile(zip_path) as archive:
                verify_batch_archive_contract(
                    archive,
                    build_archive_expectations(
                        [report_contract, batch_report_contract],
                        report_filename_path="report_payload.report_filename",
                    ),
                    "batch export",
                )
            results["batch_export_success"] = {
                "zip_filename": batch_payload["zip_filename"],
                "report_count": batch_payload["report_count"],
                "report_filenames": [
                    report_contract["report_payload"]["report_filename"],
                    batch_report_contract["report_payload"]["report_filename"],
                ],
            }

            results["batch_export_failure"] = assert_error(
                client.post("/api/tasks/reports/batch", json={"task_ids": [report_task_id, missing_asset_task_id]}),
                500,
                "report_asset_missing",
                "batch export blocks invalid member",
            )

            service_results = run_report_service_contracts(
                services,
                client,
                report_task_id,
                batch_task_id,
                sample_images[0],
                valid_browser_task_id,
            )
            results.update(service_results)
            results["task_service_contracts"] = run_task_service_contracts()
            results["native_webcam_contracts"] = run_native_webcam_contracts()
            return results
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def run_report_service_contracts(
    services,
    client,
    report_task_id: str,
    batch_task_id: str,
    sample_image: Path,
    tracking_task_id: str,
) -> dict:
    report_service = services.reports
    payload_service = services.task_payloads
    task_service = services.tasks
    results: dict[str, object] = {}

    concurrent_task_id = detect_image_task(client, sample_image)
    concurrent_summary = payload_service.build_task_payload(concurrent_task_id, include_assets=True, include_live_metrics=False)
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(report_service.ensure_task_report, concurrent_summary) for _ in range(4)]
        outputs = [future.result(timeout=90) for future in futures]
    report_names = {item["report_filename"] for item in outputs}
    if len(report_names) != 1:
        raise AssertionError(f"concurrent report requests produced different files: {sorted(report_names)}")
    results["concurrent_report_requests"] = {
        "task_id": concurrent_task_id,
        "report_filename": next(iter(report_names)),
    }

    refresh_summary = payload_service.build_task_payload(report_task_id, include_assets=True, include_live_metrics=False)
    refresh_report = report_service.ensure_task_report(refresh_summary)
    refresh_path = refresh_report["report_path"]
    refresh_mtime_before = refresh_path.stat().st_mtime_ns
    task_service.save_summary(
        report_task_id,
        refresh_summary.get("student_behavior_stats") or {},
        refresh_summary.get("teacher_behavior_stats") or {},
        int(refresh_summary.get("total_detections") or 0) + 1,
        float(refresh_summary.get("average_confidence") or 0.0),
        float(refresh_summary.get("duration") or 0.0),
    )
    time.sleep(1.1)
    refreshed_summary = payload_service.build_task_payload(report_task_id, include_assets=True, include_live_metrics=False)
    refreshed_report = report_service.ensure_task_report(refreshed_summary)
    if refreshed_report["report_path"].stat().st_mtime_ns <= refresh_mtime_before:
        raise AssertionError("report fingerprint drift did not force regeneration")
    results["report_fingerprint_refresh"] = {
        "task_id": report_task_id,
        "reused": refreshed_report["reused"],
    }

    tracking_summary = payload_service.build_task_payload(tracking_task_id, include_assets=True, include_live_metrics=False)
    tracking_report = report_service.ensure_task_report(tracking_summary)
    tracking_report_path = tracking_report["report_path"]
    tracking_mtime_before = tracking_report_path.stat().st_mtime_ns
    tracking_display_metrics = copy.deepcopy(tracking_summary.get("display_metrics") or {})
    tracking_derived_metrics = copy.deepcopy(tracking_summary.get("derived_metrics") or {})
    tracking_cards = tracking_display_metrics.get("cards") or []
    if not tracking_cards:
        raise AssertionError("tracking report refresh contract requires display metric cards")
    tracking_label = str(tracking_cards[0].get("label") or "独立目标数")
    sentinel_value = "999 个"
    tracking_cards[0]["formatted"] = sentinel_value
    tracking_cards[0]["value"] = 999
    primary_stat = tracking_display_metrics.get("primary_stat") or {}
    if primary_stat:
        primary_stat["formatted"] = sentinel_value
        primary_stat["value"] = 999
    highlight = tracking_display_metrics.get("highlight") or {}
    if highlight:
        highlight["history_text"] = f"亮点：{tracking_label} {sentinel_value}"
    tracking_derived_metrics["unique_targets"] = 999
    time.sleep(1.1)
    task_service.save_summary(
        tracking_task_id,
        tracking_summary.get("student_behavior_stats") or {},
        tracking_summary.get("teacher_behavior_stats") or {},
        int(tracking_summary.get("total_detections") or 0),
        float(tracking_summary.get("average_confidence") or 0.0),
        float(tracking_summary.get("duration") or 0.0),
        display_metrics=tracking_display_metrics,
        derived_metrics=tracking_derived_metrics,
    )
    refreshed_tracking_summary = payload_service.build_task_payload(tracking_task_id, include_assets=True, include_live_metrics=False)
    refreshed_tracking_report = report_service.ensure_task_report(refreshed_tracking_summary)
    if refreshed_tracking_report["report_path"].stat().st_mtime_ns <= tracking_mtime_before:
        raise AssertionError("tracking report display_metrics drift did not force regeneration")
    tracking_html = refreshed_tracking_report["report_path"].read_text(encoding="utf-8")
    if tracking_label not in tracking_html or sentinel_value not in tracking_html:
        raise AssertionError("tracking report HTML did not render refreshed display metrics")
    results["tracking_report_metric_refresh"] = {
        "task_id": tracking_task_id,
        "reused": refreshed_tracking_report["reused"],
        "metric_label": tracking_label,
        "metric_value": sentinel_value,
    }

    failing_task_id = detect_image_task(client, sample_image)
    failing_summary = payload_service.build_task_payload(failing_task_id, include_assets=True, include_live_metrics=False)
    original_render = report_service.render_html_report
    try:
        report_service.render_html_report = lambda summary, output_path: (_ for _ in ()).throw(RuntimeError("writer exploded"))
        try:
            report_service.ensure_task_report(failing_summary)
        except ReportError as exc:
            if exc.code != "report_generation_failed":
                raise AssertionError(f"expected report_generation_failed, got {exc.code!r}")
        else:
            raise AssertionError("report_generation_failed path did not raise")
    finally:
        report_service.render_html_report = original_render
    failure_stem = report_service.build_report_filename(failing_summary)
    leftover_report_temps = list(refresh_path.parent.glob(f"{failure_stem}.*.tmp"))
    if leftover_report_temps:
        raise AssertionError(f"report failure left temp files behind: {[item.name for item in leftover_report_temps]}")
    results["report_generation_failure_mapping"] = {"task_id": failing_task_id, "temp_files_cleaned": True}

    batch_summaries = [
        payload_service.build_task_payload(report_task_id, include_assets=True, include_live_metrics=False),
        payload_service.build_task_payload(batch_task_id, include_assets=True, include_live_metrics=False),
    ]
    original_writer = report_service.write_batch_archive
    try:
        report_service.write_batch_archive = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("zip write failed"))
        try:
            report_service.build_batch_bundle(batch_summaries)
        except ReportError as exc:
            if exc.code != "report_bundle_failed":
                raise AssertionError(f"expected report_bundle_failed, got {exc.code!r}")
        else:
            raise AssertionError("report_bundle_failed path did not raise")
    finally:
        report_service.write_batch_archive = original_writer
    leftover_bundle_temps = list(refresh_path.parent.glob("reports-batch-*.tmp"))
    if leftover_bundle_temps:
        raise AssertionError(f"batch failure left temp bundle behind: {[item.name for item in leftover_bundle_temps]}")
    results["report_bundle_failure_mapping"] = {"temp_files_cleaned": True}

    return results


class DummyDetector:
    def __init__(self):
        self.recent_student_behaviors = []
        self.recent_teacher_behaviors = []

    def reset_stats(self):
        return None

    def get_realtime_stats(self):
        return {
            "student_behavior_stats": {},
            "teacher_behavior_stats": {},
            "fps": 0.0,
            "uptime_seconds": 0.0,
            "total_detections": 0,
            "average_confidence": 0.0,
        }

    def create_tracking_runtime(self):
        class _DummyTrackingRuntime:
            @staticmethod
            def detect_image(_image):
                return {
                    "student_detections": [],
                    "teacher_detections": [],
                    "annotated_image": _image,
                    "student_behavior_counts": {},
                    "teacher_behavior_counts": {},
                }

        return _DummyTrackingRuntime()


class DummyModelService:
    def __init__(self):
        self.detector = DummyDetector()

    def update_parameters(self, confidence, iou):
        self.confidence = confidence
        self.iou = iou

    def get_detector(self):
        return self.detector


class DummyTaskService:
    def __init__(self):
        self.created = []
        self.status_updates = []
        self.saved_summaries = []
        self.assets = []
        self.tasks = {}

    def create_task(self, task_id, task_type, file_name=None):
        record = {
            "task_id": task_id,
            "task_type": task_type,
            "file_name": file_name,
            "status": "processing",
        }
        self.created.append(record)
        self.tasks[task_id] = dict(record)

    def update_status(self, task_id, status, processed_frames=None, total_frames=None):
        update = {
            "task_id": task_id,
            "status": status,
            "processed_frames": processed_frames,
            "total_frames": total_frames,
        }
        self.status_updates.append(update)
        if task_id in self.tasks:
            self.tasks[task_id].update(update)

    def save_summary(self, *args, **kwargs):
        if kwargs:
            task_id = args[0] if args else kwargs.get("task_id")
            summary_record = {
                "task_id": task_id,
                "student_behavior_stats": kwargs.get("student_behavior_stats", {}),
                "teacher_behavior_stats": kwargs.get("teacher_behavior_stats", {}),
                "total_detections": kwargs.get("total_detections", 0),
                "average_confidence": kwargs.get("average_confidence", 0.0),
                "duration": kwargs.get("duration", 0.0),
                "processed_frames": kwargs.get("processed_frames", 0),
                "total_frames": kwargs.get("total_frames", 0),
                "display_metrics": kwargs.get("display_metrics", {}),
                "derived_metrics": kwargs.get("derived_metrics", {}),
            }
        else:
            (
                task_id,
                student_behavior_stats,
                teacher_behavior_stats,
                total_detections,
                average_confidence,
                duration,
            ) = args
            summary_record = {
                "task_id": task_id,
                "student_behavior_stats": student_behavior_stats,
                "teacher_behavior_stats": teacher_behavior_stats,
                "total_detections": total_detections,
                "average_confidence": average_confidence,
                "duration": duration,
                "processed_frames": 0,
                "total_frames": 0,
                "display_metrics": {},
                "derived_metrics": {},
            }
        self.saved_summaries.append(summary_record)
        if task_id in self.tasks:
            self.tasks[task_id].update(summary_record)

    def save_task_asset(self, *args, **kwargs):
        self.assets.append((args, kwargs))

    def save_student_detections_bulk(self, *args, **kwargs):
        return None

    def save_teacher_detections_bulk(self, *args, **kwargs):
        return None

    def get_task(self, task_id):
        task = self.tasks.get(task_id)
        return dict(task) if task else None


def run_task_service_contracts() -> dict:
    class FailingCreateTaskDb:
        def __init__(self):
            self.calls = []

        def create_task(self, task_id, task_type, file_name=None):
            self.calls.append(
                {
                    "task_id": task_id,
                    "task_type": task_type,
                    "file_name": file_name,
                }
            )
            return False

    task_service = TaskService.__new__(TaskService)
    task_service.db = FailingCreateTaskDb()
    try:
        task_service.create_task("task-create-failure", "image", "sample.jpg")
    except TaskExecutionError as exc:
        if exc.code != "task_create_failed":
            raise AssertionError(f"task creation failure should raise task_create_failed, got {exc.code!r}")
    else:
        raise AssertionError("task creation failure should raise TaskExecutionError")

    if len(task_service.db.calls) != 1:
        raise AssertionError("task creation failure contract should still invoke the database layer exactly once")

    return {"task_create_failure": "raises_task_create_failed"}


def run_native_webcam_contracts() -> dict:
    def stable_ready_loop(stream: StreamService):
        def _loop():
            stream._webcam_ready_event.set()
            while stream.webcam_state["running"]:
                time.sleep(0.01)
        return _loop

    timeout_task_service = DummyTaskService()
    timeout_stream = StreamService(DummyModelService(), timeout_task_service)
    timeout_stream.WEBCAM_STARTUP_TIMEOUT = 0.1
    timeout_stream.diagnose_webcam = lambda camera_index: {
        "selected": {"index": camera_index, "backend": "CAP_ANY", "backend_id": 0},
        "attempts": [],
    }
    timeout_stream._run_webcam_loop = lambda: time.sleep(0.25)
    try:
        timeout_stream.start_webcam(0, 0.25, 0.45)
    except StreamError as exc:
        if exc.code != "webcam_unready":
            raise AssertionError(f"startup timeout should raise webcam_unready, got {exc.code!r}")
    else:
        raise AssertionError("startup timeout should have raised webcam_unready")
    if not timeout_task_service.status_updates or timeout_task_service.status_updates[-1]["status"] != "failed":
        raise AssertionError("startup timeout did not mark webcam task failed")

    post_start_task_service = DummyTaskService()
    post_start_stream = StreamService(DummyModelService(), post_start_task_service)
    post_start_stream.WEBCAM_STARTUP_TIMEOUT = 0.2
    post_start_stream.diagnose_webcam = lambda camera_index: {
        "selected": {"index": camera_index, "backend": "CAP_ANY", "backend_id": 0},
        "attempts": [],
    }

    def fake_loop():
        post_start_stream._webcam_ready_event.set()
        time.sleep(0.05)
        post_start_stream._mark_webcam_failure("camera read failed")

    post_start_stream._run_webcam_loop = fake_loop
    start_result = post_start_stream.start_webcam(0, 0.25, 0.45)
    if not start_result.get("task_id"):
        raise AssertionError("post-start failure scenario did not return task_id on successful start")

    deadline = time.time() + 1.0
    while time.time() < deadline and (
        not post_start_task_service.status_updates or post_start_task_service.status_updates[-1]["status"] != "failed"
    ):
        time.sleep(0.05)
    if not post_start_task_service.status_updates or post_start_task_service.status_updates[-1]["status"] != "failed":
        raise AssertionError("post-start read failure did not mark webcam task failed")
    if "camera read failed" not in (post_start_stream.webcam_state.get("last_error") or ""):
        raise AssertionError("post-start read failure did not preserve last_error")

    idempotent_task_service = DummyTaskService()
    idempotent_stream = StreamService(DummyModelService(), idempotent_task_service)
    idempotent_stream.WEBCAM_STARTUP_TIMEOUT = 0.2
    idempotent_stream.diagnose_webcam = lambda camera_index: {
        "selected": {"index": camera_index, "backend": "CAP_DSHOW", "backend_id": 700},
        "attempts": [],
    }
    idempotent_stream._run_webcam_loop = stable_ready_loop(idempotent_stream)
    first_start = idempotent_stream.start_webcam(0, 0.25, 0.45)
    second_start = idempotent_stream.start_webcam(0, 0.25, 0.45)
    if second_start.get("task_id") != first_start.get("task_id"):
        raise AssertionError("duplicate webcam start should reuse the active task")
    if len(idempotent_task_service.created) != 1:
        raise AssertionError("duplicate webcam start should not create a second task")
    idempotent_stream.stop_webcam()

    stale_task_service = DummyTaskService()
    stale_stream = StreamService(DummyModelService(), stale_task_service)
    stale_stream.WEBCAM_STARTUP_TIMEOUT = 0.2
    stale_stream.diagnose_webcam = lambda camera_index: {
        "selected": {"index": camera_index, "backend": "CAP_DSHOW", "backend_id": 700},
        "attempts": [],
    }
    stale_stream._run_webcam_loop = stable_ready_loop(stale_stream)
    stale_start = stale_stream.start_webcam(0, 0.25, 0.45)
    stale_task_service.update_status(stale_start["task_id"], "completed")
    restarted = stale_stream.start_webcam(0, 0.25, 0.45)
    if restarted.get("task_id") == stale_start.get("task_id"):
        raise AssertionError("stale webcam running state should restart with a new task")
    if len(stale_task_service.created) != 2:
        raise AssertionError("stale webcam running state should create a fresh task after cleanup")
    stale_stream.stop_webcam()

    return {
        "startup_timeout": "webcam_unready",
        "post_start_read_failure": "failed_with_last_error",
        "duplicate_start": "reuses_active_task",
        "stale_running_restart": "restarts_after_cleanup",
    }


def write_artifact(results: dict) -> None:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    artifact = {"generated_at": datetime.now().isoformat(timespec="seconds"), **results}
    ARTIFACT_PATH.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    try:
        results = run_route_contracts()
        write_artifact(results)
    except Exception as exc:
        print(f"硬化契约验证失败: {exc}")
        return 1
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"硬化契约验证通过，产物已写入 {ARTIFACT_PATH.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

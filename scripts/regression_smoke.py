from __future__ import annotations

import io
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

from isolated_env import create_and_apply_isolated_runtime


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from verify_report_archive import assert_batch_archive_contract, assert_report_html_contract, build_archive_expectations


# Cover the primary end-to-end business paths in an isolated regression environment.
def configure_temp_environment():
    runtime, config = create_and_apply_isolated_runtime(
        "regression",
        admin_username="regression_admin",
        admin_password="regression_pass_123",
        model_folder=ROOT / "models",
    )
    return runtime.root, config


def assert_status(response, expected=200, label="request"):
    if response.status_code != expected:
        raise AssertionError(f"{label} expected {expected}, got {response.status_code}: {response.get_data(as_text=True)[:300]}")


def upload_file_tuple(path: Path, field_name: str = "file"):
    return {field_name: (io.BytesIO(path.read_bytes()), path.name)}


def assert_tracking_summary(summary_payload: dict, detection_payload: dict, label: str) -> None:
    display_metrics = summary_payload.get("display_metrics")
    derived_metrics = summary_payload.get("derived_metrics")
    if not isinstance(display_metrics, dict) or not isinstance(derived_metrics, dict):
        raise AssertionError(f"{label} missing display_metrics/derived_metrics")
    if display_metrics.get("metric_mode") != "tracking" or derived_metrics.get("metric_mode") != "tracking":
        raise AssertionError(f"{label} missing tracking metric mode")

    unique_by_source = {"student": set(), "teacher": set()}
    per_frame_track_keys: dict[int, set[str]] = {}
    total_detections = 0
    for source in ("student", "teacher"):
        detections = detection_payload.get(f"{source}_detections", []) or []
        for item in detections:
            total_detections += 1
            track_id = item.get("track_id")
            if track_id is None:
                raise AssertionError(f"{label} detections missing track_id")
            numeric_track_id = int(track_id)
            unique_by_source[source].add(numeric_track_id)
            frame_number = int(item.get("frame_number") or 0)
            frame_track_keys = per_frame_track_keys.setdefault(frame_number, set())
            frame_track_keys.add(f"{source}:{numeric_track_id}")

    expected_breakdown = {
        "student": len(unique_by_source["student"]),
        "teacher": len(unique_by_source["teacher"]),
    }
    expected_unique_targets = expected_breakdown["student"] + expected_breakdown["teacher"]
    expected_peak_concurrency = max((len(track_keys) for track_keys in per_frame_track_keys.values()), default=0)

    if int(summary_payload.get("total_detections", 0) or 0) != total_detections:
        raise AssertionError(f"{label} total_detections mismatch")
    if int(derived_metrics.get("unique_targets", 0) or 0) != expected_unique_targets:
        raise AssertionError(f"{label} unique_targets mismatch")
    if int(derived_metrics.get("peak_concurrency", 0) or 0) != expected_peak_concurrency:
        raise AssertionError(f"{label} peak_concurrency mismatch")
    if derived_metrics.get("track_source_breakdown") != expected_breakdown:
        raise AssertionError(f"{label} track_source_breakdown mismatch")


def run():
    temp_root, Config = configure_temp_environment()
    try:
        from classroom_app import create_app

        app = create_app()
        image_paths = sorted((ROOT / "testfile").glob("*.jpg"))
        video_path = ROOT / "testfile" / "QQ202618-01246-HD.mp4"
        if len(image_paths) < 2 or not video_path.exists():
            raise RuntimeError("testfile/ 中缺少回归所需样例素材")

        results = []
        with app.test_client() as client:
            unauth = client.get("/api/dashboard/overview", follow_redirects=False)
            results.append(("unauth_overview", unauth.status_code in {302, 401}))

            login = client.post("/api/auth/login", json={"username": "regression_admin", "password": "regression_pass_123"})
            assert_status(login, 200, "login_api")

            image_response = client.post(
                "/api/detect/image",
                data={**upload_file_tuple(image_paths[0]), "confidence": "0.25", "iou": "0.45"},
                content_type="multipart/form-data",
            )
            assert_status(image_response, 200, "detect_image")
            image_data = image_response.get_json()["data"]
            image_detail_response = client.get(f"/api/tasks/{image_data['task_id']}")
            assert_status(image_detail_response, 200, "image_task_detail")
            image_detail_payload = image_detail_response.get_json()["data"]
            if not image_detail_payload.get("assets", {}).get("result"):
                raise AssertionError("image task detail missing result asset")
            if not (Config.OUTPUT_FOLDER / Path(image_detail_payload["assets"]["result"]).name).exists():
                raise AssertionError("image task detail result asset file missing")
            results.append(("image_detect", True))

            batch_data = {
                "files": [
                    (io.BytesIO(image_paths[0].read_bytes()), image_paths[0].name),
                    (io.BytesIO(image_paths[1].read_bytes()), image_paths[1].name),
                ],
                "confidence": "0.25",
                "iou": "0.45",
            }
            batch_response = client.post("/api/detect/batch", data=batch_data, content_type="multipart/form-data")
            assert_status(batch_response, 200, "detect_batch")
            batch_payload = batch_response.get_json()["data"]
            batch_detail_response = client.get(f"/api/tasks/{batch_payload['task_id']}")
            assert_status(batch_detail_response, 200, "batch_task_detail")
            batch_detail_payload = batch_detail_response.get_json()["data"]
            if len(batch_detail_payload.get("assets", {}).get("results", [])) < 2:
                raise AssertionError("batch task detail results < 2")
            results.append(("batch_detect", True))

            settings_response = client.post(
                "/api/user/settings",
                json={
                    "default_mode": "video",
                    "auto_scan_models": False,
                    "show_confidence": False,
                    "show_bbox_labels": False,
                },
            )
            assert_status(settings_response, 200, "save_settings")
            settings_payload = settings_response.get_json()["data"]["settings"]
            if settings_payload.get("default_mode") != "video":
                raise AssertionError("settings save mismatch")
            results.append(("settings_save", True))

            video_response = client.post(
                "/api/detect/video",
                data={**upload_file_tuple(video_path), "confidence": "0.25", "iou": "0.45", "frame_skip": "8"},
                content_type="multipart/form-data",
            )
            assert_status(video_response, 200, "detect_video")
            video_task_id = video_response.get_json()["data"]["task_id"]

            feed_deadline = time.time() + 20
            first_feed_chunk = None
            while time.time() < feed_deadline:
                feed_response = client.get(f"/api/streams/video/{video_task_id}/feed", buffered=False)
                try:
                    first_feed_chunk = next(feed_response.response, None)
                finally:
                    feed_response.close()
                if first_feed_chunk:
                    break
                time.sleep(0.5)
            if not first_feed_chunk or b"Content-Type: image/jpeg" not in first_feed_chunk:
                raise AssertionError("video feed did not yield jpeg stream chunk during processing")
            results.append(("video_feed_stream", True))

            deadline = time.time() + 90
            final_task = None
            while time.time() < deadline:
                task_response = client.get(f"/api/tasks/{video_task_id}")
                assert_status(task_response, 200, "task_detail")
                final_task = task_response.get_json()["data"]
                if final_task["status"] != "processing":
                    break
                time.sleep(1.0)
            if not final_task or final_task["status"] not in {"completed", "failed"}:
                raise AssertionError("video task did not finish within timeout")
            if "assets" not in final_task:
                raise AssertionError("video task detail missing unified assets payload")
            results.append(("video_task_finished", True))

            video_summary_response = client.get(f"/api/tasks/{video_task_id}/summary")
            assert_status(video_summary_response, 200, "video_task_summary")
            video_summary = video_summary_response.get_json()["data"]
            video_detail_alias_response = client.get(f"/api/tasks/{video_task_id}")
            assert_status(video_detail_alias_response, 200, "video_task_detail_alias")
            video_detail_alias = video_detail_alias_response.get_json()["data"]
            for key in ("task_id", "status", "task_type", "total_detections", "processed_frames", "total_frames"):
                if video_summary.get(key) != video_detail_alias.get(key):
                    raise AssertionError(f"video summary/detail alias mismatch: {key}")
            video_detections_response = client.get(f"/api/tasks/{video_task_id}/detections")
            assert_status(video_detections_response, 200, "video_task_detections")
            video_detections = video_detections_response.get_json()["data"]
            video_detection_count = len(video_detections.get("student_detections", [])) + len(video_detections.get("teacher_detections", []))
            if video_detection_count != int(video_summary.get("total_detections", 0) or 0):
                raise AssertionError("video task detection detail count mismatch")
            if any(item.get("frame_number") is None for item in video_detections.get("student_detections", []) + video_detections.get("teacher_detections", [])):
                raise AssertionError("video task detections contain missing frame_number")
            assert_tracking_summary(video_summary, video_detections, "video task tracking summary")
            results.append(("video_detail_integrity", True))
            video_report_response = client.get(f"/api/tasks/{video_task_id}/report")
            assert_status(video_report_response, 200, "video_task_report")
            video_report_payload = video_report_response.get_json()["data"]
            video_report_path = Config.OUTPUT_FOLDER / video_report_payload["report_filename"]
            if not video_report_path.exists():
                raise AssertionError("video report file missing")
            assert_report_html_contract(
                video_summary,
                video_report_path.read_text(encoding="utf-8"),
                "video report",
            )
            results.append(("video_report", True))

            stop_video_response = client.post(
                "/api/detect/video",
                data={**upload_file_tuple(video_path), "confidence": "0.25", "iou": "0.45", "frame_skip": "8"},
                content_type="multipart/form-data",
            )
            assert_status(stop_video_response, 200, "detect_video_stop_case")
            stop_task_id = stop_video_response.get_json()["data"]["task_id"]
            time.sleep(1.0)
            stop_response = client.post(f"/api/streams/video/{stop_task_id}/stop")
            assert_status(stop_response, 200, "stop_video")
            stop_deadline = time.time() + 30
            stopped_task = None
            while time.time() < stop_deadline:
                task_response = client.get(f"/api/tasks/{stop_task_id}")
                assert_status(task_response, 200, "stopped_task_detail")
                stopped_task = task_response.get_json()["data"]
                if stopped_task["status"] != "processing":
                    break
                time.sleep(0.5)
            if not stopped_task or stopped_task["status"] != "stopped_partial":
                raise AssertionError("stopped video task did not transition to stopped_partial")
            if stopped_task.get("live_metrics") is not None and "processed_frames" not in stopped_task:
                raise AssertionError("stopped task missing processed frame overlay")
            results.append(("video_task_stopped", True))

            summary_response = client.get(f"/api/tasks/{image_data['task_id']}/summary")
            assert_status(summary_response, 200, "task_summary")
            image_summary_payload = summary_response.get_json()["data"]
            if image_summary_payload.get("task_id") != image_detail_payload.get("task_id"):
                raise AssertionError("image summary/detail alias mismatch")
            detections_response = client.get(f"/api/tasks/{image_data['task_id']}/detections?frame_number=0")
            assert_status(detections_response, 200, "task_detections")
            detections_payload = detections_response.get_json()["data"]
            if "student_detections" not in detections_payload or "teacher_detections" not in detections_payload:
                raise AssertionError("task detections payload missing keys")
            results.append(("task_detections", True))
            report_response = client.get(f"/api/tasks/{image_data['task_id']}/report")
            assert_status(report_response, 200, "task_report")
            report_payload = report_response.get_json()["data"]
            report_path = Config.OUTPUT_FOLDER / report_payload["report_filename"]
            if not report_path.exists():
                raise AssertionError("single report file missing")
            report_mtime_before = report_path.stat().st_mtime_ns
            time.sleep(1.1)
            report_response_again = client.get(f"/api/tasks/{image_data['task_id']}/report")
            assert_status(report_response_again, 200, "task_report_reuse")
            report_payload_again = report_response_again.get_json()["data"]
            if report_payload_again["report_filename"] != report_payload["report_filename"]:
                raise AssertionError("single report filename changed between requests")
            report_mtime_after = report_path.stat().st_mtime_ns
            if report_mtime_after != report_mtime_before:
                raise AssertionError("single report was regenerated instead of reused")
            assert_report_html_contract(
                image_summary_payload,
                report_path.read_text(encoding="utf-8"),
                "single report",
            )
            results.append(("single_report", True))

            batch_summary_response = client.get(f"/api/tasks/{batch_payload['task_id']}/summary")
            assert_status(batch_summary_response, 200, "batch_task_summary")
            batch_summary_payload = batch_summary_response.get_json()["data"]
            batch_task_report_response = client.get(f"/api/tasks/{batch_payload['task_id']}/report")
            assert_status(batch_task_report_response, 200, "batch_task_report")
            batch_task_report_payload = batch_task_report_response.get_json()["data"]
            batch_task_report_path = Config.OUTPUT_FOLDER / batch_task_report_payload["report_filename"]
            if not batch_task_report_path.exists():
                raise AssertionError("batch task report file missing")
            assert_report_html_contract(
                batch_summary_payload,
                batch_task_report_path.read_text(encoding="utf-8"),
                "batch task report",
            )
            batch_report_response = client.post(
                "/api/tasks/reports/batch",
                json={"task_ids": [image_data["task_id"], batch_payload["task_id"], video_task_id]},
            )
            assert_status(batch_report_response, 200, "batch_reports")
            batch_report_payload = batch_report_response.get_json()["data"]
            if int(batch_report_payload.get("report_count", 0) or 0) != 3:
                raise AssertionError(f"batch report count mismatch: {batch_report_payload}")
            zip_path = Config.OUTPUT_FOLDER / batch_report_payload["zip_filename"]
            if not zip_path.exists():
                raise AssertionError("batch zip missing")
            with zipfile.ZipFile(zip_path) as archive:
                assert_batch_archive_contract(
                    archive,
                    build_archive_expectations(
                        [
                            {
                                "report_filename": report_payload["report_filename"],
                                "summary": image_summary_payload,
                            },
                            {
                                "report_filename": batch_task_report_payload["report_filename"],
                                "summary": batch_summary_payload,
                            },
                            {
                                "report_filename": video_report_payload["report_filename"],
                                "summary": video_summary,
                            },
                        ]
                    ),
                    "batch zip",
                )
            results.append(("batch_report_zip", True))

            history_response = client.get("/api/tasks/recent?limit=10")
            assert_status(history_response, 200, "recent_tasks")
            history_payload = history_response.get_json()["data"]["tasks"]
            if len(history_payload) < 3:
                raise AssertionError("recent task list too short after smoke run")
            recent_image_task = next((item for item in history_payload if item.get("task_id") == image_data["task_id"]), None)
            if not recent_image_task:
                raise AssertionError("recent task list missing image task")
            for key in ("total_detections", "duration", "student_behavior_stats", "teacher_behavior_stats", "display_metrics", "derived_metrics"):
                if key not in recent_image_task:
                    raise AssertionError(f"recent task missing aggregated field: {key}")
            if "assets" not in recent_image_task:
                raise AssertionError("recent task missing unified assets payload")
            results.append(("history_recent", True))

            webcam_diag = client.get("/api/streams/webcam/diagnostics?camera_index=0")
            assert_status(webcam_diag, 200, "webcam_diagnostics")
            diag_payload = webcam_diag.get_json()["data"]
            browser_session_start = client.post("/api/streams/webcam/browser-session/start")
            assert_status(browser_session_start, 200, "browser_webcam_session_start")
            browser_task_id = browser_session_start.get_json()["data"]["task_id"]
            sample_base64 = "data:image/jpeg;base64," + __import__("base64").b64encode(image_paths[0].read_bytes()).decode("ascii")
            browser_frame_response = client.post(
                "/api/detect/frame",
                json={"image": sample_base64, "tracking_session_id": browser_task_id},
            )
            assert_status(browser_frame_response, 200, "browser_webcam_session_frame")
            browser_frame_payload = browser_frame_response.get_json()["data"]
            if not isinstance(browser_frame_payload.get("summary"), dict):
                raise AssertionError("browser webcam detect frame missing tracked summary")
            browser_session_stop = client.post(
                "/api/streams/webcam/browser-session/stop",
                json={
                    "task_id": browser_task_id,
                    "original_image": sample_base64,
                    "annotated_image": sample_base64,
                },
            )
            assert_status(browser_session_stop, 200, "browser_webcam_session_stop")
            browser_summary = client.get(f"/api/tasks/{browser_task_id}/summary")
            assert_status(browser_summary, 200, "browser_webcam_summary")
            browser_payload = browser_summary.get_json()["data"]
            if browser_payload.get("assets", {}).get("result") is None:
                raise AssertionError("browser webcam session missing saved result asset")
            if not isinstance(browser_payload.get("display_metrics"), dict) or browser_payload.get("display_metrics", {}).get("metric_mode") != "tracking":
                raise AssertionError("browser webcam session summary missing tracking display metrics")
            browser_detections = client.get(f"/api/tasks/{browser_task_id}/detections")
            assert_status(browser_detections, 200, "browser_webcam_detections")
            browser_detection_payload = browser_detections.get_json()["data"]
            assert_tracking_summary(browser_payload, browser_detection_payload, "browser webcam session tracking summary")
            results.append(("browser_webcam_session", True))
            if diag_payload.get("selected"):
                webcam_start = client.post("/api/streams/webcam/start", json={"camera_index": 0, "confidence": 0.25, "iou": 0.45})
                if webcam_start.status_code == 400:
                    webcam_start_payload = webcam_start.get_json() or {}
                    webcam_error_code = ((webcam_start_payload.get("error") or {}).get("code") or "").strip()
                    if webcam_error_code in {"webcam_unready", "webcam_unavailable"}:
                        results.append(("webcam_live_cycle", f"blocked:{webcam_error_code}"))
                        webcam_start = None
                    else:
                        assert_status(webcam_start, 200, "webcam_start")
                else:
                    assert_status(webcam_start, 200, "webcam_start")
                if webcam_start is None:
                    pass
                else:
                    time.sleep(2.0)
                    webcam_stop = client.post("/api/streams/webcam/stop")
                    assert_status(webcam_stop, 200, "webcam_stop")
                    webcam_task_id = webcam_stop.get_json()["data"]["task_id"]
                    webcam_summary_response = client.get(f"/api/tasks/{webcam_task_id}/summary")
                    assert_status(webcam_summary_response, 200, "webcam_summary")
                    webcam_summary_payload = webcam_summary_response.get_json()["data"]
                    webcam_assets = webcam_summary_payload.get("assets", {})
                    if not webcam_assets.get("original") or not webcam_assets.get("result"):
                        raise AssertionError("webcam live task missing persisted assets")
                    webcam_detections_response = client.get(f"/api/tasks/{webcam_task_id}/detections")
                    assert_status(webcam_detections_response, 200, "webcam_detections")
                    webcam_detections_payload = webcam_detections_response.get_json()["data"]
                    assert_tracking_summary(webcam_summary_payload, webcam_detections_payload, "webcam live tracking summary")
                    results.append(("webcam_live_cycle", True))
            else:
                results.append(("webcam_live_cycle", "blocked:no_camera"))

        print("回归结果:")
        for name, status in results:
            print(f"- {name}: {status}")
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(run())

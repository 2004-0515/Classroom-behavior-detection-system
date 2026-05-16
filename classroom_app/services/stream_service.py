from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from typing import List, Dict, Any

import cv2

from classroom_app.core.errors import InputError, StreamError
from config import Config


class StreamService:
    PROBE_BACKEND_ORDER = (
        ("CAP_DSHOW", cv2.CAP_DSHOW),
        ("CAP_ANY", cv2.CAP_ANY),
        ("CAP_MSMF", cv2.CAP_MSMF),
    )
    PROBE_INDEX_LIMIT = 6
    PROBE_READ_ATTEMPTS = 5
    PROBE_READ_DELAY = 0.08
    PROBE_DIAGNOSTIC_TIMEOUT = 12.0
    PROBE_ATTEMPT_TIMEOUT = 5.0
    WEBCAM_STARTUP_TIMEOUT = 4.0

    def __init__(self, model_service, task_service):
        self.model_service = model_service
        self.task_service = task_service
        self.logger = logging.getLogger(__name__)
        self.webcam_state = {
            "running": False,
            "camera_index": 0,
            "backend": cv2.CAP_ANY,
            "backend_name": "CAP_ANY",
            "task_id": None,
            "started_at": None,
            "frame_count": 0,
            "processed_frames": 0,
            "total_detections": 0,
            "confidence_sum": 0.0,
            "student_behavior_stats": {},
            "teacher_behavior_stats": {},
            "last_error": None,
        }
        self.latest_original_frame = None
        self.latest_annotated_frame = None
        self.latest_frame_id = 0
        self._webcam_thread = None
        self._lock = threading.Lock()
        self._webcam_ready_event = threading.Event()
        self._webcam_failure_event = threading.Event()

    def start_webcam(self, camera_index, confidence, iou):
        if self.webcam_state["running"]:
            raise InputError("摄像头已在运行", code="webcam_running")

        diagnostics = self.diagnose_webcam(camera_index)
        selected = diagnostics.get("selected")
        if not selected:
            attempts = diagnostics.get("attempts", [])
            error = attempts[0]["error"] if attempts else f"摄像头 {camera_index} 不可用"
            raise StreamError(error, code="webcam_unavailable")

        self.model_service.update_parameters(confidence=confidence, iou=iou)
        self.model_service.get_detector().reset_stats()
        task_id = str(uuid.uuid4())
        self.task_service.create_task(task_id, "webcam", f"camera_{selected['index']}")
        self._webcam_ready_event.clear()
        self._webcam_failure_event.clear()
        self.webcam_state.update(
            {
                "running": True,
                "camera_index": selected["index"],
                "backend": selected["backend_id"],
                "backend_name": selected["backend"],
                "task_id": task_id,
                "started_at": time.time(),
                "frame_count": 0,
                "processed_frames": 0,
                "total_detections": 0,
                "confidence_sum": 0.0,
                "student_behavior_stats": {},
                "teacher_behavior_stats": {},
                "last_error": None,
            }
        )
        with self._lock:
            self.latest_original_frame = None
            self.latest_annotated_frame = None
            self.latest_frame_id = 0
        self._webcam_thread = threading.Thread(target=self._run_webcam_loop, daemon=True)
        self._webcam_thread.start()
        if not self._webcam_ready_event.wait(self.WEBCAM_STARTUP_TIMEOUT):
            message = self.webcam_state.get("last_error") or (
                f"摄像头 {selected['index']} 启动后未在 {self.WEBCAM_STARTUP_TIMEOUT:.1f} 秒内获得首帧"
            )
            self._mark_webcam_failure(message)
            if self._webcam_thread and self._webcam_thread.is_alive():
                self._webcam_thread.join(timeout=2.0)
            raise StreamError(message, code="webcam_unready")
        if self._webcam_failure_event.is_set() or not self.webcam_state["running"]:
            message = self.webcam_state.get("last_error") or f"摄像头 {selected['index']} 未能进入稳定运行状态"
            raise StreamError(message, code="webcam_unready")
        self.logger.info("task_event %s", {
            "task_id": task_id,
            "mode": "webcam",
            "file_name": f"camera_{selected['index']}",
            "status": "processing",
            "processed_frames": 0,
            "total_detections": 0,
            "duration": 0.0,
        })
        return {"task_id": task_id, "camera_index": selected["index"], "backend": selected["backend"]}

    def stop_webcam(self):
        if not self.webcam_state["running"]:
            return {"already_stopped": True}

        self.webcam_state["running"] = False
        if self._webcam_thread and self._webcam_thread.is_alive():
            self._webcam_thread.join(timeout=2.0)
        task_id = self._finalize_webcam_task("completed")
        self._webcam_thread = None
        return {"task_id": task_id} if task_id else {"already_stopped": True}

    def generate_feed(self):
        last_sent_frame_id = -1
        idle_rounds = 0
        while self.webcam_state["running"] or idle_rounds < 10:
            with self._lock:
                frame_bytes = self.latest_annotated_frame
                frame_id = self.latest_frame_id
                running = self.webcam_state["running"]
            if frame_bytes and frame_id != last_sent_frame_id:
                last_sent_frame_id = frame_id
                idle_rounds = 0
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            else:
                idle_rounds = idle_rounds + 1 if not running else 0
                time.sleep(0.1)

    def _run_webcam_loop(self):
        detector = self.model_service.get_detector()
        camera = self._open_capture(self.webcam_state["camera_index"], self.webcam_state.get("backend", cv2.CAP_ANY))
        if not camera.isOpened():
            self._mark_webcam_failure(
                f"摄像头 {self.webcam_state['camera_index']} 无法打开 "
                f"(backend={self.webcam_state.get('backend_name', 'CAP_ANY')})"
            )
            return
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        camera.set(cv2.CAP_PROP_FPS, 30)
        try:
            while self.webcam_state["running"]:
                ok, frame = camera.read()
                if not ok:
                    self._mark_webcam_failure(
                        f"摄像头 {self.webcam_state['camera_index']} 已打开，但无法继续读取画面 "
                        f"(backend={self.webcam_state.get('backend_name', 'CAP_ANY')})"
                    )
                    break

                with self._lock:
                    self.latest_original_frame = frame.copy()

                results = detector.detect_image(frame)
                for det in results["student_detections"]:
                    detector.recent_student_behaviors.append(det["behavior"])
                    self.webcam_state["student_behavior_stats"][det["behavior"]] = self.webcam_state["student_behavior_stats"].get(det["behavior"], 0) + 1
                for det in results["teacher_detections"]:
                    detector.recent_teacher_behaviors.append(det["behavior"])
                    self.webcam_state["teacher_behavior_stats"][det["behavior"]] = self.webcam_state["teacher_behavior_stats"].get(det["behavior"], 0) + 1
                current_frame_index = self.webcam_state["frame_count"] + 1
                timestamp = max(0.0, time.time() - (self.webcam_state["started_at"] or time.time()))
                self.task_service.save_student_detections_bulk(
                    self.webcam_state["task_id"],
                    current_frame_index,
                    timestamp,
                    results["student_detections"],
                )
                self.task_service.save_teacher_detections_bulk(
                    self.webcam_state["task_id"],
                    current_frame_index,
                    timestamp,
                    results["teacher_detections"],
                )
                detection_count = len(results["student_detections"]) + len(results["teacher_detections"])
                confidence_sum = sum(det["confidence"] for det in results["student_detections"]) + sum(
                    det["confidence"] for det in results["teacher_detections"]
                )

                encoded, buffer = cv2.imencode(".jpg", results["annotated_image"])
                if not encoded:
                    continue
                frame_bytes = buffer.tobytes()
                with self._lock:
                    self.latest_annotated_frame = frame_bytes
                    self.latest_frame_id += 1
                    self.webcam_state["frame_count"] += 1
                    self.webcam_state["processed_frames"] += 1
                    self.webcam_state["total_detections"] += detection_count
                    self.webcam_state["confidence_sum"] += confidence_sum
                if not self._webcam_ready_event.is_set():
                    self._webcam_ready_event.set()
        finally:
            camera.release()

    def _mark_webcam_failure(self, message: str):
        self.webcam_state["last_error"] = message
        self._webcam_failure_event.set()
        self.webcam_state["running"] = False
        self._finalize_webcam_task("failed", error_message=message)

    def get_original_frame(self):
        with self._lock:
            frame = None if self.latest_original_frame is None else self.latest_original_frame.copy()
        if frame is None:
            raise RuntimeError("未获取到帧，请确保摄像头已启动")
        ok, jpeg = cv2.imencode(".jpg", frame)
        if not ok:
            raise RuntimeError("转换图片失败")
        return "data:image/jpeg;base64," + base64.b64encode(jpeg.tobytes()).decode("utf-8")

    def get_stats(self):
        stats = self.model_service.get_detector().get_realtime_stats()
        uptime = max(0.0, time.time() - (self.webcam_state["started_at"] or time.time())) if self.webcam_state["running"] else 0.0
        fps = self.webcam_state["frame_count"] / uptime if uptime > 0 else 0.0
        stats["fps"] = fps
        stats["uptime_seconds"] = uptime
        stats["total_detections"] = int(self.webcam_state.get("total_detections", 0))
        stats["camera_index"] = self.webcam_state.get("camera_index")
        stats["backend"] = self.webcam_state.get("backend_name")
        stats["last_error"] = self.webcam_state.get("last_error")
        stats["average_confidence"] = (
            self.webcam_state["confidence_sum"] / self.webcam_state["total_detections"]
            if self.webcam_state.get("total_detections") else 0.0
        )
        return stats

    def get_metrics(self):
        stats = self.get_stats()
        return {
            "fps": stats.get("fps"),
            "eta_seconds": None,
            "total_detections": stats.get("total_detections"),
            "processed_frames": self.webcam_state["processed_frames"],
            "total_frames": self.webcam_state["frame_count"],
            "camera_index": stats.get("camera_index"),
            "backend": stats.get("backend"),
            "last_error": stats.get("last_error"),
            "average_confidence": stats.get("average_confidence"),
        }

    def _persist_latest_webcam_assets(self, task_id: str, camera_index: int):
        with self._lock:
            original_frame = None if self.latest_original_frame is None else self.latest_original_frame.copy()
            annotated_bytes = self.latest_annotated_frame
        if original_frame is not None:
            original_name = f"{task_id}_camera_{camera_index}.jpg"
            original_path = Config.UPLOAD_FOLDER / original_name
            ok, jpeg = cv2.imencode(".jpg", original_frame)
            if ok:
                original_path.write_bytes(jpeg.tobytes())
                self.task_service.save_task_asset(task_id, "original", original_name, media_type="image", file_name=f"camera_{camera_index}")
        if annotated_bytes:
            result_name = f"result_{task_id}_camera_{camera_index}.jpg"
            result_path = Config.OUTPUT_FOLDER / result_name
            result_path.write_bytes(annotated_bytes)
            self.task_service.save_task_asset(task_id, "result", result_name, media_type="image", file_name=f"camera_{camera_index}")

    def _finalize_webcam_task(self, status: str, *, error_message: str | None = None):
        task_id = self.webcam_state.get("task_id")
        if not task_id:
            return None

        camera_index = int(self.webcam_state.get("camera_index", 0) or 0)
        frame_count = int(self.webcam_state.get("frame_count", 0) or 0)
        total_detections = int(self.webcam_state.get("total_detections", 0) or 0)
        confidence_sum = float(self.webcam_state.get("confidence_sum", 0.0) or 0.0)
        started_at = self.webcam_state.get("started_at") or time.time()
        duration = max(0.0, time.time() - started_at)
        average_confidence = (confidence_sum / total_detections) if total_detections else 0.0
        student_stats = dict(self.webcam_state.get("student_behavior_stats") or {})
        teacher_stats = dict(self.webcam_state.get("teacher_behavior_stats") or {})

        if error_message:
            self.webcam_state["last_error"] = error_message

        self._persist_latest_webcam_assets(task_id, camera_index)
        self.task_service.save_summary(
            task_id,
            student_stats,
            teacher_stats,
            total_detections,
            average_confidence,
            duration,
        )
        self.task_service.update_status(task_id, status, frame_count, frame_count)
        log_payload = {
            "task_id": task_id,
            "mode": "webcam",
            "file_name": f"camera_{camera_index}",
            "status": status,
            "processed_frames": frame_count,
            "total_detections": total_detections,
            "duration": round(duration, 3),
        }
        if error_message:
            log_payload["error"] = error_message
        self.logger.info("task_event %s", log_payload)
        self.webcam_state.update({
            "running": False,
            "task_id": None,
            "started_at": None,
            "frame_count": 0,
            "processed_frames": 0,
            "total_detections": 0,
            "confidence_sum": 0.0,
            "student_behavior_stats": {},
            "teacher_behavior_stats": {},
        })
        return task_id

    def diagnose_webcam(self, preferred_index: int = 0) -> Dict[str, Any]:
        attempts = []
        deadline = time.time() + self.PROBE_DIAGNOSTIC_TIMEOUT
        indexes = self._candidate_indexes(preferred_index)
        for index_pos, index in enumerate(indexes):
            backends = self._candidate_backends(index_pos == 0)
            for backend_name, backend_id in backends:
                if time.time() >= deadline:
                    return {"selected": None, "attempts": attempts}
                result = self._probe_camera(index, backend_name, backend_id)
                attempts.append(result)
                if result["success"]:
                    return {"selected": result, "attempts": attempts}
        return {"selected": None, "attempts": attempts}

    @staticmethod
    def _candidate_indexes(preferred_index: int) -> List[int]:
        ordered = [preferred_index] + [idx for idx in range(StreamService.PROBE_INDEX_LIMIT) if idx != preferred_index]
        seen = []
        for item in ordered:
            if item not in seen and item >= 0:
                seen.append(item)
        return seen

    @staticmethod
    def _candidate_backends(include_full_scan: bool):
        if include_full_scan:
            return list(StreamService.PROBE_BACKEND_ORDER)
        return list(StreamService.PROBE_BACKEND_ORDER[:2])

    @staticmethod
    def _open_capture(index: int, backend_id: int):
        if backend_id == cv2.CAP_ANY:
            return cv2.VideoCapture(index)
        return cv2.VideoCapture(index, backend_id)

    def _probe_camera(self, index: int, backend_name: str, backend_id: int) -> Dict[str, Any]:
        result = self._probe_camera_subprocess(index, backend_name, backend_id)
        if result is not None:
            return result

        return {
            "index": index,
            "backend": backend_name,
            "backend_id": backend_id,
            "opened": False,
            "read": False,
            "shape": None,
            "success": False,
            "error": f"摄像头 {index} 探测进程无响应 ({backend_name})",
        }

    def _probe_camera_subprocess(self, index: int, backend_name: str, backend_id: int) -> Dict[str, Any] | None:
        probe_code = r"""
import cv2
import json
import sys
import time

index = int(sys.argv[1])
backend_name = sys.argv[2]
backend_id = int(sys.argv[3])
read_attempts = int(sys.argv[4])
read_delay = float(sys.argv[5])
cap = cv2.VideoCapture(index) if backend_id == int(cv2.CAP_ANY) else cv2.VideoCapture(index, backend_id)
result = {
    "index": index,
    "backend": backend_name,
    "backend_id": backend_id,
    "opened": False,
    "read": False,
    "shape": None,
    "success": False,
    "error": None,
}
try:
    result["opened"] = cap.isOpened()
    if not result["opened"]:
        result["error"] = f"摄像头 {index} 无法打开 ({backend_name})"
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    for _ in range(read_attempts):
        ok, frame = cap.read()
        if ok and frame is not None and getattr(frame, "size", 0) > 0:
            result["read"] = True
            result["shape"] = list(frame.shape)
            result["success"] = True
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit(0)
        time.sleep(read_delay)

    result["error"] = f"摄像头 {index} 已打开，但无法读取画面 ({backend_name})"
    print(json.dumps(result, ensure_ascii=False))
except Exception as exc:
    result["error"] = f"{backend_name}: {exc}"
    print(json.dumps(result, ensure_ascii=False))
finally:
    cap.release()
"""
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        command = [
            sys.executable,
            "-c",
            probe_code,
            str(index),
            backend_name,
            str(backend_id),
            str(self.PROBE_READ_ATTEMPTS),
            str(self.PROBE_READ_DELAY),
        ]
        try:
            completed = subprocess.run(
                command,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=self.PROBE_ATTEMPT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return {
                "index": index,
                "backend": backend_name,
                "backend_id": backend_id,
                "opened": False,
                "read": False,
                "shape": None,
                "success": False,
                "error": f"摄像头 {index} 探测超时 ({backend_name})",
            }

        if completed.returncode != 0 and not completed.stdout.strip():
            return {
                "index": index,
                "backend": backend_name,
                "backend_id": backend_id,
                "opened": False,
                "read": False,
                "shape": None,
                "success": False,
                "error": (completed.stderr or completed.stdout or f"{backend_name} 探测失败").strip(),
            }
        try:
            return json.loads(completed.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            return {
                "index": index,
                "backend": backend_name,
                "backend_id": backend_id,
                "opened": False,
                "read": False,
                "shape": None,
                "success": False,
                "error": (completed.stderr or completed.stdout or f"{backend_name} 探测结果无法解析").strip(),
            }

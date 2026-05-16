from __future__ import annotations

import base64
import binascii
import uuid
from pathlib import Path

import cv2
import numpy as np

from classroom_app.core.errors import StreamError
from config import Config


class DetectionOrchestrator:
    def __init__(self, detection_service, stream_service, task_service):
        self.detection_service = detection_service
        self.stream_service = stream_service
        self.task_service = task_service

    def detect_image_file(self, storage, confidence, iou):
        return self.detection_service.detect_image_file(storage, confidence, iou)

    def detect_batch_files(self, files, confidence, iou):
        return self.detection_service.detect_batch_files(files, confidence, iou)

    def start_video_detection(self, storage, confidence, iou, frame_skip):
        return self.detection_service.start_video_detection(storage, confidence, iou, frame_skip)

    def detect_frame_payload(self, image_data):
        return self.detection_service.detect_frame_payload(image_data)

    def create_browser_webcam_session(self):
        task_id = str(uuid.uuid4())
        self.task_service.create_task(task_id, "webcam", "browser_camera")
        return {"task_id": task_id}

    def finalize_browser_webcam_session(self, payload: dict):
        task_id = str(payload.get("task_id") or "").strip()
        if not task_id:
            raise StreamError("缺少浏览器摄像头任务标识", code="webcam_unready", status=400)

        task = self.task_service.get_task(task_id)
        if not task or str(task.get("task_type") or "").lower() != "webcam":
            raise StreamError("浏览器摄像头会话不存在或已失效", code="webcam_unready", status=404)
        if str(task.get("status") or "").lower() != "processing":
            raise StreamError("浏览器摄像头会话已结束，不能重复提交", code="webcam_unready", status=409)

        processed_frames = self._coerce_non_negative_int(payload.get("processed_frames"), "processed_frames")
        total_frames = self._coerce_non_negative_int(
            payload.get("total_frames") if payload.get("total_frames") is not None else processed_frames,
            "total_frames",
        )
        if total_frames < processed_frames:
            self._mark_browser_webcam_failed(
                task_id,
                processed_frames=processed_frames,
                total_frames=total_frames,
                error_message="浏览器摄像头会话帧计数无效",
            )
            raise StreamError("浏览器摄像头会话帧计数无效", code="webcam_unready", status=400)

        summary = {
            "student_behavior_stats": self._coerce_stats_map(payload.get("student_behavior_stats")),
            "teacher_behavior_stats": self._coerce_stats_map(payload.get("teacher_behavior_stats")),
            "total_detections": self._coerce_non_negative_int(payload.get("total_detections"), "total_detections"),
            "average_confidence": self._coerce_non_negative_float(payload.get("average_confidence"), "average_confidence"),
            "duration": self._coerce_non_negative_float(payload.get("duration"), "duration"),
        }
        failure_reason = str(payload.get("failure_reason") or "").strip()
        if failure_reason:
            self._mark_browser_webcam_failed(
                task_id,
                summary=summary,
                processed_frames=processed_frames,
                total_frames=total_frames,
                error_message=failure_reason,
            )
            raise StreamError(failure_reason, code="webcam_unready", status=409)

        if processed_frames < 1:
            self._mark_browser_webcam_failed(
                task_id,
                summary=summary,
                processed_frames=processed_frames,
                total_frames=total_frames,
                error_message="浏览器摄像头会话未产生有效检测帧",
            )
            raise StreamError("浏览器摄像头会话未产生有效检测帧", code="webcam_session_empty", status=409)

        original_image = payload.get("original_image")
        annotated_image = payload.get("annotated_image")

        try:
            original_bytes = self._decode_data_url_image(original_image, "original_image")
            annotated_bytes = self._decode_data_url_image(annotated_image, "annotated_image")
        except StreamError as exc:
            self._mark_browser_webcam_failed(
                task_id,
                summary=summary,
                processed_frames=processed_frames,
                total_frames=total_frames,
                error_message=exc.message,
            )
            raise

        original_name = f"{task_id}_browser_camera.jpg"
        original_path = Config.UPLOAD_FOLDER / original_name
        self._save_image_bytes(original_path, original_bytes)
        self.task_service.save_task_asset(task_id, "original", original_name, media_type="image", file_name="browser_camera")

        result_name = f"result_{task_id}_browser_camera.jpg"
        result_path = Config.OUTPUT_FOLDER / result_name
        self._save_image_bytes(result_path, annotated_bytes)
        self.task_service.save_task_asset(task_id, "result", result_name, media_type="image", file_name="browser_camera")

        self.task_service.save_summary(task_id, **summary)
        self.task_service.update_status(
            task_id,
            "completed",
            processed_frames,
            total_frames,
        )
        return {"task_id": task_id}

    @staticmethod
    def _decode_data_url_image(data_url: str, field_name: str) -> bytes:
        if not data_url:
            raise StreamError(f"{field_name} 缺失", code="webcam_session_invalid_image", status=400)
        payload = data_url.split(",", 1)[1] if "," in data_url else data_url
        try:
            image_bytes = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise StreamError(f"{field_name} 不是有效的 base64 图像", code="webcam_session_invalid_image", status=400) from exc
        if not image_bytes:
            raise StreamError(f"{field_name} 为空图像", code="webcam_session_invalid_image", status=400)
        decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None or getattr(decoded, "size", 0) <= 0:
            raise StreamError(f"{field_name} 无法解码为图像", code="webcam_session_invalid_image", status=400)
        return image_bytes

    @staticmethod
    def _save_image_bytes(path: Path, image_bytes: bytes):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image_bytes)

    def _mark_browser_webcam_failed(
        self,
        task_id: str,
        *,
        summary: dict | None = None,
        processed_frames: int = 0,
        total_frames: int = 0,
        error_message: str,
    ) -> None:
        self.task_service.save_summary(
            task_id,
            **(summary or {
                "student_behavior_stats": {},
                "teacher_behavior_stats": {},
                "total_detections": 0,
                "average_confidence": 0.0,
                "duration": 0.0,
            }),
        )
        self.task_service.update_status(task_id, "failed", processed_frames, total_frames)

    @staticmethod
    def _coerce_stats_map(value) -> dict:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _coerce_non_negative_int(value, label: str) -> int:
        try:
            parsed = int(value or 0)
        except (TypeError, ValueError) as exc:
            raise StreamError(f"{label} 格式错误", code="webcam_unready", status=400) from exc
        if parsed < 0:
            raise StreamError(f"{label} 不能为负数", code="webcam_unready", status=400)
        return parsed

    @staticmethod
    def _coerce_non_negative_float(value, label: str) -> float:
        try:
            parsed = float(value or 0.0)
        except (TypeError, ValueError) as exc:
            raise StreamError(f"{label} 格式错误", code="webcam_unready", status=400) from exc
        if parsed < 0:
            raise StreamError(f"{label} 不能为负数", code="webcam_unready", status=400)
        return parsed

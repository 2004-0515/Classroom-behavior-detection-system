from __future__ import annotations

from typing import Any

from classroom_app.core.summary_metrics import build_summary_payload

class TaskPayloadService:
    def __init__(self, task_service, detection_service, stream_service):
        self.task_service = task_service
        self.detection_service = detection_service
        self.stream_service = stream_service

    def build_task_payload(self, task_id: str, *, include_assets: bool = True, include_live_metrics: bool = True) -> dict[str, Any] | None:
        summary = self.task_service.get_summary(task_id)
        if not summary or not summary.get("task_id"):
            return None
        payload = self._normalize_task_summary(summary)
        if include_assets:
            payload["assets"] = self.task_service.build_result_urls(
                task_id,
                payload.get("file_name"),
                payload.get("task_type"),
            )
        if include_live_metrics:
            payload["live_metrics"] = self._resolve_live_metrics(payload)
            payload = self._overlay_live_metrics(payload)
        return payload

    def build_recent_payloads(self, limit: int) -> list[dict[str, Any]]:
        items = self.task_service.get_recent_tasks(limit)
        payloads = []
        for item in items:
            payload = self._normalize_task_summary(item)
            payload["assets"] = self.task_service.build_result_urls(
                payload.get("task_id"),
                payload.get("file_name"),
                payload.get("task_type"),
            )
            payload["live_metrics"] = self._resolve_live_metrics(payload)
            payloads.append(self._overlay_live_metrics(payload))
        return payloads

    def _normalize_task_summary(self, item: dict[str, Any]) -> dict[str, Any]:
        payload = dict(item or {})
        payload["student_behavior_stats"] = dict(payload.get("student_behavior_stats") or {})
        payload["teacher_behavior_stats"] = dict(payload.get("teacher_behavior_stats") or {})
        payload["total_detections"] = int(payload.get("total_detections") or 0)
        payload["average_confidence"] = float(payload.get("average_confidence") or 0.0)
        payload["duration"] = float(payload.get("duration") or 0.0)
        payload["processed_frames"] = int(payload.get("processed_frames") or 0)
        payload["total_frames"] = int(payload.get("total_frames") or 0)
        payload["display_metrics"] = dict(payload.get("display_metrics") or {})
        payload["derived_metrics"] = dict(payload.get("derived_metrics") or {})
        if not payload["display_metrics"]:
            normalized = build_summary_payload(
                task_type=payload.get("task_type") or "",
                student_behavior_stats=payload["student_behavior_stats"],
                teacher_behavior_stats=payload["teacher_behavior_stats"],
                total_detections=payload["total_detections"],
                average_confidence=payload["average_confidence"],
                duration=payload["duration"],
                processed_frames=payload["processed_frames"],
                total_frames=payload["total_frames"],
                derived_metrics=payload["derived_metrics"] or None,
            )
            payload["display_metrics"] = normalized["display_metrics"]
            payload["derived_metrics"] = normalized["derived_metrics"]
        return payload

    def _resolve_live_metrics(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if payload.get("status") != "processing":
            return None
        task_type = payload.get("task_type")
        task_id = payload.get("task_id")
        if task_type == "video":
            try:
                return self.detection_service.get_video_metrics(task_id)
            except Exception:
                return None
        if task_type == "webcam":
            try:
                if self.stream_service.webcam_state.get("task_id") != task_id:
                    return None
                return self.stream_service.get_metrics()
            except Exception:
                return None
        return None

    def _overlay_live_metrics(self, payload: dict[str, Any]) -> dict[str, Any]:
        metrics = payload.get("live_metrics") or {}
        if not metrics:
            return payload
        merged = dict(payload)
        for key in (
            "processed_frames",
            "total_frames",
            "total_detections",
            "average_confidence",
            "duration",
            "display_metrics",
            "derived_metrics",
            "fps",
            "eta_seconds",
            "camera_index",
            "backend",
            "last_error",
        ):
            if key in metrics and metrics.get(key) is not None:
                merged[key] = metrics.get(key)
        return merged

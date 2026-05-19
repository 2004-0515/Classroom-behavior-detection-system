from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from werkzeug.utils import secure_filename

from classroom_app.core.errors import InputError, MediaError, TaskExecutionError
from classroom_app.core.summary_metrics import SummaryAccumulator, build_summary_payload
from config import Config
from scripts.runtime_paths import resolve_ffmpeg


class DetectionService:
    def __init__(self, model_service, task_service, config_service, session_manager):
        self.model_service = model_service
        self.task_service = task_service
        self.config_service = config_service
        self.session_manager = session_manager
        self.logger = logging.getLogger(__name__)
        self.ffmpeg_path = resolve_ffmpeg()
        self._browser_tracking_sessions = {}
        self._browser_tracking_lock = threading.Lock()

    def allowed_file(self, filename):
        return "." in filename and filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS

    def is_video_file(self, filename):
        return "." in filename and filename.rsplit(".", 1)[1].lower() in {"mp4", "avi", "mov", "mkv"}

    def _update_detector_params(self, confidence, iou):
        self.model_service.update_parameters(confidence=confidence, iou=iou)

    def detect_image_file(self, storage, confidence, iou):
        if not storage or storage.filename == "":
            raise InputError("未选择文件", code="missing_file")
        if not self.allowed_file(storage.filename):
            raise InputError("不支持的文件格式", code="unsupported_file")

        task_id = str(uuid.uuid4())
        filename = secure_filename(storage.filename)
        input_path = os.path.join(Config.UPLOAD_FOLDER, f"{task_id}_{filename}")
        storage.save(input_path)
        self.task_service.create_task(task_id, "image", filename)
        self.task_service.save_task_asset(task_id, "original", Path(input_path).name, media_type="image", file_name=filename)
        try:
            image = cv2.imread(input_path)
            if image is None:
                raise MediaError("无法读取图片", code="image_read_failed")

            self._update_detector_params(confidence, iou)
            detector = self.model_service.get_detector()
            results = detector.detect_image(image)

            output_filename = f"result_{task_id}_{filename}"
            output_path = os.path.join(Config.OUTPUT_FOLDER, output_filename)
            cv2.imwrite(output_path, results["annotated_image"])
            self.task_service.save_task_asset(task_id, "result", output_filename, media_type="image", file_name=filename)

            self._persist_detections(task_id, 0, 0.0, results)
            summary = build_summary_payload(
                task_type="image",
                student_behavior_stats=results["student_behavior_counts"],
                teacher_behavior_stats=results["teacher_behavior_counts"],
                total_detections=len(results["student_detections"]) + len(results["teacher_detections"]),
                average_confidence=self._compute_average_confidence(results),
                duration=0.0,
                processed_frames=1,
                total_frames=1,
            )
            self.task_service.save_summary(task_id, **summary)
            self.task_service.update_status(task_id, "completed", 1, 1)
            self._log_task_event(task_id, "image", filename, "completed", processed_frames=1, total_detections=summary["total_detections"], duration=0.0)
            return self._build_completed_task_result(task_id, "image")
        except Exception as exc:
            self._mark_task_failed(
                task_id,
                "image",
                filename,
                processed_frames=0,
                total_frames=1,
                student_behavior_stats={},
                teacher_behavior_stats={},
                total_detections=0,
                average_confidence=0.0,
                duration=0.0,
                error=exc,
            )
            raise

    def detect_batch_files(self, files, confidence, iou):
        valid_files = [file for file in files if file and file.filename]
        if not valid_files:
            raise InputError("未选择文件", code="missing_files")
        unsupported_files = [file.filename for file in valid_files if not self.allowed_file(file.filename)]
        if unsupported_files:
            raise InputError(f"不支持的文件格式: {unsupported_files[0]}", code="unsupported_file")

        task_id = str(uuid.uuid4())
        self._update_detector_params(confidence, iou)
        detector = self.model_service.get_detector()
        self.task_service.create_task(task_id, "batch", f"{len(valid_files)} images")

        total_student_counts = defaultdict(int)
        total_teacher_counts = defaultdict(int)
        confidence_sum = 0.0
        total_detections = 0
        processed_frames = 0
        try:
            for idx, file in enumerate(valid_files):
                filename = secure_filename(file.filename)
                input_path = os.path.join(Config.UPLOAD_FOLDER, f"{task_id}_{idx}_{filename}")
                file.save(input_path)
                self.task_service.save_task_asset(task_id, "original", Path(input_path).name, media_type="image", frame_number=idx, file_name=filename)
                image = cv2.imread(input_path)
                if image is None:
                    raise MediaError(f"无法读取图片: {filename}", code="image_read_failed")

                result = detector.detect_image(image)
                output_filename = f"result_{task_id}_{idx}_{filename}"
                output_path = os.path.join(Config.OUTPUT_FOLDER, output_filename)
                cv2.imwrite(output_path, result["annotated_image"])
                self.task_service.save_task_asset(task_id, "result", output_filename, media_type="image", frame_number=idx, file_name=filename)

                self._persist_detections(task_id, idx, 0.0, result)
                for behavior, count in result["student_behavior_counts"].items():
                    total_student_counts[behavior] += count
                for behavior, count in result["teacher_behavior_counts"].items():
                    total_teacher_counts[behavior] += count
                for item in result["student_detections"]:
                    confidence_sum += item["confidence"]
                    total_detections += 1
                for item in result["teacher_detections"]:
                    confidence_sum += item["confidence"]
                    total_detections += 1
                processed_frames += 1

            summary = build_summary_payload(
                task_type="batch",
                student_behavior_stats=dict(total_student_counts),
                teacher_behavior_stats=dict(total_teacher_counts),
                total_detections=total_detections,
                average_confidence=(confidence_sum / total_detections) if total_detections else 0.0,
                duration=0.0,
                processed_frames=len(valid_files),
                total_frames=len(valid_files),
            )
            self.task_service.save_summary(task_id, **summary)
            self.task_service.update_status(task_id, "completed", len(valid_files), len(valid_files))
            self._log_task_event(task_id, "batch", f"{len(valid_files)} images", "completed", processed_frames=len(valid_files), total_detections=summary["total_detections"], duration=0.0)
            return self._build_completed_task_result(task_id, "batch")
        except Exception as exc:
            self._mark_task_failed(
                task_id,
                "batch",
                f"{len(valid_files)} images",
                processed_frames=processed_frames,
                total_frames=len(valid_files),
                student_behavior_stats=dict(total_student_counts),
                teacher_behavior_stats=dict(total_teacher_counts),
                total_detections=total_detections,
                average_confidence=(confidence_sum / total_detections) if total_detections else 0.0,
                duration=0.0,
                error=exc,
            )
            raise

    def start_video_detection(self, storage, confidence, iou, frame_skip):
        if not storage or storage.filename == "" or not self.is_video_file(storage.filename):
            raise InputError("请上传视频文件", code="invalid_video_input")

        task_id = str(uuid.uuid4())
        filename = secure_filename(storage.filename)
        input_path = os.path.join(Config.UPLOAD_FOLDER, f"{task_id}_{filename}")
        output_filename = f"result_{task_id}_{filename}"
        output_path = os.path.join(Config.OUTPUT_FOLDER, output_filename)
        storage.save(input_path)

        self._update_detector_params(confidence, iou)
        self.task_service.create_task(task_id, "video", filename)
        self.task_service.save_task_asset(task_id, "original", Path(input_path).name, media_type="video", file_name=filename)
        stats_holder = {
            "task_id": task_id,
            "total_frames": 0,
            "processed_frames": 0,
            "student_behavior_stats": {},
            "teacher_behavior_stats": {},
            "total_detections": 0,
            "average_confidence": 0.0,
            "duration": 0.0,
            "fps": 0.0,
            "eta_seconds": None,
        }
        session = self.session_manager.create_video_session(task_id, input_path, output_path, output_filename, filename, stats_holder)
        self._log_task_event(task_id, "video", filename, "processing", processed_frames=0, total_detections=0, duration=0.0)

        thread = threading.Thread(
            target=self._process_video_task,
            args=(task_id, session, frame_skip),
            daemon=True,
        )
        thread.start()

        return {
            "task_id": task_id,
            "mode": "video",
            "stream_url": f"/api/streams/video/{task_id}/feed",
            "metrics_url": f"/api/streams/video/{task_id}/metrics",
        }

    def _process_video_task(self, task_id, session, frame_skip):
        tracking_runtime = self.model_service.get_detector().create_tracking_runtime()
        cap = None
        writer = None
        accumulator = SummaryAccumulator("video")
        start_time = time.time()
        frame_index = 0
        processed_frames = 0
        raw_output_path = str(Path(session.output_path).with_suffix(".tracking.mp4"))

        try:
            cap = cv2.VideoCapture(session.input_path)
            if not cap.isOpened():
                raise TaskExecutionError("无法打开视频文件", code="video_open_failed")

            fps = cap.get(cv2.CAP_PROP_FPS) or 25
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            writer = cv2.VideoWriter(raw_output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
            session.stats["total_frames"] = total_frames

            while True:
                if session.stop_event.is_set():
                    break
                ok, frame = cap.read()
                if not ok:
                    break
                frame_index += 1
                session.latest_original_frame = frame.copy()
                session.latest_processed_frame_number = frame_index

                if frame_skip and frame_index % (frame_skip + 1) != 0:
                    writer.write(frame)
                    continue

                results = tracking_runtime.detect_image(frame)
                self._persist_detections(task_id, frame_index, frame_index / fps if fps else 0.0, results)
                processed_frames += 1
                accumulator.update_frame(
                    frame_index,
                    student_detections=results["student_detections"],
                    teacher_detections=results["teacher_detections"],
                )

                annotated = results["annotated_image"]
                writer.write(annotated)

                encoded, buffer = cv2.imencode(".jpg", annotated)
                if encoded:
                    if session.frame_queue.full():
                        try:
                            session.frame_queue.get_nowait()
                        except Exception:
                            pass
                    session.frame_queue.put_nowait(buffer.tobytes())

                session.stats["processed_frames"] = processed_frames
                elapsed = max(0.001, time.time() - start_time)
                session.stats["fps"] = processed_frames / elapsed
                remaining = max(0, total_frames - frame_index)
                session.stats["eta_seconds"] = remaining / session.stats["fps"] if session.stats["fps"] else None
                session.stats.update(
                    accumulator.build_payload(
                        processed_frames=processed_frames,
                        total_frames=total_frames,
                        duration=elapsed,
                    )
                )

            duration = time.time() - start_time
            summary = accumulator.build_payload(
                processed_frames=processed_frames,
                total_frames=total_frames,
                duration=duration,
            )
            session.stats.update(summary)
            session.stats["fps"] = processed_frames / duration if duration > 0 else 0.0
            session.stats["eta_seconds"] = 0.0 if not session.stop_event.is_set() else None
            if writer is not None:
                writer.release()
                writer = None
            self._finalize_video_output(raw_output_path, session.output_path)
            self.task_service.save_task_asset(task_id, "result", session.output_filename, media_type="video", file_name=session.filename)
            self.task_service.save_summary(task_id, **summary)
            final_status = Config.VIDEO_STOP_STATUS if session.stop_event.is_set() else "completed"
            self.task_service.update_status(
                task_id,
                final_status,
                processed_frames,
                session.stats["total_frames"],
            )
            self._log_task_event(task_id, "video", session.filename, final_status, processed_frames=processed_frames, total_detections=summary["total_detections"], duration=duration)
        except Exception as exc:
            self.logger.exception("video_task_failed task_id=%s file=%s", task_id, session.filename)
            self.task_service.update_status(task_id, "failed", processed_frames, session.stats.get("total_frames", 0))
            self._log_task_event(task_id, "video", session.filename, "failed", processed_frames=processed_frames, total_detections=session.stats.get("total_detections", 0), duration=time.time() - start_time, error=str(exc))
        finally:
            if cap is not None:
                cap.release()
            if writer is not None:
                writer.release()
            if Path(raw_output_path).exists() and Path(raw_output_path) != Path(session.output_path):
                try:
                    Path(raw_output_path).unlink()
                except OSError:
                    pass
            session.done_event.set()

    def stop_video_task(self, task_id):
        session = self.session_manager.get_video_session(task_id)
        if not session:
            raise TaskExecutionError("任务不存在或已结束", code="task_not_found", status=404)
        session.stop_event.set()
        stats = session.stats
        self.task_service.update_status(task_id, Config.VIDEO_STOP_STATUS, stats.get("processed_frames", 0), stats.get("total_frames", 0))

    def get_video_metrics(self, task_id):
        session = self.session_manager.get_video_session(task_id)
        if session:
            stats = dict(session.stats)
            stats["stopped"] = session.stop_event.is_set()
            return stats

        task = self.task_service.get_task(task_id)
        if not task:
            raise TaskExecutionError("任务不存在或已结束", code="task_not_found", status=404)
        status = task.get("status")
        if status == "processing":
            raise TaskExecutionError("任务不存在或已结束", code="task_not_found", status=404)
        summary = self.task_service.get_summary(task_id) or {}
        return {
            "processed_frames": task.get("processed_frames", 0),
            "total_frames": task.get("total_frames", 0),
            "total_detections": summary.get("total_detections", 0),
            "average_confidence": summary.get("average_confidence", 0.0),
            "duration": summary.get("duration", 0.0),
            "display_metrics": summary.get("display_metrics") or {},
            "derived_metrics": summary.get("derived_metrics") or {},
            "fps": 0.0,
            "eta_seconds": 0.0 if status == "completed" else None,
            "stopped": status == Config.VIDEO_STOP_STATUS,
        }

    def get_video_stream(self, task_id):
        return self.session_manager.get_video_session(task_id)

    def cleanup_video_stream(self, task_id):
        self.session_manager.cleanup_video_session(task_id)

    def get_video_original_frame(self, task_id):
        stream = self.get_video_stream(task_id)
        if not stream:
            raise TaskExecutionError("任务不存在", code="task_not_found", status=404)

        latest_frame = stream.latest_original_frame
        if latest_frame is not None:
            return self._encode_image_data(latest_frame)

        cap = cv2.VideoCapture(stream.input_path)
        if not cap.isOpened():
            raise MediaError("无法打开视频", code="video_frame_open_failed", status=500)
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            raise MediaError("无法读取帧", code="video_frame_read_failed", status=500)
        return self._encode_image_data(frame)

    def create_browser_tracking_session(self, task_id: str):
        with self._browser_tracking_lock:
            self._browser_tracking_sessions[task_id] = {
                "runtime": self.model_service.get_detector().create_tracking_runtime(),
                "accumulator": SummaryAccumulator("webcam"),
                "started_at": time.time(),
                "processed_frames": 0,
            }

    def pop_browser_tracking_session(self, task_id: str):
        with self._browser_tracking_lock:
            return self._browser_tracking_sessions.pop(task_id, None)

    def get_browser_tracking_session(self, task_id: str):
        with self._browser_tracking_lock:
            return self._browser_tracking_sessions.get(task_id)

    def detect_frame_payload(self, image_data, tracking_session_id=None):
        if not image_data:
            raise InputError("缺少image字段", code="missing_image")
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]
        img_bytes = base64.b64decode(image_data)
        img_np = np.frombuffer(img_bytes, np.uint8)
        image = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
        if image is None:
            raise MediaError("无法解析图片", code="image_decode_failed")

        if tracking_session_id:
            session = self.get_browser_tracking_session(str(tracking_session_id))
            if not session:
                raise TaskExecutionError("浏览器摄像头跟踪会话不存在或已结束", code="task_not_found", status=404)
            result = session["runtime"].detect_image(image)
            session["processed_frames"] += 1
            frame_number = int(session["processed_frames"])
            elapsed = max(0.0, time.time() - float(session["started_at"] or time.time()))
            self._persist_detections(str(tracking_session_id), frame_number, elapsed, result)
            session["accumulator"].update_frame(
                frame_number,
                student_detections=result["student_detections"],
                teacher_detections=result["teacher_detections"],
            )
            summary = session["accumulator"].build_payload(
                processed_frames=frame_number,
                total_frames=frame_number,
                duration=elapsed,
            )
            summary.update(
                {
                    "task_id": str(tracking_session_id),
                    "task_type": "webcam",
                    "status": "processing",
                    "file_name": "browser_camera",
                }
            )
            payload = {
                "summary": summary,
                "processed_frames": frame_number,
            }
        else:
            result = self.model_service.get_detector().detect_image(image)
            payload = {}
        payload.update({
            "annotated_image": self._encode_image_data(result["annotated_image"]),
            "student_detections": result["student_detections"],
            "teacher_detections": result["teacher_detections"],
            "student_behavior_counts": result["student_behavior_counts"],
            "teacher_behavior_counts": result["teacher_behavior_counts"],
        })
        return payload

    def _encode_image_data(self, image):
        ok, buffer = cv2.imencode(".jpg", image)
        if not ok:
            return None
        return "data:image/jpeg;base64," + base64.b64encode(buffer.tobytes()).decode("utf-8")

    def _persist_detections(self, task_id, frame_number, timestamp, results):
        self.task_service.save_student_detections_bulk(
            task_id,
            frame_number,
            timestamp,
            results["student_detections"],
        )
        self.task_service.save_teacher_detections_bulk(
            task_id,
            frame_number,
            timestamp,
            results["teacher_detections"],
        )

    @staticmethod
    def _build_completed_task_result(task_id, mode):
        return {
            "task_id": task_id,
            "mode": mode,
            "status": "completed",
        }

    @staticmethod
    def _compute_average_confidence(results):
        confidences = [item["confidence"] for item in results["student_detections"]] + [item["confidence"] for item in results["teacher_detections"]]
        return float(np.mean(confidences)) if confidences else 0.0

    def _finalize_video_output(self, raw_output_path: str, final_output_path: str):
        raw_path = Path(raw_output_path)
        final_path = Path(final_output_path)
        if not raw_path.exists():
            raise TaskExecutionError("视频处理中间产物不存在", code="video_output_missing", status=500)
        if final_path.exists():
            final_path.unlink()
        if self.ffmpeg_path:
            command = [
                str(self.ffmpeg_path),
                "-y",
                "-i",
                str(raw_path),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                str(final_path),
            ]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode != 0:
                raise TaskExecutionError(
                    f"视频转码失败: {result.stderr.strip() or result.stdout.strip() or '未知错误'}",
                    code="video_transcode_failed",
                    status=500,
                )
        else:
            raw_path.replace(final_path)
        probe = cv2.VideoCapture(str(final_path))
        opened = probe.isOpened()
        frame_count = int(probe.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(probe.get(cv2.CAP_PROP_FPS) or 0.0)
        probe.release()
        if not opened or frame_count <= 0 or fps <= 0:
            raise TaskExecutionError("结果视频元数据无效，无法用于浏览器预览", code="video_output_invalid", status=500)
        if raw_path.exists() and raw_path != final_path:
            raw_path.unlink(missing_ok=True)

    def _mark_task_failed(
        self,
        task_id,
        mode,
        file_name,
        *,
        processed_frames,
        total_frames,
        student_behavior_stats,
        teacher_behavior_stats,
        total_detections,
        average_confidence,
        duration,
        error,
    ):
        try:
            summary = build_summary_payload(
                task_type=mode,
                student_behavior_stats=student_behavior_stats,
                teacher_behavior_stats=teacher_behavior_stats,
                total_detections=total_detections,
                average_confidence=average_confidence,
                duration=duration,
                processed_frames=processed_frames,
                total_frames=total_frames,
            )
            self.task_service.save_summary(task_id, **summary)
            self.task_service.update_status(task_id, "failed", processed_frames, total_frames)
            self._log_task_event(
                task_id,
                mode,
                file_name,
                "failed",
                processed_frames=processed_frames,
                total_detections=summary["total_detections"],
                duration=duration,
                error=getattr(error, "message", str(error)),
            )
        except Exception:
            self.logger.exception("failed_to_persist_task_failure task_id=%s file=%s", task_id, file_name)

    def _log_task_event(self, task_id, mode, file_name, status, *, processed_frames, total_detections, duration, error=None):
        payload = {
            "task_id": task_id,
            "mode": mode,
            "file_name": file_name,
            "status": status,
            "processed_frames": processed_frames,
            "total_detections": total_detections,
            "duration": round(float(duration or 0.0), 3),
        }
        if error:
            payload["error"] = error
        self.logger.info("task_event %s", payload)

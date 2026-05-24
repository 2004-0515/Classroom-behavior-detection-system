from __future__ import annotations

import queue
import time

from flask import Blueprint, Response, current_app, jsonify, request
from flask_login import login_required

from classroom_app.core.errors import AppError
from config import Config
from classroom_app.core.api import api_error, api_error_from_exception, api_success

bp = Blueprint("streams", __name__, url_prefix="/api/streams")


def _services():
    return current_app.extensions["services"]


def _internal_error(message: str, code: str, exc: Exception):
    current_app.logger.exception("%s: %s", code, exc)
    return api_error(message, code=code, status=500)


@bp.route("/video/<task_id>/stop", methods=["POST"])
@login_required
def stop_video(task_id):
    try:
        result = _services().detect.stop_video_task(task_id) or {}
        message = "视频任务已处于停止态" if result.get("already_stopped") else "已请求停止视频检测"
        return api_success(result, message)
    except AppError as exc:
        return api_error_from_exception(exc)


@bp.route("/video/<task_id>/metrics")
@login_required
def video_metrics(task_id):
    try:
        return api_success(_services().detect.get_video_metrics(task_id))
    except AppError as exc:
        return api_error_from_exception(exc)


@bp.route("/video/<task_id>/original-frame")
@login_required
def video_original_frame(task_id):
    try:
        return api_success({"image": _services().detect.get_video_original_frame(task_id)})
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("获取视频原始帧失败，请稍后重试", "video_frame_failed", exc)


@bp.route("/video/<task_id>/feed")
@login_required
def video_feed(task_id):
    detect_service = _services().detect
    stream = detect_service.get_video_stream(task_id)

    def gen():
        if not stream:
            return
        frame_queue = stream.frame_queue
        done_event = stream.done_event
        while True:
            try:
                frame_bytes = frame_queue.get(timeout=0.5)
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            except queue.Empty:
                if done_event.is_set():
                    break
        time.sleep(0.2)
        detect_service.cleanup_video_stream(task_id)

    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


@bp.route("/webcam/start", methods=["POST"])
@login_required
def start_webcam():
    payload = request.get_json(silent=True) or {}
    try:
        result = _services().streams.start_webcam(
            int(payload.get("camera_index", 0)),
            float(payload.get("confidence", Config.DEFAULT_CONF_THRESHOLD)),
            float(payload.get("iou", Config.DEFAULT_IOU_THRESHOLD)),
        )
        return api_success(result, "摄像头已启动")
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("摄像头启动失败，请检查设备或稍后重试", "webcam_start_failed", exc)


@bp.route("/webcam/diagnostics")
@login_required
def webcam_diagnostics():
    try:
        camera_index = int(request.args.get("camera_index", 0))
        return api_success(_services().streams.diagnose_webcam(camera_index))
    except ValueError:
        return api_error("摄像头索引格式错误", status=400)
    except Exception as exc:
        return _internal_error("摄像头诊断失败，请稍后重试", "webcam_diagnostics_failed", exc)


@bp.route("/webcam/stop", methods=["POST"])
@login_required
def stop_webcam():
    try:
        return api_success(_services().streams.stop_webcam(), "摄像头已停止")
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("摄像头停止失败，请稍后重试", "webcam_stop_failed", exc)


@bp.route("/webcam/feed")
@login_required
def webcam_feed():
    return Response(_services().streams.generate_feed(), mimetype="multipart/x-mixed-replace; boundary=frame")


@bp.route("/webcam/original-frame")
@login_required
def webcam_original_frame():
    try:
        return api_success({"image": _services().streams.get_original_frame()})
    except Exception as exc:
        return api_error(str(exc), code="webcam_frame_missing", status=400)


@bp.route("/webcam/stats")
@login_required
def webcam_stats():
    try:
        return jsonify(_services().streams.get_stats())
    except Exception as exc:
        return _internal_error("获取摄像头状态失败，请稍后重试", "webcam_stats_failed", exc)


@bp.route("/webcam/metrics")
@login_required
def webcam_metrics():
    try:
        return api_success(_services().streams.get_metrics())
    except Exception as exc:
        return _internal_error("获取摄像头指标失败，请稍后重试", "webcam_metrics_failed", exc)


@bp.route("/webcam/browser-session/start", methods=["POST"])
@login_required
def start_browser_webcam_session():
    try:
        return api_success(_services().orchestrator.create_browser_webcam_session(), "浏览器摄像头会话已创建")
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("浏览器摄像头会话创建失败，请稍后重试", "browser_webcam_start_failed", exc)


@bp.route("/webcam/browser-session/stop", methods=["POST"])
@login_required
def stop_browser_webcam_session():
    try:
        payload = request.get_json(silent=True) or {}
        return api_success(_services().orchestrator.finalize_browser_webcam_session(payload), "浏览器摄像头会话已结束")
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("浏览器摄像头会话结束失败，请稍后重试", "browser_webcam_stop_failed", exc)

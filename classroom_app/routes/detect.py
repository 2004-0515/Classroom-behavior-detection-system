from __future__ import annotations

from flask import Blueprint, current_app, request
from flask_login import login_required

from classroom_app.core.errors import AppError
from config import Config
from classroom_app.core.api import api_error, api_error_from_exception, api_success

bp = Blueprint("detect", __name__, url_prefix="/api/detect")


def _services():
    return current_app.extensions["services"]


def _internal_error(message: str, code: str, exc: Exception):
    current_app.logger.exception("%s: %s", code, exc)
    return api_error(message, code=code, status=500)


@bp.route("/image", methods=["POST"])
@login_required
def detect_image():
    try:
        result = _services().orchestrator.detect_image_file(
            request.files.get("file"),
            float(request.form.get("confidence", Config.DEFAULT_CONF_THRESHOLD)),
            float(request.form.get("iou", Config.DEFAULT_IOU_THRESHOLD)),
        )
        return api_success(
            {
                "task_id": result["task_id"],
                "task_type": "image",
                "status": "completed",
            },
            "图片检测完成",
        )
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("图片检测失败，请检查输入文件或稍后重试", "image_detect_failed", exc)


@bp.route("/batch", methods=["POST"])
@login_required
def detect_batch():
    try:
        result = _services().orchestrator.detect_batch_files(
            request.files.getlist("files"),
            float(request.form.get("confidence", Config.DEFAULT_CONF_THRESHOLD)),
            float(request.form.get("iou", Config.DEFAULT_IOU_THRESHOLD)),
        )
        return api_success(
            {
                "task_id": result["task_id"],
                "task_type": "batch",
                "status": "completed",
            },
            "批量检测完成",
        )
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("批量检测失败，请检查输入文件或稍后重试", "batch_detect_failed", exc)


@bp.route("/video", methods=["POST"])
@login_required
def detect_video():
    try:
        result = _services().orchestrator.start_video_detection(
            request.files.get("file"),
            float(request.form.get("confidence", Config.DEFAULT_CONF_THRESHOLD)),
            float(request.form.get("iou", Config.DEFAULT_IOU_THRESHOLD)),
            int(request.form.get("frame_skip", Config.VIDEO_FRAME_SKIP)),
        )
        return api_success(result, "视频检测已开始")
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("视频检测失败，请检查输入文件或稍后重试", "video_detect_failed", exc)


@bp.route("/frame", methods=["POST"])
@login_required
def detect_frame():
    data = request.get_json(silent=True) or {}
    try:
        result = _services().orchestrator.detect_frame_payload(data.get("image"))
        return api_success(result, "帧检测完成")
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("帧检测失败，请稍后重试", "frame_detect_failed", exc)

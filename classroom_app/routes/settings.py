from __future__ import annotations

from flask import Blueprint, current_app, request
from flask_login import login_required

from config import Config
from classroom_app.core.api import api_success

bp = Blueprint("settings", __name__, url_prefix="/api")


def _services():
    return current_app.extensions["services"]


@bp.route("/config")
@login_required
def config_bundle():
    detector = _services().models.get_detector()
    return api_success(
        {
            "student_behaviors": detector.student_classes if detector.student_model else [],
            "teacher_behaviors": detector.teacher_classes if detector.teacher_model else [],
            "student_behaviors_example": Config.STUDENT_BEHAVIORS_EXAMPLE,
            "teacher_behaviors_example": Config.TEACHER_BEHAVIORS_EXAMPLE,
            "default_conf": Config.DEFAULT_CONF_THRESHOLD,
            "default_iou": Config.DEFAULT_IOU_THRESHOLD,
            "default_img_size": Config.DEFAULT_IMG_SIZE,
            "history_recent_limit": Config.HISTORY_RECENT_LIMIT,
            "history_poll_interval_ms": Config.HISTORY_POLL_INTERVAL_MS,
            "task_poll_interval_ms": Config.TASK_POLL_INTERVAL_MS,
            "report_reuse_enabled": Config.REPORT_REUSE_ENABLED,
            "video_stop_status": Config.VIDEO_STOP_STATUS,
            "models_loaded": {
                "student": detector.student_model is not None,
                "teacher": detector.teacher_model is not None,
            },
        }
    )


@bp.route("/user/config")
@login_required
def user_config():
    return api_success({"config": _services().config.get_user_config_bundle()})


@bp.route("/user/config/first-run")
@login_required
def first_run():
    return api_success({"is_first_run": _services().config.is_first_run()})


@bp.route("/user/config/first-run/done", methods=["POST"])
@login_required
def first_run_done():
    _services().config.mark_first_run_done()
    return api_success({}, "首次运行标记已更新")


@bp.route("/user/config/last-models")
@login_required
def last_models():
    return api_success({"last_models": _services().config.get_last_models()})


@bp.route("/user/config/save-models", methods=["POST"])
@login_required
def save_models():
    data = request.get_json(silent=True) or {}
    models = _services().config.save_last_models(data.get("student"), data.get("teacher"))
    return api_success({"last_models": models}, "模型选择已保存")


@bp.route("/user/config/detection-params", methods=["GET", "POST"])
@login_required
def detection_params():
    if request.method == "GET":
        return api_success({"params": _services().config.get_detection_params()})
    payload = request.get_json(silent=True) or {}
    params = _services().config.save_detection_params(
        payload.get("confidence"), payload.get("iou"), payload.get("frame_skip")
    )
    return api_success({"params": params}, "检测参数已保存")


@bp.route("/user/settings", methods=["GET", "POST"])
@login_required
def user_settings():
    if request.method == "GET":
        return api_success({"settings": _services().config.get_ui_settings()})
    payload = request.get_json(silent=True) or {}
    settings = _services().config.save_ui_settings(payload)
    return api_success({"settings": settings}, "设置已保存")


@bp.route("/user/config/reset", methods=["POST"])
@login_required
def reset_config():
    _services().config.reset_user_config()
    return api_success({}, "配置已重置为默认值")

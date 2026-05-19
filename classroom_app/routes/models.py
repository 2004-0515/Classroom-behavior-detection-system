from __future__ import annotations

from flask import Blueprint, current_app, request
from flask_login import login_required

from classroom_app.core.api import api_error, api_error_from_exception, api_success
from classroom_app.core.errors import AppError, InputError

bp = Blueprint("models", __name__, url_prefix="/api/models")


def _services():
    return current_app.extensions["services"]


def _internal_error(message: str, code: str, exc: Exception):
    current_app.logger.exception("%s: %s", code, exc)
    return api_error(message, code=code, status=500)


@bp.route("/scan")
@login_required
def scan_models():
    try:
        models = _services().models.scan_models(force=request.args.get("force") == "1")
        return api_success({"models": models, "total": len(models)})
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("模型列表获取失败，请稍后重试", "model_scan_failed", exc)


@bp.route("/info")
@login_required
def model_info():
    try:
        return api_success(_services().models.get_current_model_info())
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("当前模型信息获取失败，请稍后重试", "model_info_failed", exc)


@bp.route("/load", methods=["POST"])
@login_required
def load_model():
    try:
        payload = request.get_json(silent=True) or {}
        model_type = payload.get("type")
        model_ref = payload.get("model")
        if model_type not in {"student", "teacher"} or not model_ref:
            raise InputError("参数不完整")

        _, model_path = _services().models.load_model(model_type, model_ref)
        return api_success({"path": model_path}, "模型加载成功")
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("模型加载失败，请稍后重试", "model_load_request_failed", exc)

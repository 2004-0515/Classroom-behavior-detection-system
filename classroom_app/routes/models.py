from __future__ import annotations

from flask import Blueprint, current_app, request
from flask_login import login_required

from classroom_app.core.api import api_error_from_exception, api_success
from classroom_app.core.errors import AppError, InputError

bp = Blueprint("models", __name__, url_prefix="/api/models")


def _services():
    return current_app.extensions["services"]


@bp.route("/scan")
@login_required
def scan_models():
    models = _services().models.scan_models(force=request.args.get("force") == "1")
    return api_success({"models": models, "total": len(models)})


@bp.route("/info")
@login_required
def model_info():
    return api_success(_services().models.get_current_model_info())


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

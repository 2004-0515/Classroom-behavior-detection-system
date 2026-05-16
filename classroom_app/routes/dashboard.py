from __future__ import annotations

from flask import Blueprint, current_app, render_template, send_from_directory
from flask_login import current_user, login_required

from config import Config
from classroom_app.core.api import api_success

bp = Blueprint("dashboard", __name__)


def _services():
    return current_app.extensions["services"]


@bp.route("/")
@login_required
def shell():
    return render_template("app_shell.html", username=current_user.username)


@bp.route("/outputs/<path:filename>")
@login_required
def outputs(filename):
    return send_from_directory(Config.OUTPUT_FOLDER, filename)


@bp.route("/uploads/<path:filename>")
@login_required
def uploads(filename):
    return send_from_directory(Config.UPLOAD_FOLDER, filename)


@bp.route("/api/dashboard/overview")
@login_required
def overview():
    recent_tasks = _services().task_payloads.build_recent_payloads(limit=6)
    model_info = _services().models.get_current_model_info()
    return api_success(
        {
            "recent_tasks": recent_tasks,
            "models": model_info,
            "username": current_user.username,
        }
    )

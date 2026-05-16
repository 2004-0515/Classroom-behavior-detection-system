from __future__ import annotations

from flask import Blueprint, current_app, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from classroom_app.core.api import api_error, api_success
from classroom_app.core.auth import AdminUser

bp = Blueprint("auth", __name__)


def _services():
    return current_app.extensions["services"]


@bp.route("/login", methods=["GET", "POST"])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.shell"))

    setup_required = not _services().config.is_admin_configured()
    setup_reason = _services().config.get_admin_setup_reason() if setup_required else None

    if request.method == "POST" and request.form:
        if setup_required:
            return render_template("login.html", error=setup_reason, setup_required=True, setup_reason=setup_reason)
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if _services().config.verify_admin(username, password):
            login_user(AdminUser(username))
            return redirect(url_for("dashboard.shell"))
        return render_template("login.html", error="账号或密码错误", setup_required=False)

    return render_template("login.html", setup_required=setup_required, setup_reason=setup_reason)


@bp.route("/logout")
@login_required
def logout_page():
    logout_user()
    return redirect(url_for("auth.login_page"))


@bp.route("/api/auth/login", methods=["POST"])
def login_api():
    if not _services().config.is_admin_configured():
        return api_error(_services().config.get_admin_setup_reason(), code="setup_required", status=503)
    data = request.get_json(silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")
    if not _services().config.verify_admin(username, password):
        return api_error("账号或密码错误", code="invalid_credentials", status=401)

    login_user(AdminUser(username))
    return api_success({"username": username}, "登录成功")


@bp.route("/api/auth/logout", methods=["POST"])
@login_required
def logout_api():
    logout_user()
    return api_success({}, "已退出登录")


@bp.route("/api/auth/session")
def session_api():
    if not current_user.is_authenticated:
        setup_required = not _services().config.is_admin_configured()
        return api_success(
            {
                "authenticated": False,
                "setup_required": setup_required,
                "setup_reason": _services().config.get_admin_setup_reason() if setup_required else None,
            }
        )
    return api_success({"authenticated": True, "username": current_user.username, "setup_required": False, "setup_reason": None})

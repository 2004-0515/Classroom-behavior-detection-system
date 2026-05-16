from __future__ import annotations

from flask import jsonify

from classroom_app.core.errors import AppError


def api_success(data=None, message="ok", status=200):
    payload = {
        "success": True,
        "message": message,
        "data": data if data is not None else {},
    }
    return jsonify(payload), status


def api_error(message, code="bad_request", status=400, **extra):
    payload = {
        "success": False,
        "message": message,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if extra:
        payload["error"].update(extra)
    return jsonify(payload), status


def api_error_from_exception(exc: AppError, **extra):
    return api_error(exc.message, code=exc.code, status=exc.status, category=exc.category, **extra)

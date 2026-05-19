from __future__ import annotations

from flask import Blueprint, current_app, request
from flask_login import login_required

from classroom_app.core.api import api_error, api_error_from_exception, api_success
from classroom_app.core.errors import AppError
from config import Config

bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")


def _services():
    return current_app.extensions["services"]


def _internal_error(message: str, code: str, exc: Exception):
    current_app.logger.exception("%s: %s", code, exc)
    return api_error(message, code=code, status=500)


def _task_payload_or_404(task_id, *, include_assets=True, include_live_metrics=True):
    payload = _services().task_payloads.build_task_payload(
        task_id,
        include_assets=include_assets,
        include_live_metrics=include_live_metrics,
    )
    if not payload:
        return None, api_error("任务不存在", code="task_not_found", status=404)
    return payload, None


def _collect_reportable_summaries(task_ids):
    items = []
    for task_id in task_ids:
        summary = _services().task_payloads.build_task_payload(task_id, include_assets=True, include_live_metrics=False)
        if not summary or not summary.get("task_id"):
            continue
        items.append(summary)
    return items


@bp.route("/recent")
@login_required
def recent_tasks():
    try:
        limit = request.args.get("limit", Config.HISTORY_RECENT_LIMIT, type=int)
        return api_success({"tasks": _services().task_payloads.build_recent_payloads(limit)})
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("任务历史获取失败，请稍后重试", "recent_tasks_failed", exc)


@bp.route("/<task_id>")
@login_required
def task_detail(task_id):
    try:
        task, error = _task_payload_or_404(task_id)
        if error:
            return error
        return api_success(task)
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("任务详情获取失败，请稍后重试", "task_detail_failed", exc)


@bp.route("/<task_id>/summary")
@login_required
def task_summary(task_id):
    try:
        summary, error = _task_payload_or_404(task_id)
        if error:
            return error
        return api_success(summary)
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("任务摘要获取失败，请稍后重试", "task_summary_failed", exc)


@bp.route("/<task_id>/detections")
@login_required
def task_detections(task_id):
    try:
        task = _services().tasks.get_task(task_id)
        if not task:
            return api_error("任务不存在", code="task_not_found", status=404)
        frame_number = request.args.get("frame_number", type=int)
        return api_success(_services().tasks.get_task_detections(task_id, frame_number))
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("检测明细获取失败，请稍后重试", "task_detections_failed", exc)


@bp.route("/<task_id>/report")
@login_required
def task_report(task_id):
    try:
        summary = _services().task_payloads.build_task_payload(task_id, include_assets=True, include_live_metrics=False)
        if not summary or not summary.get("task_id"):
            return api_error("任务不存在或数据不完整", code="task_not_found", status=404)
        report = _services().reports.ensure_task_report(summary)
        return api_success(
            {"report_url": report["report_url"], "report_filename": report["report_filename"]},
            "报告已就绪",
        )
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("任务报告生成失败，请稍后重试", "task_report_failed", exc)


@bp.route("/reports/batch", methods=["POST"])
@login_required
def batch_task_reports():
    try:
        payload = request.get_json(silent=True) or {}
        task_ids = payload.get("task_ids") or []
        if not isinstance(task_ids, list):
            return api_error("任务列表格式错误", code="bad_request", status=400)
        unique_task_ids = [str(task_id) for task_id in dict.fromkeys(task_ids) if task_id]
        if not unique_task_ids:
            return api_error("请先选择要导出的任务", code="bad_request", status=400)

        summaries = _collect_reportable_summaries(unique_task_ids)
        if len(summaries) != len(unique_task_ids):
            return api_error("存在不存在的任务，无法导出报告", code="task_not_found", status=404)
        if not summaries:
            return api_error("没有可导出的报告任务", code="task_not_found", status=404)

        bundle = _services().reports.build_batch_bundle(summaries)
        return api_success(bundle, "批量报告已生成")
    except AppError as exc:
        return api_error_from_exception(exc)
    except Exception as exc:
        return _internal_error("批量报告生成失败，请稍后重试", "batch_reports_failed", exc)

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime
from io import StringIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from classroom_app.core.errors import ReportError
from config import Config
from utils.report_generator import ReportGenerator


class ReportService:
    REPORTABLE_STATUSES = {"completed", "failed", Config.VIDEO_STOP_STATUS}
    REPORT_META_SUFFIX = ".meta.json"

    def __init__(self, task_service):
        self.task_service = task_service
        self._lock_guard = threading.Lock()
        self._task_locks: dict[str, threading.Lock] = {}

    def ensure_task_report(self, summary: dict) -> dict:
        normalized = self._normalize_summary(summary)
        asset_manifest = self._validate_report_summary(normalized)
        task_id = normalized["task_id"]
        fingerprint = self._build_report_fingerprint(normalized, asset_manifest)
        report_filename = self.build_report_filename(normalized)
        report_path = Config.OUTPUT_FOLDER / report_filename
        meta_path = self.build_report_metadata_path(report_path)

        with self._get_task_lock(task_id):
            if self._can_reuse_report(report_path, meta_path, fingerprint):
                self.task_service.save_task_asset(task_id, "report", report_filename, media_type="html", file_name=report_filename)
                return {
                    "report_filename": report_filename,
                    "report_path": report_path,
                    "report_url": f"/outputs/{report_filename}",
                    "fingerprint": fingerprint,
                    "reused": True,
                }

            self._generate_report_atomically(normalized, report_path, meta_path, fingerprint, asset_manifest)
            self.task_service.save_task_asset(task_id, "report", report_filename, media_type="html", file_name=report_filename)
            return {
                "report_filename": report_filename,
                "report_path": report_path,
                "report_url": f"/outputs/{report_filename}",
                "fingerprint": fingerprint,
                "reused": False,
            }

    def build_batch_bundle(self, summaries: list[dict]) -> dict:
        normalized_entries = []
        for summary in summaries:
            report_entry = self.ensure_task_report(summary)
            normalized_entries.append(
                {
                    "summary": self._normalize_summary(summary),
                    "report_filename": report_entry["report_filename"],
                    "report_path": report_entry["report_path"],
                }
            )

        bundle_name = f"reports-batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        bundle_path = Config.OUTPUT_FOLDER / bundle_name
        temp_bundle_path = self._create_temp_path(bundle_path)
        manifest_files = self._build_batch_manifest(normalized_entries, bundle_name)

        try:
            self.write_batch_archive(temp_bundle_path, normalized_entries, manifest_files)
            self._validate_batch_archive(temp_bundle_path, normalized_entries, manifest_files)
            temp_bundle_path.replace(bundle_path)
        except ReportError:
            self._cleanup_temp_paths(temp_bundle_path)
            raise
        except Exception as exc:
            self._cleanup_temp_paths(temp_bundle_path)
            raise ReportError(f"批量报告打包失败: {exc}", code="report_bundle_failed", status=500)

        return {
            "zip_url": f"/outputs/{bundle_name}",
            "zip_filename": bundle_name,
            "report_count": len(normalized_entries),
        }

    def render_html_report(self, summary: dict, output_path: Path) -> Path:
        return Path(ReportGenerator.generate_html_report(summary, output_path))

    def write_batch_archive(self, bundle_path: Path, entries: list[dict], manifest_files: dict[str, str]) -> None:
        with ZipFile(bundle_path, "w", compression=ZIP_DEFLATED) as archive:
            for entry in entries:
                archive.write(entry["report_path"], arcname=entry["report_filename"])
            for arcname, content in manifest_files.items():
                archive.writestr(arcname, content)

    @staticmethod
    def build_report_filename(summary: dict) -> str:
        task_id = str(summary.get("task_id", "unknown"))
        task_type = str(summary.get("task_type", "task") or "task").strip().lower()
        file_name = str(summary.get("file_name", "unnamed") or "unnamed")
        stem = Path(file_name).stem or "unnamed"
        safe_stem = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in stem).strip("-._") or "unnamed"
        return f"report-{task_type}-{safe_stem}-{task_id[:8]}.html"

    @classmethod
    def build_report_metadata_path(cls, report_path: Path) -> Path:
        return report_path.with_name(report_path.name + cls.REPORT_META_SUFFIX)

    def _generate_report_atomically(self, summary: dict, report_path: Path, meta_path: Path, fingerprint: str, asset_manifest: list[dict]) -> None:
        temp_report_path = self._create_temp_path(report_path)
        temp_meta_path = self._create_temp_path(meta_path)
        try:
            generated_report_path = self.render_html_report(summary, temp_report_path)
            if Path(generated_report_path) != temp_report_path:
                temp_report_path = Path(generated_report_path)
            self._assert_nonempty_file(temp_report_path, "报告 HTML")
            report_sha256 = self._sha256_file(temp_report_path)

            metadata = {
                "task_id": summary["task_id"],
                "task_type": summary["task_type"],
                "report_filename": report_path.name,
                "fingerprint": fingerprint,
                "template_version": ReportGenerator.TEMPLATE_VERSION,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "report_sha256": report_sha256,
                "assets": asset_manifest,
            }
            self._write_json(temp_meta_path, metadata)
            self._assert_nonempty_file(temp_meta_path, "报告元数据")

            temp_meta_path.replace(meta_path)
            temp_report_path.replace(report_path)
        except ReportError:
            self._cleanup_temp_paths(temp_report_path, temp_meta_path)
            raise
        except Exception as exc:
            self._cleanup_temp_paths(temp_report_path, temp_meta_path)
            raise ReportError(f"报告生成失败: {exc}", code="report_generation_failed", status=500)

    def _can_reuse_report(self, report_path: Path, meta_path: Path, fingerprint: str) -> bool:
        if not report_path.exists() or not meta_path.exists():
            return False
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        if metadata.get("fingerprint") != fingerprint:
            return False
        if metadata.get("template_version") != ReportGenerator.TEMPLATE_VERSION:
            return False
        if metadata.get("report_sha256") != self._sha256_file(report_path):
            return False
        return True

    def _validate_report_summary(self, summary: dict) -> list[dict]:
        task_id = str(summary.get("task_id") or "").strip()
        task_type = str(summary.get("task_type") or "").strip().lower()
        status = str(summary.get("status") or "").strip().lower()
        if not task_id or not task_type:
            raise ReportError("任务摘要不完整，无法生成报告", code="report_not_ready", status=409)
        if status not in self.REPORTABLE_STATUSES:
            raise ReportError("任务仍在处理中，报告尚未就绪", code="report_not_ready", status=409)
        assets = summary.get("assets") or {}
        if not isinstance(assets, dict):
            raise ReportError("报告资源信息缺失", code="report_asset_missing", status=500)
        return self._collect_required_assets(task_type, assets)

    def _collect_required_assets(self, task_type: str, assets: dict) -> list[dict]:
        manifest: list[dict] = []
        if task_type == "batch":
            results = assets.get("results") or []
            if not results:
                raise ReportError("批量任务缺少结果资源", code="report_asset_missing", status=500)
            for index, item in enumerate(results):
                result_url = item.get("result")
                original_url = item.get("original")
                if not result_url:
                    raise ReportError("批量任务缺少结果资源", code="report_asset_missing", status=500)
                manifest.append(self._asset_record("result", result_url, frame_number=index))
                if original_url:
                    manifest.append(self._asset_record("original", original_url, frame_number=index))
            return manifest

        result_url = assets.get("result")
        original_url = assets.get("original")
        if not result_url:
            raise ReportError("任务缺少结果资源，无法生成报告", code="report_asset_missing", status=500)
        manifest.append(self._asset_record("result", result_url))
        if original_url:
            manifest.append(self._asset_record("original", original_url))
        return manifest

    def _asset_record(self, role: str, asset_url: str, *, frame_number: int | None = None) -> dict:
        path = self._url_to_path(asset_url)
        if not path.exists() or not path.is_file():
            raise ReportError(f"报告所需资源缺失: {path.name}", code="report_asset_missing", status=500)
        return {
            "role": role,
            "frame_number": frame_number,
            "url": asset_url,
            "path": path.name,
            "size": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
        }

    @staticmethod
    def _url_to_path(asset_url: str) -> Path:
        if not asset_url:
            raise ReportError("报告资源路径为空", code="report_asset_missing", status=500)
        if asset_url.startswith("/outputs/"):
            return Config.OUTPUT_FOLDER / asset_url.removeprefix("/outputs/")
        if asset_url.startswith("/uploads/"):
            return Config.UPLOAD_FOLDER / asset_url.removeprefix("/uploads/")
        raise ReportError("报告资源路径无效", code="report_asset_missing", status=500)

    def _build_report_fingerprint(self, summary: dict, asset_manifest: list[dict]) -> str:
        payload = {
            "template_version": ReportGenerator.TEMPLATE_VERSION,
            "task": {
                "task_id": summary.get("task_id"),
                "task_type": summary.get("task_type"),
                "file_name": summary.get("file_name"),
                "status": summary.get("status"),
                "processed_frames": int(summary.get("processed_frames") or 0),
                "total_frames": int(summary.get("total_frames") or 0),
                "total_detections": int(summary.get("total_detections") or 0),
                "average_confidence": float(summary.get("average_confidence") or 0.0),
                "duration": float(summary.get("duration") or 0.0),
                "student_behavior_stats": summary.get("student_behavior_stats") or {},
                "teacher_behavior_stats": summary.get("teacher_behavior_stats") or {},
                "display_metrics": summary.get("display_metrics") or {},
                "derived_metrics": summary.get("derived_metrics") or {},
            },
            "assets": asset_manifest,
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_summary(summary: dict) -> dict:
        payload = dict(summary or {})
        payload["student_behavior_stats"] = dict(payload.get("student_behavior_stats") or {})
        payload["teacher_behavior_stats"] = dict(payload.get("teacher_behavior_stats") or {})
        payload["assets"] = dict(payload.get("assets") or {})
        payload["display_metrics"] = dict(payload.get("display_metrics") or {})
        payload["derived_metrics"] = dict(payload.get("derived_metrics") or {})
        payload["total_detections"] = int(payload.get("total_detections") or 0)
        payload["average_confidence"] = float(payload.get("average_confidence") or 0.0)
        payload["duration"] = float(payload.get("duration") or 0.0)
        payload["processed_frames"] = int(payload.get("processed_frames") or 0)
        payload["total_frames"] = int(payload.get("total_frames") or 0)
        return payload

    def _build_batch_manifest(self, entries: list[dict], bundle_name: str) -> dict[str, str]:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        csv_buffer = StringIO()
        csv_buffer.write("task_id,task_type,file_name,total_detections,duration_seconds,report_filename\n")
        for entry in entries:
            summary = entry["summary"]
            row = [
                str(summary.get("task_id", "")),
                str(summary.get("task_type", "")),
                str(summary.get("file_name", "")),
                str(int(summary.get("total_detections", 0) or 0)),
                f"{float(summary.get('duration', 0) or 0):.1f}",
                entry["report_filename"],
            ]
            csv_buffer.write(",".join(self._csv_escape(cell) for cell in row) + "\n")

        readme_lines = [
            "课堂行为检测系统 - 批量报告清单",
            f"打包文件: {bundle_name}",
            f"生成时间: {timestamp}",
            f"报告数量: {len(entries)}",
            "",
            "内容说明:",
            "1. 本压缩包包含所选任务的 HTML 报告文件。",
            "2. manifest.csv 记录每份报告对应的任务类型、原文件名、检测数和报告文件名。",
            "",
            "报告列表:",
        ]
        for index, entry in enumerate(entries, start=1):
            summary = entry["summary"]
            readme_lines.append(
                f"{index}. {entry['report_filename']} | {summary.get('task_type', '')} | "
                f"{summary.get('file_name', '')} | 检测数 {int(summary.get('total_detections', 0) or 0)}"
            )
        return {
            "readme.txt": "\n".join(readme_lines),
            "manifest.csv": csv_buffer.getvalue(),
        }

    def _validate_batch_archive(self, bundle_path: Path, entries: list[dict], manifest_files: dict[str, str]) -> None:
        if not bundle_path.exists() or bundle_path.stat().st_size <= 0:
            raise ReportError("批量报告压缩包未生成成功", code="report_bundle_failed", status=500)
        expected_names = {entry["report_filename"] for entry in entries} | set(manifest_files.keys())
        with ZipFile(bundle_path) as archive:
            actual_names = set(archive.namelist())
            if expected_names != actual_names:
                raise ReportError("批量报告压缩包内容不完整", code="report_bundle_failed", status=500)

    @staticmethod
    def _csv_escape(value: str) -> str:
        value = str(value or "")
        if any(ch in value for ch in {",", "\"", "\n"}):
            return '"' + value.replace('"', '""') + '"'
        return value

    def _get_task_lock(self, task_id: str) -> threading.Lock:
        with self._lock_guard:
            lock = self._task_locks.get(task_id)
            if lock is None:
                lock = threading.Lock()
                self._task_locks[task_id] = lock
            return lock

    @staticmethod
    def _create_temp_path(target_path: Path) -> Path:
        temp_name = f"{target_path.name}.{uuid.uuid4().hex}.tmp"
        return target_path.with_name(temp_name)

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _assert_nonempty_file(path: Path, label: str) -> None:
        if not path.exists() or path.stat().st_size <= 0:
            raise ReportError(f"{label}生成失败", code="report_generation_failed", status=500)

    @staticmethod
    def _cleanup_temp_paths(*paths: Path) -> None:
        for path in paths:
            if path and path.exists():
                path.unlink(missing_ok=True)

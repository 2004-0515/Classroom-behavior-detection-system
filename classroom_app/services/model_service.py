from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from config import Config
from classroom_app.core.errors import ModelError
from classroom_app.core.model_integrity import load_manifest, resolve_model_candidate, validate_model_file
from utils.detector import BehaviorDetector

MODEL_SELECTION_SOURCE_LABELS = {
    "env_default": "启动入口默认",
    "env_pin": "环境固定",
    "saved_config": "上次选择",
    "default_config": "默认模型",
    "scanned_preferred": "扫描优先匹配",
    "scanned_fallback": "扫描回退",
    "manual_selection": "手动切换",
}

CHECKPOINT_NAMES = {"best", "last", "final"}


class ModelService:
    def __init__(self, config_service):
        self.config_service = config_service
        self.model_root = Path(Config.MODEL_FOLDER).resolve()
        self._manifest_entries = load_manifest(self.model_root)
        self._scan_cache = {"models": [], "expires_at": 0.0}
        self._load_lock = threading.Lock()
        self._env_selected_models = {
            "student": self._resolve_known_model(self._get_env_model_ref("student")),
            "teacher": self._resolve_known_model(self._get_env_model_ref("teacher")),
        }
        self._env_model_lock_enabled = os.environ.get("MODEL_SELECTION_LOCKED", "0") == "1"
        saved_models = config_service.get_last_models()
        student_model_path, student_selection = self._resolve_initial_model(saved_models.get("student"), "student")
        teacher_model_path, teacher_selection = self._resolve_initial_model(saved_models.get("teacher"), "teacher")
        self._model_selection_meta = {
            "student": student_selection,
            "teacher": teacher_selection,
        }
        student_storage_ref = self._to_storage_reference(student_model_path)
        teacher_storage_ref = self._to_storage_reference(teacher_model_path)
        student_to_save = None
        teacher_to_save = None
        if not self._env_selected_models["student"] and saved_models.get("student") != student_storage_ref:
            student_to_save = student_storage_ref
        if not self._env_selected_models["teacher"] and saved_models.get("teacher") != teacher_storage_ref:
            teacher_to_save = teacher_storage_ref
        if student_to_save or teacher_to_save:
            self.config_service.save_last_models(student_model=student_to_save, teacher_model=teacher_to_save)
        self.detector = BehaviorDetector(
            student_model_path=student_model_path,
            teacher_model_path=teacher_model_path,
            conf_threshold=config_service.get_detection_params().get("confidence", Config.DEFAULT_CONF_THRESHOLD),
            iou_threshold=config_service.get_detection_params().get("iou", Config.DEFAULT_IOU_THRESHOLD),
            img_size=Config.DEFAULT_IMG_SIZE,
        )

    def _resolve_initial_model(self, configured_path, role):
        env_ref = self._get_env_model_ref(role)
        env_path = self._env_selected_models.get(role)
        if env_path:
            source = "env_pin" if self._env_model_lock_enabled else "env_default"
            return env_path, self._build_selection_meta(
                role,
                env_path,
                source,
                requested_ref=env_ref,
                locked=self._env_model_lock_enabled,
            )

        resolved = self._resolve_known_model(configured_path)
        if resolved:
            return resolved, self._build_selection_meta(role, resolved, "saved_config", requested_ref=configured_path)

        default_ref = Config.STUDENT_MODEL_PATH if role == "student" else Config.TEACHER_MODEL_PATH
        default_path = self._resolve_known_model(default_ref)
        if default_path:
            return default_path, self._build_selection_meta(role, default_path, "default_config", requested_ref=default_ref)

        models = self.scan_models(force=True)
        preferred_keywords = ["behavior", "student"] if role == "student" else ["teacher", "head", "heand"]
        for model in models:
            path_lower = model["path"].lower()
            if any(keyword in path_lower for keyword in preferred_keywords):
                return model["path"], self._build_selection_meta(
                    role,
                    model["path"],
                    "scanned_preferred",
                    requested_ref=model.get("relative_path", model["filename"]),
                )
        if models:
            return models[0]["path"], self._build_selection_meta(
                role,
                models[0]["path"],
                "scanned_fallback",
                requested_ref=models[0].get("relative_path", models[0]["filename"]),
            )
        fallback_path = str(Path(default_ref))
        return fallback_path, self._build_selection_meta(role, fallback_path, "default_config", requested_ref=default_ref)

    def scan_models(self, force=False):
        now = time.time()
        if not force and self._scan_cache["expires_at"] > now:
            return self._scan_cache["models"]

        models = BehaviorDetector.scan_models_directory(str(self.model_root))
        for item in models:
            try:
                item["relative_path"] = str(Path(item["path"]).resolve().relative_to(self.model_root)).replace("\\", "/")
            except Exception:
                item["relative_path"] = item["filename"]
            manifest_meta = self._manifest_entries.get(item["relative_path"], {})
            item["sha256"] = manifest_meta.get("sha256")
            item["size_bytes"] = manifest_meta.get("size_bytes")
            item.update(self._build_inventory_meta(item))
        self._annotate_duplicate_groups(models)
        self._scan_cache = {
            "models": sorted(
                models,
                key=lambda item: (
                    0 if item.get("source_group") == "official_model" else 1,
                    item.get("relative_path", item["filename"]).lower(),
                ),
            ),
            "expires_at": now + 30,
        }
        return self._scan_cache["models"]

    def get_detector(self):
        return self.detector

    def get_current_model_info(self):
        return {
            "student": self._build_current_model_info("student"),
            "teacher": self._build_current_model_info("teacher"),
        }

    def update_parameters(self, confidence=None, iou=None, img_size=None):
        self.detector.update_parameters(confidence, iou, img_size)

    def load_model(self, model_type, model_ref):
        with self._load_lock:
            model_path = self._resolve_requested_model(model_ref)
            selected_path = self._env_selected_models.get(model_type)
            if self._env_model_lock_enabled and selected_path and Path(model_path).resolve() != Path(selected_path).resolve():
                role_name = "学生" if model_type == "student" else "教师"
                raise ModelError(f"{role_name}模型已由当前启动入口固定，不能在运行中切换", code="model_locked", status=409)

            current_info = self.detector.get_model_info(model_type)
            current_path = self._resolve_known_model(current_info.get("path") or current_info.get("relative_path"))
            if current_info.get("loaded") and current_path and Path(current_path).resolve() == Path(model_path).resolve():
                return True, model_path

            success = self.detector.load_model(model_type, model_path)
            if not success:
                raise ModelError("模型加载失败", code="model_load_failed", status=500)

            storage_ref = self._to_storage_reference(model_path)
            if self._env_model_lock_enabled and selected_path:
                self._model_selection_meta[model_type] = self._build_selection_meta(
                    model_type,
                    selected_path,
                    "env_pin",
                    requested_ref=self._get_env_model_ref(model_type),
                    locked=True,
                )
            else:
                if model_type == "student":
                    self.config_service.save_last_models(student_model=storage_ref)
                else:
                    self.config_service.save_last_models(teacher_model=storage_ref)
                self._model_selection_meta[model_type] = self._build_selection_meta(
                    model_type,
                    model_path,
                    "manual_selection",
                    requested_ref=storage_ref,
                )
            return True, model_path

    def _resolve_requested_model(self, model_ref):
        candidate, _ = resolve_model_candidate(model_ref, self.model_root)
        validated = validate_model_file(candidate, self.model_root, manifest=self._manifest_entries)
        return str(validated)

    def _resolve_known_model(self, model_ref):
        if not model_ref:
            return None
        normalized_ref = str(model_ref).strip().replace("\\", "/")
        direct_path = Path(normalized_ref)
        if direct_path.is_absolute():
            try:
                resolved = direct_path.resolve()
                resolved.relative_to(self.model_root)
            except Exception:
                return None
            if resolved.exists():
                return str(resolved)
            return None

        candidate = (self.model_root / normalized_ref).resolve()
        try:
            candidate.relative_to(self.model_root)
        except Exception:
            return None
        if candidate.exists():
            return str(candidate)
        return None

    def _get_env_model_ref(self, role):
        return os.environ.get("STUDENT_MODEL_PATH" if role == "student" else "TEACHER_MODEL_PATH")

    def _build_current_model_info(self, role):
        info = self.detector.get_model_info(role)
        info["relative_path"] = self._to_storage_reference(info.get("path"))
        info["display_name"] = self._format_model_display_name(info.get("relative_path") or info.get("path"), role=role)
        info.update(self._model_selection_meta.get(role, {}))
        return info

    def _build_selection_meta(self, role, model_path, source, requested_ref=None, locked=False):
        return {
            "selection_role": role,
            "selection_source": source,
            "selection_source_label": MODEL_SELECTION_SOURCE_LABELS.get(source, source),
            "selection_requested_ref": requested_ref,
            "selection_locked": locked,
            "selection_lock_reason": "当前启动入口已固定该模型" if locked else None,
            "selection_relative_path": self._to_storage_reference(model_path),
        }

    def _to_storage_reference(self, model_path):
        if not model_path:
            return None
        path = Path(model_path)
        try:
            return path.resolve().relative_to(self.model_root).as_posix()
        except Exception:
            return str(path)

    @staticmethod
    def _slug_part(value: str) -> str:
        return (
            str(value or "")
            .strip()
            .replace("\\", "/")
            .split("/")[-1]
            .rsplit(".", 1)[0]
            .replace("_", " ")
            .replace("-", " ")
            .strip()
        )

    def _format_model_display_name(self, value: str | None, role: str = "") -> str:
        relative = str(value or "").replace("\\", "/")
        if not relative:
            return "学生行为模型" if role == "student" else "人头检测模型" if role == "teacher" else "检测模型"
        compact = relative.lower()
        parts = [self._slug_part(item) for item in relative.split("/") if item and item.lower() not in {"weights"}]
        parts = [item for item in parts if item]
        raw_parts = [item.lower() for item in relative.split("/") if item]
        is_checkpoint_path = Path(relative).stem.lower() in CHECKPOINT_NAMES or "weights" in raw_parts or "train" in raw_parts
        if not is_checkpoint_path:
            if "behavior" in compact or "student" in compact:
                return "学生行为模型"
            if "teacher" in compact or "head" in compact or "heand" in compact:
                return "人头检测模型"
        if not parts:
            return "检测模型"
        if parts[-1].lower() in CHECKPOINT_NAMES:
            prefix = " · ".join(parts[:-1]) if len(parts) > 1 else "训练"
            return f"{prefix} · {parts[-1]} 检查点"
        return f"{parts[-1]} 模型"

    def _build_inventory_meta(self, item: dict) -> dict:
        relative_path = str(item.get("relative_path") or item.get("filename") or "").replace("\\", "/")
        parts = [part for part in relative_path.split("/") if part]
        stem = Path(relative_path).stem.lower()
        is_checkpoint = stem in CHECKPOINT_NAMES or ("weights" in [part.lower() for part in parts] and "train" in [part.lower() for part in parts])
        source_group = "training_checkpoint" if is_checkpoint else "official_model"
        source_label = "训练检查点" if is_checkpoint else "正式模型"
        source_detail = "来自训练输出目录" if is_checkpoint else "正式候选入口"
        return {
            "source_group": source_group,
            "source_group_label": source_label,
            "source_detail": source_detail,
            "display_name": self._format_model_display_name(relative_path),
            "is_checkpoint": is_checkpoint,
            "checkpoint_name": stem if stem in CHECKPOINT_NAMES else None,
        }

    def _annotate_duplicate_groups(self, models: list[dict]):
        grouped: dict[str, list[dict]] = {}
        for item in models:
            sha256 = str(item.get("sha256") or "").strip()
            if sha256:
                grouped.setdefault(sha256, []).append(item)
        for sha256, items in grouped.items():
            canonical = sorted(
                items,
                key=lambda entry: (
                    0 if entry.get("source_group") == "official_model" else 1,
                    entry.get("relative_path", entry.get("filename", "")).lower(),
                ),
            )[0]
            for item in items:
                item["duplicate_group_id"] = sha256
                item["canonical_relative_path"] = canonical.get("relative_path")
                item["canonical_display_name"] = canonical.get("display_name")
                item["is_duplicate_alias"] = item is not canonical
                item["is_official_entry"] = item.get("source_group") == "official_model"
                item["duplicate_count"] = len(items)
                item["duplicate_note"] = (
                    f"与 {canonical.get('relative_path')} 指向同一模型文件"
                    if len(items) > 1 and item is not canonical
                    else (f"同一模型共有 {len(items)} 个入口" if len(items) > 1 else "")
                )

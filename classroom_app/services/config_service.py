from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from utils.user_config import UserConfig


class ConfigService:
    WEAK_PASSWORD_CANDIDATES = ("123456", "123465", "admin", "admin123", "12345678")
    VALID_DEFAULT_MODES = {"image", "batch", "video", "webcam"}

    def __init__(self):
        self.user_config = UserConfig(Config.USER_CONFIG_PATH)
        self.admin_config_path = Path(Config.ADMIN_CONFIG_PATH)
        self.admin_config = self._load_admin_config()

    def _load_admin_config(self):
        if self.admin_config_path.exists():
            with open(self.admin_config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            if self._is_weak_admin_config(config):
                return {
                    "username": None,
                    "password_hash": None,
                    "created_at": config.get("created_at"),
                    "updated_at": datetime.now().isoformat(),
                    "setup_required": True,
                    "setup_reason": "检测到历史默认弱口令配置，请重新初始化管理员账号",
                }
            return config

        if not Config.DEFAULT_ADMIN_USERNAME or not Config.DEFAULT_ADMIN_PASSWORD:
            return {
                "username": None,
                "password_hash": None,
                "created_at": None,
                "updated_at": None,
                "setup_required": True,
            }

        config = {
            "username": Config.DEFAULT_ADMIN_USERNAME,
            "password_hash": generate_password_hash(Config.DEFAULT_ADMIN_PASSWORD),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "setup_required": False,
        }
        self.admin_config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.admin_config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return config

    def _is_weak_admin_config(self, config) -> bool:
        username = (config.get("username") or "").strip().lower()
        password_hash = config.get("password_hash") or ""
        if not username or not password_hash:
            return False
        if username != "admin":
            return False
        for candidate in self.WEAK_PASSWORD_CANDIDATES:
            try:
                if check_password_hash(password_hash, candidate):
                    return True
            except ValueError:
                continue
        return False

    def save_admin_config(self):
        self.admin_config["updated_at"] = datetime.now().isoformat()
        self.admin_config["setup_required"] = False
        with open(self.admin_config_path, "w", encoding="utf-8") as f:
            json.dump(self.admin_config, f, ensure_ascii=False, indent=2)

    def is_admin_configured(self) -> bool:
        return bool(self.admin_config.get("username") and self.admin_config.get("password_hash"))

    def get_admin_setup_reason(self) -> str:
        return self.admin_config.get("setup_reason") or "管理员账号尚未初始化，请先运行本地初始化脚本"

    def bootstrap_admin(self, username: str, password: str):
        username = (username or "").strip()
        password = password or ""
        if len(username) < 3:
            raise ValueError("管理员账号至少需要 3 个字符")
        if len(password) < 8:
            raise ValueError("管理员密码至少需要 8 个字符")
        self.admin_config = {
            "username": username,
            "password_hash": generate_password_hash(password),
            "created_at": self.admin_config.get("created_at") or datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "setup_required": False,
        }
        self.save_admin_config()
        return {"username": username}

    def verify_admin(self, username: str, password: str) -> bool:
        if not self.is_admin_configured():
            return False
        return (
            username == self.admin_config.get("username")
            and check_password_hash(self.admin_config.get("password_hash", ""), password)
        )

    def get_admin_username(self) -> str:
        return self.admin_config.get("username") or ""

    def get_user_config_bundle(self):
        return self.user_config.config

    def get_detection_params(self):
        return self.user_config.get_detection_params()

    def save_detection_params(self, confidence=None, iou=None, frame_skip=None):
        self.user_config.save_detection_params(confidence, iou, frame_skip)
        return self.user_config.get_detection_params()

    def get_ui_settings(self):
        settings = dict(self.user_config.get_ui_settings())
        override_mode = (os.environ.get("UI_DEFAULT_MODE") or "").strip().lower()
        if override_mode in self.VALID_DEFAULT_MODES:
            settings["default_mode"] = override_mode
        return settings

    def save_ui_settings(self, settings):
        self.user_config.save_ui_settings(settings)
        return self.user_config.get_ui_settings()

    def mark_first_run_done(self):
        self.user_config.mark_first_run_done()

    def is_first_run(self):
        return self.user_config.is_first_run()

    def reset_user_config(self):
        self.user_config.reset_to_default()

    def save_last_models(self, student_model=None, teacher_model=None):
        self.user_config.save_last_models(student_model, teacher_model)
        return self.user_config.get_last_models()

    def get_last_models(self):
        return self.user_config.get_last_models()

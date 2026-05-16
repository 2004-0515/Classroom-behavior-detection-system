from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


@dataclass
class IsolatedRuntime:
    root: Path
    data_dir: Path
    uploads_dir: Path
    outputs_dir: Path
    yolo_config_dir: Path
    admin_username: str | None = None
    admin_password: str | None = None

    def build_env(self, *, base_env: dict[str, str] | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = dict(base_env or os.environ)
        env["UPLOAD_FOLDER"] = str(self.uploads_dir)
        env["OUTPUT_FOLDER"] = str(self.outputs_dir)
        env["DATABASE_PATH"] = str(self.data_dir / "detections.db")
        env["USER_CONFIG_PATH"] = str(self.data_dir / "user_config.json")
        env["ADMIN_CONFIG_PATH"] = str(self.data_dir / "admin_config.json")
        env["RUNTIME_SECRET_PATH"] = str(self.data_dir / "runtime_secrets.json")
        env["YOLO_CONFIG_DIR"] = str(self.yolo_config_dir)
        if self.admin_username:
            env["ADMIN_USERNAME"] = self.admin_username
        else:
            env.pop("ADMIN_USERNAME", None)
        if self.admin_password:
            env["ADMIN_PASSWORD"] = self.admin_password
        else:
            env.pop("ADMIN_PASSWORD", None)
        if extra:
            env.update(extra)
        return env


def create_isolated_runtime(prefix: str, *, admin_username: str | None = None, admin_password: str | None = None) -> IsolatedRuntime:
    temp_root = Path(tempfile.mkdtemp(prefix=f"classroom-{prefix}-"))
    data_dir = temp_root / "data"
    uploads_dir = temp_root / "uploads"
    outputs_dir = temp_root / "outputs"
    yolo_config_dir = data_dir / "yolo_config"
    for path in (uploads_dir, outputs_dir, yolo_config_dir):
        path.mkdir(parents=True, exist_ok=True)
    return IsolatedRuntime(
        root=temp_root,
        data_dir=data_dir,
        uploads_dir=uploads_dir,
        outputs_dir=outputs_dir,
        yolo_config_dir=yolo_config_dir,
        admin_username=admin_username,
        admin_password=admin_password,
    )


def apply_isolated_runtime(runtime: IsolatedRuntime, *, model_folder: Path | None = None):
    os.environ.update(runtime.build_env())
    from config import Config, _load_or_create_runtime_secret

    Config.UPLOAD_FOLDER = runtime.uploads_dir
    Config.OUTPUT_FOLDER = runtime.outputs_dir
    if model_folder is not None:
        Config.MODEL_FOLDER = Path(model_folder)
    Config.DATABASE_PATH = runtime.data_dir / "detections.db"
    Config.USER_CONFIG_PATH = runtime.data_dir / "user_config.json"
    Config.ADMIN_CONFIG_PATH = runtime.data_dir / "admin_config.json"
    Config.RUNTIME_SECRET_PATH = runtime.data_dir / "runtime_secrets.json"
    Config.YOLO_CONFIG_DIR = str(runtime.yolo_config_dir)
    Config.DEFAULT_ADMIN_USERNAME = runtime.admin_username
    Config.DEFAULT_ADMIN_PASSWORD = runtime.admin_password
    Config.SECRET_KEY = _load_or_create_runtime_secret(Config.RUNTIME_SECRET_PATH)
    return Config


def create_and_apply_isolated_runtime(prefix: str, *, admin_username: str | None = None, admin_password: str | None = None, model_folder: Path | None = None):
    runtime = create_isolated_runtime(prefix, admin_username=admin_username, admin_password=admin_password)
    config = apply_isolated_runtime(runtime, model_folder=model_folder)
    return runtime, config

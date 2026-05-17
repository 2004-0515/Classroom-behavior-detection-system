from __future__ import annotations

import os
from types import SimpleNamespace

from flask import Flask
from flask_cors import CORS
from flask_login import LoginManager

from config import Config, create_directories
from classroom_app.core.auth import AdminUser
from classroom_app.core.model_integrity import ensure_model_manifest_valid
from classroom_app.routes.auth import bp as auth_bp
from classroom_app.routes.dashboard import bp as dashboard_bp
from classroom_app.routes.detect import bp as detect_bp
from classroom_app.routes.models import bp as models_bp
from classroom_app.routes.settings import bp as settings_bp
from classroom_app.routes.streams import bp as streams_bp
from classroom_app.routes.tasks import bp as tasks_bp
os.environ.setdefault("YOLO_CONFIG_DIR", Config.YOLO_CONFIG_DIR)

from classroom_app.services.config_service import ConfigService
from classroom_app.services.detection_service import DetectionService
from classroom_app.services.detection_orchestrator import DetectionOrchestrator
from classroom_app.services.model_service import ModelService
from classroom_app.services.report_service import ReportService
from classroom_app.services.stream_session_manager import StreamSessionManager
from classroom_app.services.stream_service import StreamService
from classroom_app.services.task_payload_service import TaskPayloadService
from classroom_app.services.task_service import TaskService


def _build_services():
    config_service = ConfigService()
    task_service = TaskService()
    report_service = ReportService(task_service)
    model_service = ModelService(config_service)
    session_manager = StreamSessionManager()
    detect_service = DetectionService(model_service, task_service, config_service, session_manager)
    stream_service = StreamService(model_service, task_service)
    orchestrator = DetectionOrchestrator(detect_service, stream_service, task_service)
    payloads = TaskPayloadService(task_service, detect_service, stream_service)
    return SimpleNamespace(
        config=config_service,
        tasks=task_service,
        task_payloads=payloads,
        reports=report_service,
        models=model_service,
        detect=detect_service,
        orchestrator=orchestrator,
        streams=stream_service,
        sessions=session_manager,
    )


def create_app():
    ensure_model_manifest_valid(Config.MODEL_FOLDER)
    create_directories()
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.from_object(Config)
    CORS(app)

    services = _build_services()
    app.extensions["services"] = services

    login_manager = LoginManager()
    login_manager.login_view = "auth.login_page"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        username = services.config.get_admin_username()
        if user_id == username:
            return AdminUser(username)
        return None

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(detect_bp)
    app.register_blueprint(streams_bp)
    app.register_blueprint(models_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(settings_bp)

    return app

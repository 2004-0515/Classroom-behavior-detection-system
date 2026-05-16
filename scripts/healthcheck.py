from __future__ import annotations

import os
import pathlib
import py_compile
import shutil
import subprocess
import sys
import tempfile
import importlib
from pathlib import Path
import json

from isolated_env import create_and_apply_isolated_runtime


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime_paths import resolve_node


# Read-only baseline checks that should be cheap and environment-safe.
PYTHON_PACKAGE_CHECKS = [
    ("flask", "Flask Web 服务"),
    ("flask_login", "Flask-Login 登录会话"),
    ("flask_cors", "Flask-CORS 跨域支持"),
    ("numpy", "NumPy 数值计算"),
    ("cv2", "OpenCV 图像处理"),
    ("ultralytics", "Ultralytics YOLO"),
    ("requests", "Requests HTTP 客户端"),
]


def compile_python():
    failures = []
    for path in ROOT.rglob("*.py"):
        if any(part in {".venv", ".browser_tmp", "__pycache__"} for part in path.parts):
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            failures.append(f"{path.relative_to(ROOT)}: {exc}")
    return failures


def check_frontend():
    node = resolve_node()
    if not node:
        return ["未找到可用 node，无法执行 static/app/main.js 语法检查"]
    source = ROOT / "static" / "app" / "main.js"
    with tempfile.TemporaryDirectory(prefix="classroom-frontend-check-") as temp_dir:
        temp_entry = Path(temp_dir) / "main.mjs"
        temp_entry.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        result = subprocess.run([str(node), "--check", str(temp_entry)], capture_output=True, text=True)
    if result.returncode == 0:
        return []
    return [result.stderr.strip() or result.stdout.strip() or "node --check 失败"]


def check_python_packages():
    failures = []
    for module_name, label in PYTHON_PACKAGE_CHECKS:
        try:
            if module_name == "ultralytics":
                yolo_config_dir = Path(os.environ.get("YOLO_CONFIG_DIR") or ROOT / "data" / "yolo_config")
                yolo_config_dir.mkdir(parents=True, exist_ok=True)
                os.environ.setdefault("YOLO_CONFIG_DIR", str(yolo_config_dir))
            importlib.import_module(module_name)
        except Exception as exc:
            failures.append(f"{label} 不可用: import {module_name} 失败 ({exc})")
    return failures


def check_filesystem():
    required_dirs = ["classroom_app", "templates", "static", "models", "uploads", "outputs", "data", "scripts", "docs"]
    missing = [name for name in required_dirs if not (ROOT / name).exists()]
    return [f"缺少目录: {name}" for name in missing]


def _resolve_model_reference(model_ref: str | None) -> Path | None:
    ref = (model_ref or "").strip()
    if not ref:
        return None
    candidate = Path(ref)
    if candidate.is_absolute():
        return candidate
    rooted = ROOT / candidate
    if rooted.exists():
        return rooted
    return ROOT / "models" / candidate


def _collect_required_models():
    required_models: list[tuple[str, Path]] = [
        ("默认学生模型", ROOT / "models" / "behavior.pt"),
        ("默认教师模型", ROOT / "models" / "head.pt"),
    ]

    explicit_student = _resolve_model_reference(os.environ.get("STUDENT_MODEL_PATH"))
    explicit_teacher = _resolve_model_reference(os.environ.get("TEACHER_MODEL_PATH"))
    if explicit_student is not None:
        required_models.append(("当前启动学生模型", explicit_student))
    if explicit_teacher is not None:
        required_models.append(("当前启动教师模型", explicit_teacher))
    if explicit_student is not None or explicit_teacher is not None:
        return required_models

    user_config_path = ROOT / "data" / "user_config.json"
    if user_config_path.exists():
        try:
            user_config = json.loads(user_config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return required_models + [(f"用户配置解析失败: data/user_config.json ({exc})", ROOT / "__invalid_user_config__")]
        last_models = user_config.get("last_models") or {}
        for role, label in [("student", "当前学生模型"), ("teacher", "当前教师模型")]:
            resolved = _resolve_model_reference(last_models.get(role))
            if resolved is not None:
                required_models.append((label, resolved))

    return required_models


def check_model_assets():
    failures = []
    required_models = _collect_required_models()

    seen: set[str] = set()
    for label, path in required_models:
        if "__invalid_user_config__" in str(path):
            failures.append(label)
            continue
        normalized = str(path.resolve()) if path.exists() else str(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        if not path.exists():
            try:
                display = path.relative_to(ROOT).as_posix()
            except ValueError:
                display = str(path)
            failures.append(f"{label}缺失: {display}")
            continue
        if path.stat().st_size <= 0:
            try:
                display = path.relative_to(ROOT).as_posix()
            except ValueError:
                display = str(path)
            failures.append(f"{label}为空: {display}")

    return failures


def check_routes():
    os.environ.setdefault("ADMIN_USERNAME", "healthcheck_admin")
    os.environ.setdefault("ADMIN_PASSWORD", "healthcheck_pass_123")

    runtime, _ = create_and_apply_isolated_runtime(
        "healthcheck",
        admin_username="healthcheck_admin",
        admin_password="healthcheck_pass_123",
        model_folder=ROOT / "models",
    )

    from classroom_app import create_app

    app = create_app()
    failures = []
    with app.test_client() as client:
        unauth = client.get("/api/dashboard/overview", follow_redirects=False)
        if unauth.status_code not in {302, 401}:
            failures.append(f"未登录访问 /api/dashboard/overview 返回 {unauth.status_code}")

        login = client.post("/api/auth/login", json={"username": "healthcheck_admin", "password": "healthcheck_pass_123"})
        if login.status_code != 200:
            failures.append(f"登录接口返回 {login.status_code}")
            shutil.rmtree(runtime.root, ignore_errors=True)
            return failures

        for route in ["/", "/api/auth/session", "/api/dashboard/overview", "/api/tasks/recent", "/api/models/info", "/api/config"]:
            response = client.get(route, follow_redirects=False)
            if response.status_code != 200:
                failures.append(f"{route} 返回 {response.status_code}")

    shutil.rmtree(runtime.root, ignore_errors=True)
    return failures


def check_runtime_helpers():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "runtime_paths_test.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return []
    output = result.stderr.strip() or result.stdout.strip() or "runtime_paths_test.py 执行失败"
    return [output]


def print_section(title, failures):
    print(f"\n== {title} ==")
    if not failures:
        print("OK")
        return
    for item in failures:
        print(f"- {item}")


def main():
    python_failures = compile_python()
    package_failures = check_python_packages()
    frontend_failures = check_frontend()
    fs_failures = check_filesystem()
    model_failures = check_model_assets()
    route_failures = check_routes()
    runtime_helper_failures = check_runtime_helpers()

    print_section("Python 编译", python_failures)
    print_section("Python 依赖", package_failures)
    print_section("前端语法", frontend_failures)
    print_section("目录检查", fs_failures)
    print_section("模型检查", model_failures)
    print_section("关键路由", route_failures)
    print_section("脚本运行时", runtime_helper_failures)

    all_failures = (
        python_failures
        + package_failures
        + frontend_failures
        + fs_failures
        + model_failures
        + route_failures
        + runtime_helper_failures
    )
    if all_failures:
        print(f"\n健康检查失败，共 {len(all_failures)} 项。")
        sys.exit(1)

    print("\n健康检查通过。")


if __name__ == "__main__":
    main()

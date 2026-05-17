from __future__ import annotations

import json
import os
import socket
import time
import argparse
import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from classroom_app.core.errors import ModelError
from classroom_app.core.model_integrity import validate_model_file, verify_model_manifest
from runtime_paths import NODE_FALLBACK, PYTHON_ENV_VAR, PYTHON_FALLBACK, resolve_node, resolve_python
MODEL_ROOT = ROOT / "models"
DEMO_HOST = "127.0.0.1"
DEMO_PORT = 5000
DEMO_URL = f"http://{DEMO_HOST}:{DEMO_PORT}"
ACCEPTANCE_MAX_AGE = timedelta(hours=24)

RECOMMENDED_ASSETS = {
    "single_image": Path("testfile/0014012.jpg"),
    "batch_images": [
        Path("testfile/0009008.jpg"),
        Path("testfile/0009013.jpg"),
        Path("testfile/0009022.jpg"),
    ],
    "video": Path("testfile/QQ202618-01246-HD.mp4"),
}

VISUAL_AUDIT_ARTIFACTS = [
    Path("docs/_artifacts/browser-audit-login.png"),
    Path("docs/_artifacts/browser-audit-dashboard.png"),
    Path("docs/_artifacts/browser-audit-webcam.png"),
    Path("docs/_artifacts/browser-audit-report.png"),
    Path("docs/_artifacts/browser-visual-audit.json"),
]
ACCEPTANCE_ARTIFACTS = [
    Path("docs/_artifacts/verify-all-summary.json"),
    Path("docs/_artifacts/hardening-contracts.json"),
    *VISUAL_AUDIT_ARTIFACTS,
]

BROWSER_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files\Mozilla Firefox\firefox.exe"),
    Path(r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"),
]
PYTHON_PACKAGE_CHECKS = [
    ("flask", "Flask Web 服务"),
    ("flask_login", "Flask-Login 登录会话"),
    ("flask_cors", "Flask-CORS 跨域支持"),
    ("numpy", "NumPy 数值计算"),
    ("cv2", "OpenCV 图像处理"),
    ("ultralytics", "Ultralytics YOLO"),
    ("requests", "Requests HTTP 客户端"),
]


def parse_args():
    parser = argparse.ArgumentParser(description="课堂行为检测系统答辩预检")
    parser.add_argument(
        "--check-running-demo",
        action="store_true",
        help="仅检查 127.0.0.1:5000 是否已经是当前系统实例",
    )
    parser.add_argument(
        "--check-running-demo-entry-contract",
        action="store_true",
        help="仅检查 127.0.0.1:5000 上当前系统实例是否满足答辩入口契约",
    )
    return parser.parse_args()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def resolve_model_reference(model_ref: str | None) -> Path | None:
    ref = (model_ref or "").strip()
    if not ref:
        return None
    candidate = Path(ref)
    if candidate.is_absolute():
        return candidate

    rooted = ROOT / candidate
    if rooted.exists():
        return rooted
    return MODEL_ROOT / candidate


def collect_required_models():
    required_models: list[tuple[str, Path]] = [
        ("默认学生模型", ROOT / "models" / "behavior.pt"),
        ("默认教师模型", ROOT / "models" / "head.pt"),
    ]

    explicit_student = resolve_model_reference(os.environ.get("STUDENT_MODEL_PATH"))
    explicit_teacher = resolve_model_reference(os.environ.get("TEACHER_MODEL_PATH"))
    if explicit_student is not None:
        required_models.append(("当前启动学生模型", explicit_student))
    if explicit_teacher is not None:
        required_models.append(("当前启动教师模型", explicit_teacher))
    if explicit_student is not None or explicit_teacher is not None:
        return required_models

    user_config_path = ROOT / "data" / "user_config.json"
    if user_config_path.exists():
        try:
            user_config = load_json(user_config_path)
        except Exception as exc:
            return required_models + [(f"用户配置解析失败: {exc}", ROOT / "__invalid_user_config__")]
        last_models = user_config.get("last_models") or {}
        for role, label in [("student", "当前学生模型"), ("teacher", "当前教师模型")]:
            resolved = resolve_model_reference(last_models.get(role))
            if resolved is not None:
                required_models.append((label, resolved))

    return required_models


def ok():
    return [], []


def fail(message: str):
    return [message], []


def warn(message: str):
    return [], [message]


def is_current_demo_running() -> bool:
    try:
        with urlopen(f"{DEMO_URL}/", timeout=2) as response:
            body = response.read(2048).decode("utf-8", errors="ignore")
        return "课堂行为检测控制台" in body or "课堂行为检测" in body
    except Exception:
        return False


def inspect_running_demo_entry_contract():
    try:
        from demo_runtime_contract import inspect_demo_entry_contract
    except Exception as exc:
        return {
            "ok": False,
            "issues": [f"无法加载答辩入口契约探测模块: {exc}"],
            "snapshot": None,
        }
    return inspect_demo_entry_contract(DEMO_URL)


def check_python_runtime():
    python = resolve_python(current_python=sys.executable)
    if python:
        return ok()
    return fail(
        f"未找到可用 Python 运行时；可设置 {PYTHON_ENV_VAR}，"
        f"或准备 {PYTHON_FALLBACK.relative_to(ROOT).as_posix()}，"
        "或确保 PATH 中有 python"
    )


def check_node_runtime():
    node = resolve_node()
    if node:
        return ok()
    return fail(f"未找到可用 node；请确保 PATH 中存在 node，或准备 bundled runtime: {NODE_FALLBACK}")


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
    return failures, []


def check_admin_config():
    path = ROOT / "data" / "admin_config.json"
    if not path.exists():
        return fail(
            "缺少管理员配置: data/admin_config.json；请执行 "
            r'.\.venv\Scripts\python.exe scripts\init_local_admin.py --username admin --password "请替换为你自己的密码"'
        )

    try:
        payload = load_json(path)
    except Exception as exc:
        return fail(f"管理员配置无法解析: {exc}")

    failures = []
    username = (payload.get("username") or "").strip()
    if len(username) < 3:
        failures.append("管理员账号无效或长度不足 3，请重新执行 scripts/init_local_admin.py")
    if not payload.get("password_hash"):
        failures.append("管理员密码哈希缺失，请重新执行 scripts/init_local_admin.py")
    if payload.get("setup_required"):
        failures.append("管理员配置仍要求初始化，请重新执行 scripts/init_local_admin.py")
    return failures, []


def check_models():
    failures = []
    try:
        failures.extend(verify_model_manifest(MODEL_ROOT))
    except ModelError as exc:
        return [f"{exc.code}: {exc.message}"], []

    required_models = collect_required_models()
    seen: set[str] = set()
    for label, path in required_models:
        if "__invalid_user_config__" in str(path):
            failures.append(label)
            continue
        normalized = str(path.resolve()) if path.exists() else str(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            validate_model_file(path, MODEL_ROOT)
        except ModelError as exc:
            failures.append(f"{label}: {exc.message}")
    return failures, []


def check_demo_assets():
    failures = []
    if not (ROOT / RECOMMENDED_ASSETS["single_image"]).exists():
        failures.append(f"缺少单图演示素材: {RECOMMENDED_ASSETS['single_image'].as_posix()}")
    for rel in RECOMMENDED_ASSETS["batch_images"]:
        if not (ROOT / rel).exists():
            failures.append(f"缺少批量演示素材: {rel.as_posix()}")
    if not (ROOT / RECOMMENDED_ASSETS["video"]).exists():
        failures.append(f"缺少视频演示素材: {RECOMMENDED_ASSETS['video'].as_posix()}")
    return failures, []


def check_entrypoints():
    failures = []
    for rel in [
        Path("start_classroom_app.bat"),
        Path("verify_classroom_app.bat"),
        Path("demo_preflight.bat"),
        Path("start_demo_session.bat"),
        Path("startup_smoke.bat"),
    ]:
        if not (ROOT / rel).exists():
            failures.append(f"缺少入口脚本: {rel.as_posix()}")
    return failures, []


def check_browser():
    for candidate in BROWSER_CANDIDATES:
        if candidate.exists():
            return ok()
    return fail("未找到可用浏览器（Edge/Chrome/Firefox），无法现场打开 http://127.0.0.1:5000")


def parse_generated_at(path: Path) -> datetime:
    payload = load_json(path)
    generated_at = payload.get("generated_at")
    if not generated_at:
        raise ValueError(f"{path.relative_to(ROOT).as_posix()} 缺少 generated_at")
    return datetime.fromisoformat(str(generated_at))


def check_acceptance_artifacts():
    missing = [rel.as_posix() for rel in ACCEPTANCE_ARTIFACTS if not (ROOT / rel).exists()]
    if missing:
        return fail(f"缺少完整验收产物: {', '.join(missing)}")

    verify_summary_path = ROOT / "docs/_artifacts/verify-all-summary.json"
    hardening_path = ROOT / "docs/_artifacts/hardening-contracts.json"
    browser_summary_path = ROOT / "docs/_artifacts/browser-visual-audit.json"

    try:
        verify_summary = load_json(verify_summary_path)
        hardening_summary = load_json(hardening_path)
        browser_summary = load_json(browser_summary_path)
    except Exception as exc:
        return fail(f"验收产物解析失败: {exc}")

    if verify_summary.get("overall_status") != "OK":
        return fail("verify-all-summary.json 未记录成功通过的完整验收链")
    check_statuses = {item.get("name"): item.get("status") for item in verify_summary.get("checks", [])}
    required_checks = {
        "healthcheck",
        "startup_smoke",
        "frontend_service_tests",
        "ui_smoke",
        "interaction_smoke",
        "regression_smoke",
        "hardening_contracts",
        "audit_readiness",
        "browser_visual_audit",
    }
    missing_checks = sorted(name for name in required_checks if check_statuses.get(name) != "OK")
    if missing_checks:
        return fail(f"完整验收链存在未通过检查: {', '.join(missing_checks)}")

    for key in ("report_reuse", "batch_export_success", "native_webcam_contracts"):
        if key not in hardening_summary:
            return fail(f"hardening-contracts.json 缺少关键证据: {key}")
    if not browser_summary.get("report_markers_verified"):
        return fail("browser-visual-audit.json 未确认真实报告页面标记")
    if not browser_summary.get("batch_zip_path"):
        return fail("browser-visual-audit.json 缺少真实批量导出证据")

    try:
        generated_times = {
            "verify_all": parse_generated_at(verify_summary_path),
            "hardening_contracts": parse_generated_at(hardening_path),
            "browser_visual_audit": parse_generated_at(browser_summary_path),
        }
    except Exception as exc:
        return fail(f"验收时间戳解析失败: {exc}")

    now = datetime.now()
    stale = [
        f"{name} ({timestamp.strftime('%Y-%m-%d %H:%M:%S')})"
        for name, timestamp in generated_times.items()
        if now - timestamp > ACCEPTANCE_MAX_AGE
    ]
    if stale:
        return fail(
            "完整验收产物已超过 24 小时有效期，请重新执行 verify_classroom_app.bat: "
            + ", ".join(stale)
        )

    stale_screenshots = [
        rel.as_posix()
        for rel in VISUAL_AUDIT_ARTIFACTS[:-1]
        if now - datetime.fromtimestamp((ROOT / rel).stat().st_mtime) > ACCEPTANCE_MAX_AGE
    ]
    if stale_screenshots:
        return fail("视觉审计截图已超过 24 小时有效期: " + ", ".join(stale_screenshots))
    return ok()


def check_demo_port():
    for _ in range(3):
        if is_current_demo_running():
            inspection = inspect_running_demo_entry_contract()
            if inspection["ok"]:
                return warn(
                    f"端口 {DEMO_PORT} 已被当前系统实例占用，且当前服务已满足答辩入口契约；"
                    f"`start_demo_session.bat` 会直接复用现有服务"
                )
            details = "; ".join(inspection.get("issues") or []) or "原因未知"
            return fail(
                f"端口 {DEMO_PORT} 已被当前系统实例占用，但当前服务不满足答辩入口契约（{details}）；"
                f"`start_demo_session.bat` 会要求先关闭现有服务后重新启动"
            )
        try:
            with socket.create_connection((DEMO_HOST, DEMO_PORT), timeout=1):
                pass
            time.sleep(0.3)
            continue
        except OSError:
            return ok()

    if is_current_demo_running():
        inspection = inspect_running_demo_entry_contract()
        if inspection["ok"]:
            return warn(
                f"端口 {DEMO_PORT} 已被当前系统实例占用，且当前服务已满足答辩入口契约；"
                f"`start_demo_session.bat` 会直接复用现有服务"
            )
        details = "; ".join(inspection.get("issues") or []) or "原因未知"
        return fail(
            f"端口 {DEMO_PORT} 已被当前系统实例占用，但当前服务不满足答辩入口契约（{details}）；"
            f"`start_demo_session.bat` 会要求先关闭现有服务后重新启动"
        )

    try:
        with urlopen(f"{DEMO_URL}/", timeout=2):
            return fail(f"端口 {DEMO_PORT} 已被其他 HTTP 服务占用")
    except HTTPError as exc:
        return fail(f"端口 {DEMO_PORT} 已被其他 HTTP 服务占用，状态码 {exc.code}")
    except URLError:
        return fail(f"端口 {DEMO_PORT} 已被其他进程占用，启动前请先释放")


def print_section(title: str, failures: list[str], warnings: list[str]):
    print(f"\n== {title} ==")
    if not failures and not warnings:
        print("OK")
        return
    for item in warnings:
        print(f"! {item}")
    for item in failures:
        print(f"- {item}")


def print_recommended_assets():
    print("\n推荐演示素材:")
    print(f"- 单图: {RECOMMENDED_ASSETS['single_image'].as_posix()}")
    print("- 批量:")
    for rel in RECOMMENDED_ASSETS["batch_images"]:
        print(f"  - {rel.as_posix()}")
    print(f"- 视频: {RECOMMENDED_ASSETS['video'].as_posix()}")
    print(f"- 访问地址: {DEMO_URL}")


def main():
    args = parse_args()
    if args.check_running_demo:
        raise SystemExit(0 if is_current_demo_running() else 1)
    if args.check_running_demo_entry_contract:
        inspection = inspect_running_demo_entry_contract()
        raise SystemExit(0 if inspection["ok"] else 1)

    checks = [
        ("Python 运行时", *check_python_runtime()),
        ("Python 依赖", *check_python_packages()),
        ("Node 运行时", *check_node_runtime()),
        ("管理员配置", *check_admin_config()),
        ("模型文件", *check_models()),
        ("演示素材", *check_demo_assets()),
        ("根目录入口", *check_entrypoints()),
        ("浏览器可用性", *check_browser()),
        ("完整验收产物", *check_acceptance_artifacts()),
        ("演示端口", *check_demo_port()),
    ]

    for title, failures, warnings in checks:
        print_section(title, failures, warnings)
    print_recommended_assets()

    all_failures = [item for _, failures, _ in checks for item in failures]
    if all_failures:
        print(f"\n答辩预检失败，共 {len(all_failures)} 项。")
        raise SystemExit(1)

    all_warnings = [item for _, _, warnings in checks for item in warnings]
    if all_warnings:
        print(f"\n答辩预检通过，但有 {len(all_warnings)} 条提醒。")
        raise SystemExit(0)

    print("\n答辩预检通过。")


if __name__ == "__main__":
    main()

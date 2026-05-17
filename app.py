import os
import sys

from classroom_app import create_app
from classroom_app.core.errors import AppError
from config import Config

try:
    app = create_app()
except AppError as exc:
    print(f"应用启动失败 [{exc.code}]: {exc.message}", file=sys.stderr)
    raise SystemExit(1) from None


def _resolve_bind_settings():
    host = os.environ.get("APP_HOST") or "0.0.0.0"
    port_text = os.environ.get("APP_PORT") or "5000"
    try:
        port = int(port_text)
    except ValueError:
        raise SystemExit(f"无效 APP_PORT: {port_text}")

    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return host, port, display_host


if __name__ == "__main__":
    host, port, display_host = _resolve_bind_settings()
    print("=" * 60)
    print("课堂行为检测系统启动中...")
    print("=" * 60)
    print(f"上传文件夹: {Config.UPLOAD_FOLDER}")
    print(f"输出文件夹: {Config.OUTPUT_FOLDER}")
    print(f"模型文件夹: {Config.MODEL_FOLDER}")
    print(f"访问地址: http://{display_host}:{port}")
    print("=" * 60)
    app.run(
        debug=False,
        use_reloader=False,
        host=host,
        port=port,
        threaded=True,
    )

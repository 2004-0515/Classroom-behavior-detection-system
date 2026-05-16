from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from isolated_env import create_isolated_runtime

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def prepare_isolated_environment() -> Path:
    runtime = create_isolated_runtime(
        "browser-audit",
        admin_username=os.environ.get("ADMIN_USERNAME") or "audit_admin",
        admin_password=os.environ.get("ADMIN_PASSWORD") or "audit_password_123",
    )
    os.environ.update(runtime.build_env())
    return runtime.root


def main() -> int:
    parser = argparse.ArgumentParser(description="Start an isolated browser-audit server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()

    temp_root = prepare_isolated_environment()
    from classroom_app import create_app
    from flask import redirect, request
    from flask_login import login_user
    from classroom_app.core.auth import AdminUser

    app = create_app()

    @app.route("/audit/login-and-go")
    def audit_login_and_go():
        target = request.args.get("next") or "/"
        if not target.startswith("/"):
            target = "/"
        login_user(AdminUser("audit_admin"))
        return redirect(target)

    print(f"Audit server data root: {temp_root}", flush=True)
    print(f"Audit login: audit_admin / audit_password_123", flush=True)
    print(f"Audit URL: http://{args.host}:{args.port}", flush=True)
    app.run(debug=False, use_reloader=False, host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

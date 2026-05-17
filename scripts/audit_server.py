from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from isolated_env import create_isolated_runtime

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def prepare_isolated_environment(*, admin_username: str | None, admin_password: str | None) -> Path:
    runtime = create_isolated_runtime(
        "browser-audit",
        admin_username=admin_username,
        admin_password=admin_password,
    )
    os.environ.update(runtime.build_env())
    return runtime.root


def main() -> int:
    parser = argparse.ArgumentParser(description="Start an isolated browser-audit server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--admin-username", default=os.environ.get("ADMIN_USERNAME") or "audit_admin")
    parser.add_argument("--admin-password", default=os.environ.get("ADMIN_PASSWORD") or "audit_password_123")
    parser.add_argument("--without-admin", action="store_true", help="start with setup_required login state")
    args = parser.parse_args()

    admin_username = None if args.without_admin else args.admin_username
    admin_password = None if args.without_admin else args.admin_password
    temp_root = prepare_isolated_environment(admin_username=admin_username, admin_password=admin_password)
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
        if admin_username:
            login_user(AdminUser(admin_username))
            return redirect(target)
        return redirect("/login")

    print(f"Audit server data root: {temp_root}", flush=True)
    if admin_username:
        print(f"Audit login: {admin_username} / {admin_password}", flush=True)
    else:
        print("Audit login: setup_required (no admin configured)", flush=True)
    print(f"Audit URL: http://{args.host}:{args.port}", flush=True)
    app.run(debug=False, use_reloader=False, host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

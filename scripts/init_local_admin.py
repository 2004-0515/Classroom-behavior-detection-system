from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from classroom_app.services.config_service import ConfigService


# Local setup helper for creating or resetting the admin account outside source control.
def parse_args():
    parser = argparse.ArgumentParser(description="初始化或重置本地管理员账号")
    parser.add_argument("--username", required=True, help="管理员账号，至少 3 个字符")
    parser.add_argument("--password", required=True, help="管理员密码，至少 8 个字符")
    return parser.parse_args()


def main():
    args = parse_args()
    service = ConfigService()
    result = service.bootstrap_admin(args.username, args.password)
    print(f"管理员账号已写入: {result['username']}")
    print(f"配置文件位置: {service.admin_config_path}")


if __name__ == "__main__":
    main()

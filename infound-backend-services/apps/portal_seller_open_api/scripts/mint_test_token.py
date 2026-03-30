from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from apps.portal_seller_open_api.core.config import Settings
from core_base import SettingsFactory
from core_redis import RedisClientManager
from shared_seller_application_services.current_user_info import CurrentUserInfo
from shared_seller_application_services.token_manager import TokenManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mint a seller test JWT and save it into Redis."
    )
    parser.add_argument("--user-id", required=True, help="Seller user_id")
    parser.add_argument("--username", required=True, help="Seller username")
    parser.add_argument("--phone-number", default="", help="Optional phone number")
    parser.add_argument("--device-id", default="manual-device", help="Optional device id")
    parser.add_argument("--device-type", default="desktop", help="Optional device type")
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Print shell export commands instead of plain text",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = SettingsFactory.initialize(
        settings_class=Settings,
        config_dir=Path(__file__).resolve().parents[1] / "configs",
    )
    RedisClientManager.initialize(settings.redis)

    try:
        token_manager = TokenManager(settings.auth, settings.redis)
        current_user = CurrentUserInfo(
            jti="manual-test",
            iat=datetime.now(timezone.utc),
            user_id=args.user_id,
            username=args.username,
            phone_number=args.phone_number or "",
            device_id=args.device_id,
            device_type=args.device_type,
        )
        token = token_manager.create_access_token(current_user)

        if args.shell:
            print(f'export SELLER_AUTH_HEADER="{settings.auth.required_header}"')
            print(f'export SELLER_TOKEN="{token}"')
            print(f'export SELLER_USER_ID="{args.user_id}"')
            print(f'export SELLER_USERNAME="{args.username}"')
            return

        print(f"header={settings.auth.required_header}")
        print(f"token={token}")
        print(f"user_id={args.user_id}")
        print(f"username={args.username}")
    finally:
        RedisClientManager.close()


if __name__ == "__main__":
    main()

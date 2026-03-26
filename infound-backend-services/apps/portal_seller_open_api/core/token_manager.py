import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.models.entities import CurrentUserInfo
from core_base import get_logger
from core_redis import RedisClientManager


class TokenManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(TokenManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger(self.__class__.__name__)
        self.secret_key = settings.auth.secret_key
        self.algorithm = "HS256"
        self.expire_days = settings.auth.expire_days
        self.max_tokens = settings.auth.max_tokens
        self.redis = RedisClientManager.get_client()

    def create_access_token(self, user: CurrentUserInfo) -> str:
        jti = str(uuid.uuid4())
        expire = datetime.now(timezone.utc) + timedelta(days=self.expire_days)

        payload = {
            "sub": user.username,
            "jti": jti,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
        }
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        self._save_token_to_redis(user, jti)
        return token

    def decode_access_token(self, token: str) -> Optional[dict]:
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except jwt.exceptions.DecodeError as exc:
            self.logger.warning("JWT decode failed: %s", str(exc))
            return None
        except jwt.ExpiredSignatureError:
            self.logger.warning("JWT token has expired")
            return None

    def is_token_valid_in_redis(self, username: str, token_jti: str) -> bool:
        redis_key = self._get_redis_key(username)
        return bool(self.redis.hexists(redis_key, token_jti))

    def get_current_user_info(
        self, username: str, jti: str
    ) -> Optional[CurrentUserInfo]:
        redis_key = self._get_redis_key(username)
        user_data = self.redis.hget(redis_key, jti)
        if user_data:
            return CurrentUserInfo.model_validate_json(user_data)
        return None

    def _save_token_to_redis(self, user: CurrentUserInfo, jti: str) -> None:
        username = user.username
        redis_key = self._get_redis_key(username)
        token_count = self.redis.hlen(redis_key)
        if token_count >= self.max_tokens:
            all_keys = self.redis.hkeys(redis_key)
            if all_keys:
                self.redis.hdel(redis_key, all_keys[0])
        self.redis.hset(redis_key, jti, user.model_dump_json())
        self.redis.expire(redis_key, self.expire_days * 86400)

    def _get_redis_key(self, username: str) -> str:
        return f"{self.settings.redis.prefix}:authTokens:{username}"

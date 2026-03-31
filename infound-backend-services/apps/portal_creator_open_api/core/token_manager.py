import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from apps.portal_creator_open_api.core.config import Settings
from apps.portal_creator_open_api.models.entities import CurrentUserInfo
from core_base import get_logger
from core_redis import RedisClientManager


class TokenManager:
    """
    统一管理 JWT 的创建、解析及 Redis 状态维护
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(TokenManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, settings: Settings):
        self.settings = settings
        # 将 logger 绑定到实例，日志中会带上类名，方便追踪
        self.logger = get_logger(self.__class__.__name__)

        # 核心配置（可以从 settings 读取，避免硬编码）
        self.secret_key = settings.auth.secret_key
        self.algorithm = "HS256"
        self.expire_days = settings.auth.expire_days
        self.max_tokens = settings.auth.max_tokens

        # Redis 客户端初始化
        self._redis = RedisClientManager.get_client()

    # --- 核心方法 1：创建 Token ---
    def create_access_token(self, user: CurrentUserInfo) -> str:
        """
        生成 JWT，并自动将其元数据存入 Redis
        """
        jti = str(uuid.uuid4())  # 生成唯一的 Token ID
        expire = datetime.now(timezone.utc) + timedelta(days=self.expire_days)

        payload = {
            "sub": user.platform_creator_username,
            "jti": jti,
            "exp": expire,
            "iat": datetime.now(timezone.utc),  # 签发时间
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        # 自动同步到 Redis
        self._save_token_to_redis(user, jti)

        self.logger.info(
            f"Created token for user: {user.platform_creator_username}, JTI: {jti}"
        )
        return token

    # --- 核心方法 2：解析 Token ---
    def decode_access_token(self, token: str) -> Optional[dict]:
        """
        解码并校验 JWT 令牌
        """
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except jwt.exceptions.DecodeError as e:
            self.logger.warning(f"JWT decode failed: {str(e)}")
            return None
        except jwt.ExpiredSignatureError:
            self.logger.warning("JWT token has expired")
            return None

    # --- 核心方法 4：校验与获取用户信息 ---
    def get_current_user_info(
            self, username: str, jti: str
    ) -> Optional[CurrentUserInfo]:
        """
        从 Redis 中验证并提取用户信息
        """
        redis_key = self._get_redis_key(username)
        user_data = self._redis.hget(redis_key, jti)

        if user_data:
            return CurrentUserInfo.model_validate_json(user_data)

        self.logger.debug(f"No valid session found in Redis for user: {username}")
        return None

    # --- 核心方法 3：Redis 状态维护 (私有) ---
    def _save_token_to_redis(self, user: CurrentUserInfo, jti: str) -> None:
        """
        实现“每个用户最多 N 个有效 Token”的逻辑
        """
        username = user.platform_creator_username
        redis_key = self._get_redis_key(username)

        # 1. 检查并清理旧 Token
        token_count = self._redis.hlen(redis_key)
        if token_count >= self.max_tokens:
            # 获取所有并按时间顺序（这里可以用 jti 的先后，或在 value 里存时间戳）
            # 简单处理：删除 Hash 中的第一个字段
            all_keys = self._redis.hkeys(redis_key)
            if all_keys:
                self._redis.hdel(redis_key, all_keys[0])
                self.logger.info(f"Max tokens reached for {username}, removed oldest.")

        # 2. 存储新 Token 信息
        self._redis.hset(redis_key, jti, user.model_dump_json())

        # 3. 更新过期时间
        self._redis.expire(redis_key, self.expire_days * 86400)

    def _get_redis_key(self, username: str) -> str:
        """内部方法：构建统一的 Redis Key"""
        return f"{self.settings.redis.prefix}:creator:authTokens:{username}"

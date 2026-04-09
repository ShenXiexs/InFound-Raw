from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError, PyJWTError

from core_base import get_logger
from core_redis import RedisClientManager
from core_redis.redis_setting import RedisSettings
from shared_infrastructure.settings.auth_config import IFAuthSettings
from shared_seller_application_services.current_user_info import CurrentUserInfo


class TokenManager:
    """
    统一管理 JWT 的创建、解析及 Redis 状态维护
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(TokenManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, auth_settings: IFAuthSettings, redis_settings: RedisSettings):
        # 将 logger 绑定到实例，日志中会带上类名，方便追踪
        self.logger = get_logger(self.__class__.__name__)
        self.redis_settings = redis_settings
        self.secret_key = auth_settings.secret_key
        self.algorithm = "HS256"
        self.expire_days = auth_settings.expire_days
        self.max_tokens = auth_settings.max_tokens

        # Redis 客户端初始化
        self.redis = RedisClientManager.get_client()

    # --- 核心方法 1：创建 Token ---
    def create_access_token(self, user: CurrentUserInfo) -> str:
        """
        生成 JWT，并自动将其元数据存入 Redis
        """
        expire = datetime.now(timezone.utc) + timedelta(days=self.expire_days)

        payload = {
            "sub": user.username,
            "jti": user.jti,
            "exp": expire,
            "iat": user.iat,
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        # 自动同步到 Redis
        self._save_token_to_redis(user, user.jti)

        # self.logger.info(
        #     f"Created token for user: {user.username}, JTI: {user.jti}"
        # )
        return token

    # --- 核心方法 2：解析 Token ---
    def decode_access_token(self, token: str) -> Optional[dict]:
        """
        解码并校验 JWT 令牌
        """
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except ExpiredSignatureError:
            self.logger.warning("JWT token has expired")
            return None
        except InvalidTokenError as e:
            self.logger.warning(f"JWT decode failed: {str(e)}")
            return None
        except PyJWTError as e:
            self.logger.warning(f"JWT decode failed: {str(e)}")
            return None

    def is_token_valid_in_redis(self, username: str, token_jti: str) -> bool:
        """检查 Token 是否存在于 Redis（有效）"""
        redis_key = self._get_redis_key(username)
        try:
            existing_jtis = list((self.redis.hkeys(redis_key) or []))
        except Exception:
            existing_jtis = []
        exists = self.redis.hexists(redis_key, token_jti)
        self.logger.info(
            "Redis token validity check",
            redis_key=redis_key,
            username=username,
            token_jti=token_jti,
            exists=exists,
            existing_jtis=existing_jtis,
        )
        return exists

    # --- 核心方法 4：校验与获取用户信息 ---
    def get_current_user_info(
            self, username: str, jti: str
    ) -> Optional[CurrentUserInfo]:
        """
        从 Redis 中验证并提取用户信息
        """
        redis_key = self._get_redis_key(username)
        user_data = self.redis.hget(redis_key, jti)

        if user_data:
            return CurrentUserInfo.model_validate_json(user_data)

        self.logger.debug(f"No valid session found in Redis for user: {username}")
        return None

    # --- 核心方法 3：Redis 状态维护 (私有) ---
    def _save_token_to_redis(self, user: CurrentUserInfo, new_jti: str) -> None:
        """
        实现"每个用户最多 N 个有效 Token"的逻辑，并处理同一设备的旧 Token
        """
        username = user.username
        redis_key = self._get_redis_key(username)

        # 1. 一次性获取并解析所有现有的 token
        existing = self.redis.hgetall(redis_key)

        same_device_jtis = []
        same_device_type_tokens = []

        if existing:
            for existing_jti, user_json in existing.items():
                if not isinstance(user_json, str):
                    continue

                try:
                    old_user = CurrentUserInfo.model_validate_json(user_json)

                    # 收集同一 device_id 的 token
                    if user.device_id and old_user.device_id == user.device_id:
                        same_device_jtis.append(existing_jti)

                    # 收集同一 device_type 的 token
                    if old_user.device_type == (user.device_type or "other"):
                        same_device_type_tokens.append((existing_jti, old_user))

                except Exception:
                    continue

        # 2. 删除同一设备的旧 token
        if same_device_jtis:
            self.redis.hdel(redis_key, *same_device_jtis)
            for removed_jti in same_device_jtis:
                self.logger.info(f"Removed old token for same device: {removed_jti}")

        # 3. 检查并按 device_type 限制清理
        max_allowed = self.max_tokens

        if len(same_device_type_tokens) >= max_allowed:
            # 按 iat 排序，删除最旧的
            same_device_type_tokens.sort(key=lambda x: x[1].iat)
            tokens_to_remove = same_device_type_tokens[:len(same_device_type_tokens) - max_allowed + 1]

            jti_to_remove = [jti for jti, _ in tokens_to_remove]
            self.redis.hdel(redis_key, *jti_to_remove)

            for removed_jti in jti_to_remove:
                self.logger.info(
                    f"Max tokens ({max_allowed}) reached for device_type '{user.device_type or 'other'}' "
                    f"for {username}, removed: {removed_jti}"
                )

        self.logger.info(f"Stored token for {username}, JTI: {new_jti}")

        # 4. 存储新 Token 信息
        self.redis.hset(redis_key, new_jti, user.model_dump_json())
        try:
            existing_jtis_after_set = list((self.redis.hkeys(redis_key) or []))
        except Exception:
            existing_jtis_after_set = []
        self.logger.info(
            "Stored token into Redis",
            redis_key=redis_key,
            username=username,
            token_jti=new_jti,
            device_id=user.device_id,
            device_type=user.device_type,
            existing_jtis_after_set=existing_jtis_after_set,
        )

        # 5. 更新过期时间
        self.redis.expire(redis_key, self.expire_days * 86400)

    def _get_redis_key(self, username: str) -> str:
        """内部方法：构建统一的 Redis Key"""
        return f"{self.redis_settings.prefix}:seller:authTokens:{username}"

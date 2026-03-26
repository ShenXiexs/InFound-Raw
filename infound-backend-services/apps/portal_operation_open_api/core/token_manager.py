import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
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
        self.redis = RedisClientManager.get_client()

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

    def is_token_valid_in_redis(self, username: str, token_jti: str) -> bool:
        """检查 Token 是否存在于 Redis（有效）"""
        redis_key = self._get_redis_key(username)
        return self.redis.hexists(redis_key, token_jti)

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

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码（直接使用 bcrypt 库）"""
        if not plain_password or not hashed_password:
            return False

        # 检查哈希值格式
        if not hashed_password.startswith(('$2a$', '$2b$', '$2y$')):
            self.logger.warning(f"无效的密码哈希值格式（不是 bcrypt 格式）")
            return False

        if len(hashed_password) != 60:
            self.logger.warning(f"密码哈希值长度不正确（应该是 60 字符，实际是 {len(hashed_password)}）")
            return False

        # 检查密码长度
        password_bytes = plain_password.encode('utf-8')
        if len(password_bytes) > 72:
            self.logger.warning(f"密码长度超过 72 字节（实际 {len(password_bytes)} 字节），验证将失败")
            return False

        try:
            # 将哈希值转换为 bytes
            hashed_bytes = hashed_password.encode('utf-8')

            # 使用 bcrypt 验证密码
            return bcrypt.checkpw(password_bytes, hashed_bytes)
        except ValueError as e:
            # 处理密码验证错误
            error_msg = str(e)
            self.logger.error(f"密码验证失败（ValueError）: {error_msg}")
            return False
        except Exception as e:
            self.logger.error(f"密码验证时发生未知错误: {str(e)}, 类型: {type(e).__name__}")
            self.logger.error(f"错误堆栈: {traceback.format_exc()}")
            return False

    # --- 核心方法 3：Redis 状态维护 (私有) ---
    def _save_token_to_redis(self, user: CurrentUserInfo, jti: str) -> None:
        """
        实现“每个用户最多 N 个有效 Token”的逻辑
        """
        username = user.platform_creator_username
        redis_key = self._get_redis_key(username)

        # 1. 检查并清理旧 Token
        token_count = self.redis.hlen(redis_key)
        if token_count >= self.max_tokens:
            # 获取所有并按时间顺序（这里可以用 jti 的先后，或在 value 里存时间戳）
            # 简单处理：删除 Hash 中的第一个字段
            all_keys = self.redis.hkeys(redis_key)
            if all_keys:
                self.redis.hdel(redis_key, all_keys[0])
                self.logger.info(f"Max tokens reached for {username}, removed oldest.")

        # 2. 存储新 Token 信息
        self.redis.hset(redis_key, jti, user.model_dump_json())

        # 3. 更新过期时间
        self.redis.expire(redis_key, self.expire_days * 86400)

    def _get_redis_key(self, username: str) -> str:
        """内部方法：构建统一的 Redis Key"""
        return f"{self.settings.redis.prefix}:authTokens:{username}"

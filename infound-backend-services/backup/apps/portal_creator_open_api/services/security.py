from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from apps.portal_creator_open_api.models.entities import CurrentUserInfo
from common import app_constants
from common.core.config import get_settings
from common.core.logger import get_logger
from common.core.redis_client import RedisClientManager

settings = get_settings()
logger = get_logger()

SECRET_KEY = "94dfc07baaef3854516a0f0f0d0d22f5bb887b1b28380fcb6734d055f353d43b"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 14
MAX_TOKEN_PER_USER = 5


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """解码 JWT 令牌"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=ALGORITHM)
        return payload
    except jwt.exceptions.DecodeError as e:
        logger.warning(f"JWT 解码失败: {str(e)}")
        return None


def save_token_to_redis(user: CurrentUserInfo, token: str) -> None:
    """
    将 Token 保存到 Redis
    规则：每个用户最多 5 个 Token，超出则删除最早的
    """
    # Redis Key：user_tokens:{username}（存储该用户的所有 Token 及创建时间）
    redis_key = get_redis_key_for_user(user.platform_creator_username)
    token_jti = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])["jti"]

    # 1. 检查用户已有的 Token 数量
    redis_client = RedisClientManager.get_client()
    token_count = redis_client.hlen(redis_key)

    # 2. 如果达到上限，删除最早的 Token
    if token_count >= MAX_TOKEN_PER_USER:
        # 获取所有 Token 的创建时间，按时间排序，删除最早的
        tokens = redis_client.hgetall(redis_key)
        sorted_tokens = sorted(tokens.items(), key=lambda x: int(x[0]))
        oldest_token_jti, _ = sorted_tokens[0]
        redis_client.hdel(redis_key, oldest_token_jti)

    logger.info(f"用户 {user.platform_creator_username} 添加 Token: {redis_key}")

    # 3. 保存新 Token（JTI 作为字段名，创建时间作为值）
    redis_client.hset(redis_key, token_jti, user.model_dump_json())
    # 4. 设置 Redis 过期时间（与 Token 有效期一致）
    redis_client.expire(redis_key, ACCESS_TOKEN_EXPIRE_DAYS * 86400)


def is_token_valid_in_redis(username: str, token_jti: str) -> bool:
    """检查 Token 是否存在于 Redis（有效）"""
    redis_client = RedisClientManager.get_client()
    redis_key = get_redis_key_for_user(username)
    return redis_client.hexists(redis_key, token_jti)


def get_current_user_info(username: str, token_jti: str) -> Optional[CurrentUserInfo]:
    """获取用户信息"""
    redis_client = RedisClientManager.get_client()
    redis_key = get_redis_key_for_user(username)
    user_data = redis_client.hget(redis_key, token_jti)
    if user_data:
        return CurrentUserInfo.model_validate_json(user_data)
    return None


def get_redis_key_for_user(username: str) -> str:
    return f"{settings.REDIS_PREFIX}:{app_constants.CREATOR_REDIS_PREFIX_FOR_USER}:{username}"

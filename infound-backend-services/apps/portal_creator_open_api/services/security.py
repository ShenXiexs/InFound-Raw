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

SECRET_KEY = settings.JWT_SECRET_KEY
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
    """Decode JWT access token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=ALGORITHM)
        return payload
    except jwt.exceptions.DecodeError as e:
        logger.warning(f"JWT decode failed: {str(e)}")
        return None


def save_token_to_redis(user: CurrentUserInfo, token: str) -> None:
    """
    Save token to Redis.
    Policy: keep up to 5 tokens per user; drop the oldest when exceeded.
    """
    # Redis key: user_tokens:{username} (stores token + timestamps)
    redis_key = get_redis_key_for_user(user.platform_creator_username)
    token_jti = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])["jti"]

    # 1. Check existing token count
    redis_client = RedisClientManager.get_client()
    token_count = redis_client.hlen(redis_key)

    # 2. Delete oldest token if limit reached
    if token_count >= MAX_TOKEN_PER_USER:
        # Sort by creation time and delete the oldest
        tokens = redis_client.hgetall(redis_key)
        sorted_tokens = sorted(tokens.items(), key=lambda x: int(x[0]))
        oldest_token_jti, _ = sorted_tokens[0]
        redis_client.hdel(redis_key, oldest_token_jti)

    logger.info(f"Token stored for user {user.platform_creator_username}: {redis_key}")

    # 3. Save new token (JTI as field; creation time as value)
    redis_client.hset(redis_key, token_jti, user.model_dump_json())
    # 4. Set Redis TTL to match token expiry
    redis_client.expire(redis_key, ACCESS_TOKEN_EXPIRE_DAYS * 86400)


def is_token_valid_in_redis(username: str, token_jti: str) -> bool:
    """Check whether token exists in Redis."""
    redis_client = RedisClientManager.get_client()
    redis_key = get_redis_key_for_user(username)
    return redis_client.hexists(redis_key, token_jti)


def get_current_user_info(username: str, token_jti: str) -> Optional[CurrentUserInfo]:
    """Get current user info."""
    redis_client = RedisClientManager.get_client()
    redis_key = get_redis_key_for_user(username)
    user_data = redis_client.hget(redis_key, token_jti)
    if user_data:
        return CurrentUserInfo.model_validate_json(user_data)
    return None


def get_redis_key_for_user(username: str) -> str:
    return f"{settings.REDIS_PREFIX}:{app_constants.CREATOR_REDIS_PREFIX_FOR_USER}:{username}"

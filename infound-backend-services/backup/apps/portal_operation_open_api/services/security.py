import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from apps.portal_operation_open_api.models.entities import CurrentUserInfo
from common import app_constants
from common.core.config import get_settings
from common.core.logger import get_logger
from common.core.redis_client import RedisClientManager

settings = get_settings()
logger = get_logger()

# 直接使用 bcrypt 库，避免 passlib 的兼容性问题
BCRYPT_ROUNDS = 12

SECRET_KEY = "94dfc07baaef3854516a0f0f0d0d22f5bb887b1b28380fcb6734d055f353d43b"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 14
MAX_TOKEN_PER_USER = 5


def get_password_hash(password: str) -> str:
    """加密密码"""
    # 将密码编码为 bytes
    password_bytes = password.encode('utf-8')
    # 生成盐并加密
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password_bytes, salt)
    # 返回字符串格式的哈希值
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码（直接使用 bcrypt 库）"""
    if not plain_password or not hashed_password:
        return False
    
    # 检查哈希值格式
    if not hashed_password.startswith(('$2a$', '$2b$', '$2y$')):
        logger.warning(f"无效的密码哈希值格式（不是 bcrypt 格式）")
        return False
    
    if len(hashed_password) != 60:
        logger.warning(f"密码哈希值长度不正确（应该是 60 字符，实际是 {len(hashed_password)}）")
        return False
    
    # 检查密码长度
    password_bytes = plain_password.encode('utf-8')
    if len(password_bytes) > 72:
        logger.warning(f"密码长度超过 72 字节（实际 {len(password_bytes)} 字节），验证将失败")
        return False
    
    try:
        # 将哈希值转换为 bytes
        hashed_bytes = hashed_password.encode('utf-8')
        
        # 使用 bcrypt 验证密码
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except ValueError as e:
        # 处理密码验证错误
        error_msg = str(e)
        logger.error(f"密码验证失败（ValueError）: {error_msg}")
        return False
    except Exception as e:
        logger.error(f"密码验证时发生未知错误: {str(e)}, 类型: {type(e).__name__}")
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return False


def create_access_token(data: dict) -> str:
    """创建 JWT Token"""
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
    except jwt.exceptions.JWTException as e:
        logger.warning(f"JWT 解码失败: {str(e)}")
        return None


def save_token_to_redis(user: CurrentUserInfo, token: str) -> None:
    """
    将 Token 保存到 Redis
    规则：每个用户最多 5 个 Token，超出则删除最早的
    """
    # Redis Key：user_tokens:{username}（存储该用户的所有 Token 及创建时间）
    redis_key = get_redis_key_for_user(user.user_name)
    
    # 解析 Token 获取 JTI，如果失败则记录日志并返回
    try:
        token_jti = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])["jti"]
    except jwt.exceptions.JWTException as e:
        logger.error(f"保存 Token 到 Redis 时 JWT 解析失败: {str(e)}")
        raise ValueError(f"Invalid token: {str(e)}")

    # 1. 检查用户已有的 Token 数量
    redis_client = RedisClientManager.get_client()
    token_count = redis_client.hlen(redis_key)

    # 2. 如果达到上限，删除最早的 Token
    if token_count >= MAX_TOKEN_PER_USER:
        # 获取所有 Token，按 JTI（时间戳）排序，删除最早的
        tokens = redis_client.hgetall(redis_key)
        if tokens:
            try:
                sorted_tokens = sorted(tokens.items(), key=lambda x: int(x[0]))
                if sorted_tokens:
                    oldest_token_jti, _ = sorted_tokens[0]
                    redis_client.hdel(redis_key, oldest_token_jti)
            except (ValueError, IndexError) as e:
                logger.warning(f"删除旧 Token 时出错: {str(e)}，将直接覆盖")

    logger.info(f"用户 {user.user_name} 添加 Token: {redis_key}")

    # 3. 保存新 Token（JTI 作为字段名，用户信息 JSON 作为值）
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
    if user_data and isinstance(user_data, str):
        try:
            return CurrentUserInfo.model_validate_json(user_data)
        except Exception as e:
            logger.error(f"解析用户信息 JSON 失败: {str(e)}, data: {user_data}")
            return None
    return None


def get_redis_key_for_user(username: str) -> str:
    """生成 Redis Key"""
    return f"{settings.REDIS_PREFIX}:{app_constants.OPERATION_REDIS_PREFIX_FOR_USER}:{username}"


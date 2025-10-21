"""
JWT Token 生成和验证
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from ..config import settings


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建 JWT 访问令牌

    Args:
        data: 要编码到 token 中的数据（通常包含用户ID、用户名等）
        expires_delta: token 过期时间

    Returns:
        JWT token 字符串
    """
    to_encode = data.copy()

    # 设置过期时间
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})

    # 编码 JWT
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """
    解码 JWT 访问令牌

    Args:
        token: JWT token 字符串

    Returns:
        解码后的数据，如果失败返回 None
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError:
        return None

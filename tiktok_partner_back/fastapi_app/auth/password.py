"""
密码加密和验证
"""
from passlib.context import CryptContext

# 创建密码上下文（使用 bcrypt 算法）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    对密码进行哈希加密

    Args:
        password: 明文密码

    Returns:
        加密后的密码哈希值
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码是否正确

    Args:
        plain_password: 明文密码
        hashed_password: 加密后的密码哈希值

    Returns:
        密码是否匹配
    """
    return pwd_context.verify(plain_password, hashed_password)

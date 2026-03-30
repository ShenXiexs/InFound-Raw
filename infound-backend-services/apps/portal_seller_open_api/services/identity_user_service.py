import traceback

import bcrypt

from apps.portal_seller_open_api.app_constants import AUTH_BCRYPT_ROUNDS
from apps.portal_seller_open_api.core.config import IFRabbitMQWebSTOMPSettings
from apps.portal_seller_open_api.core.rabbitmq_producer import RabbitMQProducer
from core_base import get_logger

logger = get_logger(__name__)


def get_password_hash(password: str) -> str:
    """加密密码"""
    # 将密码编码为 bytes
    password_bytes = password.encode('utf-8')
    # 生成盐并加密
    salt = bcrypt.gensalt(rounds=AUTH_BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password_bytes, salt)
    # 返回字符串格式的哈希值
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False

    # 检查哈希值格式
    if not hashed_password.startswith(('$2a$', '$2b$', '$2y$')):
        logger.warning("无效的密码哈希值格式（不是 bcrypt 格式）")
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


async def setup_user_stomp_queue(user_id: str, settings: IFRabbitMQWebSTOMPSettings) -> bool:
    """
    为用户设置资源，如队列、交换机、绑定关系等

    :param user_id: 用户ID
    :param settings: RabbitMQ设置
    :return: 是否成功
    """

    try:
        if not RabbitMQProducer.is_initialized():
            await RabbitMQProducer.initialize(settings)
        queue_name, binding_key, _ = await RabbitMQProducer.ensure_user_notification_queue(
            user_id=user_id
        )
        logger.info(
            "Successfully initialized user notification queue",
            user_id=user_id,
            queue_name=queue_name,
            binding_key=binding_key,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to setup user notification queue for user {user_id}: {str(e)}")
        return False

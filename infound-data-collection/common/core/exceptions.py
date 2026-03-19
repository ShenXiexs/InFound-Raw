class ConsumerBaseException(Exception):
    """基础异常"""
    pass


class RabbitMQConnectionError(ConsumerBaseException):
    """RabbitMQ 连接异常"""
    pass


class MessageProcessingError(ConsumerBaseException):
    """消息处理异常"""
    pass


class NonRetryableMessageError(ConsumerBaseException):
    """不可重试的消息异常"""
    pass


class ApiClientError(ConsumerBaseException):
    """API 客户端异常"""
    pass


class PlaywrightError(ConsumerBaseException):
    """Playwright 操作异常"""
    pass

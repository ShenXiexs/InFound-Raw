class ConsumerBaseException(Exception):
    """Base exception."""
    pass


class RabbitMQConnectionError(ConsumerBaseException):
    """RabbitMQ connection error."""
    pass


class MessageProcessingError(ConsumerBaseException):
    """Message processing error."""
    pass


class NonRetryableMessageError(ConsumerBaseException):
    """Non-retryable message error."""
    pass


class ApiClientError(ConsumerBaseException):
    """API client error."""
    pass


class PlaywrightError(ConsumerBaseException):
    """Playwright operation error."""
    pass

from typing import Optional, Dict, Literal

from pydantic import Field

from core_base.settings import SettingsBase


class QueueConfig(SettingsBase):
    exchange: str = "infound.topic"
    routing_key_pattern: str = "infound.*"
    queue_name: str = ""
    durable: bool = True
    auto_delete: bool = False
    exclusive: bool = False
    # Outreach 专用字段
    queue_prefix: Optional[str] = None
    control_queue: Optional[str] = None
    control_routing_key_prefix: Optional[str] = None


class RabbitMQSettings(SettingsBase):
    host: str = Field("47.238.5.253", validation_alias="RABBITMQ__HOST")
    port: int = Field(8803, validation_alias="RABBITMQ__PORT")
    username: str = Field("infound.stg", validation_alias="RABBITMQ__USERNAME")
    password: str = Field("xy6Ucz5IZ@Z%P)", validation_alias="RABBITMQ__PASSWORD")
    vhost: str = "/infound.stg"
    prefetch_count: int = 1
    reconnect_delay: int = 5
    max_reconnect_attempts: int = 4

    # 主交换机配置（统一使用 Topic）
    exchange_name: str = "infound.topic"
    exchange_type: Literal["topic", "direct", "fanout"] = "topic"  # 添加类型字段
    routing_key_prefix: str = "infound"

    # 多队列配置
    queues: Dict[str, QueueConfig] = Field(default_factory=dict)

    # 向后兼容的旧配置字段（统一改为 topic）
    queue_name: str = "chatbot.sample.queue"
    routing_key: str = "infound.chatbot.sample"
    exchange: str = "infound.topic"  # 改为 topic

    # Outreach 相关
    outreach_queue: str = "chatbot.outreach.queue.topic"
    outreach_routing_key_prefix: str = "chatbot.outreach"
    outreach_queue_prefix: str = "chatbot.outreach.queue"

    # ✅ Outreach Control 相关（新增）
    outreach_control_queue: str = "chatbot.outreach.control.queue"
    outreach_control_routing_key_prefix: str = "chatbot.outreach.control"

    # Crawler 相关（改为 topic）
    crawler_exchange: str = "infound.topic"  # 从 crawler.direct 改为 infound.topic
    crawler_routing_key: str = "crawler.tiktok.creator.key"
    crawler_queue: str = "crawler.tiktok.creator.queue"

    @property
    def url(self) -> str:
        """构建 RabbitMQ 连接 URL"""
        from urllib.parse import quote_plus

        vhost_path = quote_plus(self.vhost or "/")
        return (
            f"amqp://{quote_plus(self.username)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{vhost_path}"
        )

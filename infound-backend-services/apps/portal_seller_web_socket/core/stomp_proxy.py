from typing import Optional, Set

import anyio
from fastapi import WebSocket

from apps.portal_seller_web_socket.core.config import IFRabbitMQWebSTOMPSettings
from core_base import get_logger
from shared_seller_application_services.current_user_info import CurrentUserInfo


class STOMPProxy:
    """STOMP 透明代理 - 对客户端隐藏 RabbitMQ 信息"""

    def __init__(
            self,
            settings: IFRabbitMQWebSTOMPSettings,
            current_user_info: CurrentUserInfo,
    ):
        self.logger = get_logger(__name__)
        self.settings = settings
        self.current_user_info = current_user_info
        self.mq_client: Optional[anyio.abc.ByteStream] = None
        self.subscription_ids: Set[str] = set()  # 跟踪所有订阅 ID
        self._is_subscribed = False
        self._running = False

    async def connect_to_mq(self) -> anyio.abc.ByteStream:
        """连接到 RabbitMQ STOMP 服务器并完成握手"""
        # 1. 建立 TCP 连接
        try:
            self.mq_client = await anyio.connect_tcp(self.settings.host, self.settings.port)
            self._running = True
            self.logger.info(
                f"Connected to RabbitMQ Web STOMP - "
                f"{self.settings.host}:{self.settings.port}, "
                f"User ID: {self.current_user_info.user_id}"
            )
        except Exception as e:
            self.logger.error(f"MQ Connection Failed: {e}")
            raise

        return self.mq_client

    async def heartbeat_loop(self):
        """【关键】主动心跳：每 10 秒向 MQ 发送一个换行符"""
        try:
            while self._running and self.mq_client:
                await anyio.sleep(10)
                # STOMP 心跳就是一个简单的换行符
                await self.mq_client.send(b"\n")
        except Exception as e:
            self.logger.debug(f"Heartbeat loop stopped: {e}")

    async def intercept_and_replace_connect_frame(self, client_data: bytes) -> bytes:
        """拦截客户端的 CONNECT 帧，替换为真实的 RabbitMQ 凭证"""
        try:
            client_frame = client_data.decode('utf-8')

            # 验证是否是 CONNECT 帧
            if not client_frame.startswith('CONNECT'):
                raise ValueError(f"Expected CONNECT frame, got: {client_frame[:100]}")

            # 构建真实的 CONNECT 帧（使用服务端配置中的凭证）
            # STOMP 1.1 格式，兼容 @stomp/stompjs
            real_connect_frame = (
                f"CONNECT\n"
                f"login:{self.settings.username}\n"
                f"passcode:{self.settings.password}\n"
                f"host:{self.settings.vhost}\n"
                f"accept-version:1.1,1.0\n"
                f"heart-beat:10000,10000\n"
                f"\n\x00"
            )

            # self.logger.info(
            #     f"STOMP CONNECT replaced - "
            #     f"User: {self.settings.username}, "
            #     f"VHost: {self.settings.vhost}, "
            #     f"User ID: {self.current_user_info.user_id}"
            # )
            return real_connect_frame.encode('utf-8')

        except Exception as e:
            self.logger.error(f"Failed to process CONNECT frame: {e}")
            raise

    async def auto_subscribe_user_queues(self) -> None:
        """
        预留自动订阅逻辑。

        当前 seller desktop 会在客户端显式发起 SUBSCRIBE：
        - /amq/queue/user.notification.{userId}

        因此这里不再强行自动订阅，避免把具体客户端订阅策略写死。
        """
        self._is_subscribed = True

    async def intercept_and_forward_subscription(
            self,
            client_data: bytes
    ) -> bytes:
        """拦截客户端的 SUBSCRIBE 帧，允许客户端动态添加订阅"""
        try:
            client_frame = client_data.decode('utf-8')

            if not client_frame.startswith('SUBSCRIBE'):
                return client_data

            # 解析 SUBSCRIBE 帧
            lines = client_frame.split('\n')
            headers = {}
            for line in lines[1:]:
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key] = value

            # 提取 subscription ID
            sub_id = headers.get('id', '')
            destination = headers.get('destination', '')

            if destination:
                self.logger.info(
                    f"Client requested subscribe destination: {destination}"
                )

            # 记录订阅
            if sub_id:
                self.subscription_ids.add(sub_id)
                self.logger.info(
                    f"Client subscribed to: {destination} (ID: {sub_id})"
                )

            return client_data

        except Exception as e:
            self.logger.error(f"Failed to process SUBSCRIBE frame: {e}")
            return client_data

    async def forward_to_mq(self, websocket: WebSocket) -> None:
        """WebSocket → RabbitMQ"""
        try:
            first_message = True
            # 统一监听 WebSocket 消息
            while True:
                # 使用 receive() 替代 iter_bytes()，这样我们可以手动处理文本或二进制
                result = await websocket.receive()

                if result["type"] == "websocket.disconnect":
                    break

                data = result.get("bytes") or result.get("text", "").encode('utf-8')
                if not data: continue

                # 处理心跳：STOMP 心跳通常是单个 \n 或 \r\n
                if data.strip() == b"":
                    await self.mq_client.send(b"\n")
                    continue

                if first_message and data.startswith(b'CONNECT'):
                    real_frame = await self.intercept_and_replace_connect_frame(data)
                    await self.mq_client.send(real_frame)
                    first_message = False
                    # await self.auto_subscribe_user_queues()
                    continue

                # elif message.startswith(b'SUBSCRIBE'):
                #     message = await self.intercept_and_forward_subscription(message)
                #
                # elif message.startswith(b'UNSUBSCRIBE'):
                #     # ... 保持你原有的 UNSUBSCRIBE 处理逻辑 ...
                #     pass

                # 转发处理后的数据到 MQ
                await self.mq_client.send(data)

        except anyio.EndOfStream:
            self.logger.debug("WebSocket to MQ forwarding stopped")
        except Exception as e:
            self.logger.error(f"Error forwarding to MQ: {e}")
            raise

    async def forward_to_client(self, websocket: WebSocket) -> None:
        """RabbitMQ → WebSocket"""
        try:
            while self._running:
                data = await self.mq_client.receive(4096)
                if not data:
                    self.logger.info("RabbitMQ connection closed by server")
                    break

                # msg_text = data.decode('utf-8', errors='ignore')

                # 关键：捕获 MQ 返回的 CONNECTED 帧
                if b"CONNECTED" in data and not self._is_subscribed:
                    await self.auto_subscribe_user_queues()

                # 如果 MQ 返回 ERROR，说明交换机没找到或权限问题
                if b"ERROR" in data:
                    self.logger.error(f"MQ returned ERROR frame: {data.decode('utf-8', 'ignore')}")

                await websocket.send_bytes(data)

        except anyio.EndOfStream:
            self.logger.debug("MQ to WebSocket forwarding stopped (stream ended)")
        except Exception as e:
            self.logger.error(f"Error forwarding to client: {e}")
            raise

    async def disconnect(self) -> None:
        """优雅断开与 RabbitMQ 的连接"""
        if self.mq_client:
            try:
                # 先取消所有订阅
                for sub_id in self.subscription_ids:
                    unsubscribe_frame = (
                        f"UNSUBSCRIBE\n"
                        f"id:{sub_id}\n"
                        f"\n\x00"
                    )
                    await self.mq_client.send(unsubscribe_frame.encode('utf-8'))

                # 发送 DISCONNECT 帧（STOMP 协议）
                await self.mq_client.send(b"DISCONNECT\nreceipt:1\n\n\x00")
                self.logger.debug("Sent DISCONNECT frame to MQ")
            except Exception as e:
                self.logger.debug(f"Error sending DISCONNECT: {e}")
            finally:
                try:
                    await self.mq_client.aclose()
                except Exception as e:
                    self.logger.debug(f"Error closing MQ connection: {e}")
                    pass

import asyncio
import signal
import sys
from asyncio import Event
from pathlib import Path

from apps.portal_async_scheduler.core.config import Settings
from apps.portal_async_scheduler.services.scheduler import initialize_scheduler, register_tasks
from apps.portal_seller_open_api.core.rabbitmq_producer import RabbitMQProducer
from core_base import SettingsFactory, get_logger
from core_redis import RedisClientManager
from shared_domain import DatabaseManager


def handle_signals(shutdown_event: Event) -> None:
    """处理系统信号"""

    def signal_handler(signum, frame):
        """信号处理函数必须简单、快速、安全"""
        try:
            signal_name = signal.Signals(signum).name
        except Exception:
            signal_name = f"UNKNOWN({signum})"

        # 只设置标志位，不做其他操作
        shutdown_event.set()

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def main() -> None:
    logger = get_logger(__name__)
    logger.info("程序启动")

    settings: Settings = SettingsFactory.initialize(
        settings_class=Settings,
        config_dir=Path(__file__).parent / "configs",
    )

    DatabaseManager.initialize(settings.mysql)
    RedisClientManager.initialize(settings.redis)

    # 创建事件
    shutdown_event = Event()

    # 注册信号处理（只传 event，不传 logger）
    handle_signals(shutdown_event)

    try:
        # 启动消费者
        scheduler = initialize_scheduler(logger, settings)

        # 注册定时任务
        register_tasks(logger, scheduler)

        # 启动调度器
        scheduler.start()

        try:
            # 主循环
            while not shutdown_event.is_set():
                try:
                    await asyncio.wait_for(
                        shutdown_event.wait(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

            # 收到信号，执行清理逻辑
            logger.info("Shutdown signal received, cleaning up...")

        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            raise

    except Exception as e:
        logger.critical("Application startup failed", exc_info=e)
        sys.exit(1)
    finally:
        logger.info("Scheduler stopped")
        await RabbitMQProducer.close()
        RedisClientManager.close()
        await DatabaseManager.close()
        logger.info("All resources cleaned up, application exited.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        pass

import argparse
import asyncio
import signal
import sys
from contextlib import suppress
from importlib import import_module
from typing import Optional

import structlog

from common.core.config import initialize_settings, get_settings
from common.core.logger import initialize_logging, get_logger
from common.mq.consumer_base import ConsumerBase

# 声明全局 Logger 变量。初始为 None 或一个占位符，将在 main() 中被配置好的实例覆盖。
logger: Optional[structlog.stdlib.BoundLogger] = None

# 全局退出信号
shutdown_signal = asyncio.Event()


# 1. 初始化命令行参数解析
def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="RabbitMQ Consumer")
    parser.add_argument(
        "--env",
        default="dev",
        help="环境代码，如 dev/stg/pro/vn"
    )
    parser.add_argument(
        "--consumer",
        required=True,
        help=f"消费端服务名"
    )
    return parser.parse_args()


def handle_signals() -> None:
    """处理系统信号"""
    global logger

    def signal_handler(signum, frame):
        if shutdown_signal.is_set():
            return
        signal_name = signal.Signals(signum).name
        # 信号处理函数必须使用全局 logger，且要检查它是否已初始化
        if logger:
            logger.info(f"Received signal: {signal_name}, initiating shutdown")
        else:
            # 初始化失败时的回退机制
            print(f"Received signal: {signal_name}, initiating shutdown (Logger not ready)", file=sys.stderr)

        shutdown_signal.set()

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def _on_consumer_task_done(task: asyncio.Task, consumer_name: str) -> None:
    global logger

    if task.cancelled():
        return

    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return

    if exc:
        if logger:
            logger.error(
                f"Consumer '{consumer_name}' terminated with an error",
                exc_info=exc,
            )
        shutdown_signal.set()
        return

    if not shutdown_signal.is_set():
        if logger:
            logger.warning(f"Consumer '{consumer_name}' exited unexpectedly")
        shutdown_signal.set()


async def start_single_consumer(consumer_name: str) -> 'ConsumerBase':
    """启动单个消费端"""
    global logger

    # 假设 ConsumerBase 位于 common.mq.consumer_base 中
    # 注意：这里需要 ConsumerBase 的定义，但为了保持简洁，我们假设它是一个可用的基类。
    try:
        consumer_module = import_module(f"apps.{consumer_name}.crawler_consumer")
        consumer_class = getattr(consumer_module, "CrawlerConsumer")
        consumer = consumer_class()

        consumer_task = asyncio.create_task(consumer.start(), name=f"consumer:{consumer_name}")
        setattr(consumer, "_run_task", consumer_task)
        consumer_task.add_done_callback(lambda task: _on_consumer_task_done(task, consumer_name))
        logger.info(f"Consumer '{consumer_name}' started successfully.")

        return consumer
    except ImportError:
        logger.critical(
            f"Failed to import consumer module for '{consumer_name}'. Ensure apps/{consumer_name}/crawler_consumer.py and class 'Consumer' exist.")
        raise
    except AttributeError:
        logger.critical(f"Consumer class 'CrawlerConsumer' not found in apps.{consumer_name}.crawler_consumer.")
        raise


async def main() -> None:
    global logger
    args = parse_args()
    consumer = None

    try:
        # A. 初始化配置 (Configuration Initialization)
        # 必须是第一个调用的初始化函数

        initialize_settings(env_arg=args.env, consumer_arg=args.consumer)
        settings = get_settings()

        # B. 初始化日志 (Logging Initialization)
        # 必须在配置初始化之后调用
        initialize_logging()

        # C. 重新获取全局 Logger 实例 (现在它是结构化且配置好的)
        # 覆盖模块级 logger 变量
        logger = get_logger(__name__)

        # 信号处理（现在 logger 已配置）
        handle_signals()

        logger.info(
            "程序启动",
            consumer_id=settings.CONSUMER,
            env=settings.ENV,
            log_level=settings.LOG_LEVEL
        )

        # 启动消费者
        consumer = await start_single_consumer(args.consumer)

        # 等待退出信号
        logger.info("Application ready, waiting for shutdown signal.")
        await shutdown_signal.wait()
        logger.info("Shutdown signal received, initiating cleanup...")

    except Exception as e:
        # 任何启动阶段的异常都会被捕获并记录
        if logger:
            logger.critical("Application startup failed", exc_info=e)
        else:
            print(f"FATAL ERROR: Application startup failed: {e}", file=sys.stderr)
        # 确保进程以错误状态退出
        sys.exit(1)
    finally:
        # 清理资源
        if consumer:
            logger.info("Stopping consumers...")
            await consumer.stop()
            consumer_task = getattr(consumer, "_run_task", None)
            if consumer_task:
                with suppress(asyncio.CancelledError, asyncio.TimeoutError):
                    await asyncio.wait_for(consumer_task, timeout=5)

        if logger:
            logger.info("All resources cleaned up, application exited.")
        else:
            print("Cleaning up resources and exiting.")


if __name__ == "__main__":
    try:
        # 如果在 asyncio.run 之外发生异常，也会被顶层 except 捕获
        asyncio.run(main())
    except Exception:
        # 顶层异常处理已经交给 main() 内部的 try/except
        pass

from typing import Callable

from fastapi import FastAPI

# 定义启动钩子类型：接收 FastAPI 实例，返回 None
StartupHook = Callable[[FastAPI], None]
ShutdownHook = Callable[[FastAPI], None]


# 默认空钩子（服务无专属逻辑时使用）
def default_startup_hook(app: FastAPI):
    pass


def default_shutdown_hook(app: FastAPI):
    pass
